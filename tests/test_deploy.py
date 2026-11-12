import ast
import json
import time
from pathlib import Path

import pytest

from pipeline import deploy
from pipeline.decide import Decision

CFG = {"host_port": 18080, "app_port": 8080, "latency_limit_ms": 2000, "health_window_s": 30, "check_interval_s": 3}
PROBES = [
    {"name": "order1-total", "path": "/api/orders/1/total", "expect_status": 200, "expect_body": "950.00"},
    {"name": "order2-discount-at-threshold", "path": "/api/orders/2/discount", "expect_status": 200,
     "expect_body": "900.00"},
    {"name": "search-alice", "path": "/api/orders/search?customer=alice", "expect_status": 200,
     "expect_body": '[{"id":1,"customer":"alice"},{"id":3,"customer":"alice"}]'},
]
HEALTHY = {"/actuator/health": (200, '{"status":"UP"}'), "/api/orders/1/total": (200, "950.00"),
           "/api/orders/2/discount": (200, "900.00"),
           "/api/orders/search?customer=alice": (200, '[{"id": 1, "customer": "alice"}, {"id": 3, "customer": "alice"}]')}


class Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text
        self.headers = {"Content-Type": "application/json" if text.startswith(("{", "[")) else "text/plain"}

    def json(self):
        return json.loads(self.text)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.0)


def fake_http(routes, delay=None, clock=None, stall=None):
    """delay: {path: seconds} added to the fake clock per request. stall: (call number, seconds) frozen once."""
    calls = []

    def get(url, timeout=None):
        path = url.split("18080", 1)[1]
        calls.append(path)
        if delay and path in delay:
            clock.t += delay[path]
        if stall and len(calls) == stall[0]:
            clock.t += stall[1]
        return Resp(*routes[path])

    get.calls = calls
    return get


def window(http, cfg=CFG, clock=None, sleep=None):
    clock = clock or FakeClock()
    return deploy.health_window(cfg, PROBES, http_get=http, clock=clock, sleep=sleep or clock.sleep)


# ------------------------------------------------------------------ health window

def test_window_passes_with_every_check_recorded():
    w = window(fake_http(HEALTHY))
    assert w["passed"] is True and w["breach"] is None
    assert len(w["checks"]) == 11 and [c["t_s"] for c in w["checks"]][:3] == [0.0, 3.0, 6.0]
    assert all(c["ok"] and len(c["probes"]) == 3 for c in w["checks"])


def test_probe_bodies_compare_as_exact_json_decimals():
    assert deploy._same_body("950.00", "950.0") and not deploy._same_body("900.00", "1000.00")
    assert deploy._same_body('[{"a": 1}]', '[{"a":1}]')


def test_wrong_value_is_a_breach():
    w = window(fake_http({**HEALTHY, "/api/orders/2/discount": (200, "1000.00")}))
    assert w["passed"] is False and len(w["checks"]) == 1
    assert w["breach"]["breaches"] == ["probe order2-discount-at-threshold returned http=200 body='1000.00', "
                                       "expected http=200 body='900.00'"]


def test_latency_over_limit_is_a_breach():
    clock = FakeClock()
    w = window(fake_http(HEALTHY, delay={"/api/orders/2/discount": 3.015}, clock=clock), clock=clock)
    assert w["passed"] is False and "invalid" not in w
    assert w["breach"]["breaches"] == ["probe order2-discount-at-threshold took 3015 ms, limit 2000 ms"]


# ------------------------------------------------------------------ observer suspended (host sleep)

def test_oversleep_between_checks_invalidates_the_window():
    clock = FakeClock()
    naps = iter([0, 0, 267])                       # third sleep: the host was suspended for 267 s extra

    def sleep(s):
        clock.t += max(s, 0.0) + next(naps, 0)

    w = window(fake_http(HEALTHY, clock=clock), clock=clock, sleep=sleep)
    assert w["passed"] is None and w["breach"] is None
    assert w["invalid"]["invalid"] == "observer_suspended" and w["invalid"]["sign"] == "gap between checks"
    assert w["invalid"]["gap_s"] > 9 and w["invalid"]["limit_s"] == 9
    assert len(w["checks"]) == 4


def test_request_frozen_mid_check_is_not_a_breach():
    # The 264 s health request seen on the laptop: a host freeze, not the service (its timeout is 5 s).
    clock = FakeClock()
    w = window(fake_http(HEALTHY, clock=clock, stall=(16, 264.0)), clock=clock)
    assert w["passed"] is None and w["invalid"]["sign"] == "request outlasted its timeout"
    assert w["invalid"]["request_s"] == 264.0 and w["invalid"]["limit_s"] == 14.0


def test_hung_service_is_still_a_breach_not_a_suspension():
    clock = FakeClock()
    import requests as rq

    def timing_out(url, timeout=None):
        clock.t += timeout                          # every request runs into its own timeout
        raise rq.Timeout("read timed out")

    w = window(timing_out, clock=clock)
    assert w["passed"] is False and "invalid" not in w
    assert w["breach"]["breaches"][0] == "/actuator/health not UP (http=None, status=None)"


def test_release_with_suspended_observer_neither_promotes_nor_counts_a_rollback(tmp_path, monkeypatch):
    invalid = {"invalid": "observer_suspended", "sign": "gap between checks", "gap_s": 267.0, "limit_s": 9}
    events = _fake_swap(monkeypatch, {"passed": None, "invalid": invalid, "checks": [{"ok": True}],
                                      "breach": None, "breach_clock": None})
    res = deploy.release(AUTO, tmp_path, "r", run_dir=tmp_path, cfg=CFG)
    assert res["outcome"] == "invalid: observer_suspended" and res["rolled_back"] is None
    assert events == ["stop", "run order-service:baseline", "wait healthy=True"]
    rec = json.loads((tmp_path / "deploy.json").read_text(encoding="utf-8"))
    assert rec["outcome"] == "invalid" and rec["invalid"] == invalid and "promoted_image" not in rec
    assert not (tmp_path / "rollback.json").exists()


def test_health_down_is_a_breach():
    w = window(fake_http({**HEALTHY, "/actuator/health": (503, '{"status":"DOWN"}')}))
    assert w["breach"]["breaches"] == ["/actuator/health not UP (http=503, status=DOWN)"]


# ------------------------------------------------------------------ approval gate and release

AUTO = Decision("low", "AUTO_APPLY", ("ok",), "v")
ESC = Decision("medium", "ESCALATE", ("diff touches a sensitive path",), "v")
REJ = Decision("high", "REJECT", ("V2 failed",), "v")


@pytest.mark.parametrize("decision, approval, allowed", [
    (AUTO, None, True), (ESC, None, False), (ESC, {"answer": "reject"}, False),
    (ESC, {"answer": "no_answer"}, False), (ESC, {"answer": "approve", "user": "u", "time": "t"}, True),
    (REJ, None, False), (REJ, {"answer": "approve"}, False),
])
def test_may_deploy(decision, approval, allowed):
    assert deploy.may_deploy(decision, approval)[0] is allowed


@pytest.mark.parametrize("decision", [ESC, REJ])
def test_release_never_deploys_without_permission(tmp_path, monkeypatch, decision):
    monkeypatch.setattr(deploy, "deploy", lambda *a, **k: pytest.fail("deploy must not be called"))
    res = deploy.release(decision, tmp_path, "r", run_dir=tmp_path, cfg=CFG)
    assert res["deployed"] is False and res["awaiting_review"] is (decision is ESC)
    assert not (tmp_path / "deploy.json").exists()


def _fake_swap(monkeypatch, window_result):
    events = []
    monkeypatch.setattr(deploy, "deploy", lambda src, run_id, cfg: {
        "run_id": run_id, "new_image": "order-service:new", "previous_image": "order-service:baseline",
        "build_s": 1.0, "swap_to_answer_s": 2.0, "answered": True, "swap_started_at": "t", "swap_clock": 0.0})
    monkeypatch.setattr(deploy, "health_window", lambda cfg: window_result)
    monkeypatch.setattr(deploy, "_stop_app", lambda: events.append("stop"))
    monkeypatch.setattr(deploy, "_run_app", lambda tag, cfg: events.append(f"run {tag}"))
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, **k: events.append(f"wait healthy={healthy}") or 1.0)
    return events


def test_release_promotes_on_a_clean_window(tmp_path, monkeypatch):
    events = _fake_swap(monkeypatch, {"passed": True, "checks": [{"ok": True}], "breach": None, "breach_clock": None})
    res = deploy.release(AUTO, tmp_path, "r", run_dir=tmp_path, cfg=CFG)
    assert res["outcome"] == "promoted" and res["rolled_back"] is False and events == []
    rec = json.loads((tmp_path / "deploy.json").read_text(encoding="utf-8"))
    assert rec["outcome"] == "promoted" and rec["promoted_image"] == "order-service:new"
    assert not (tmp_path / "rollback.json").exists()


def test_release_rolls_back_to_previous_image_on_breach(tmp_path, monkeypatch):
    breach = {"ok": False, "breaches": ["probe x took 3021 ms, limit 2000 ms"]}
    events = _fake_swap(monkeypatch, {"passed": False, "checks": [breach], "breach": breach,
                                      "breach_clock": time.monotonic()})
    approval = {"answer": "approve", "user": "u", "time": "t"}
    res = deploy.release(ESC, tmp_path, "r", approval=approval, run_dir=tmp_path, cfg=CFG)
    assert events == ["stop", "run order-service:baseline", "wait healthy=True"]
    assert res["rolled_back"] is True and res["image"] == "order-service:baseline"
    rb = json.loads((tmp_path / "rollback.json").read_text(encoding="utf-8"))
    assert rb["reason"] == "probe x took 3021 ms, limit 2000 ms" and rb["failed_check"] == breach
    assert rb["restored_image"] == "order-service:baseline" and rb["rolled_back_image"] == "order-service:new"
    assert rb["seconds_breach_to_healthy"] >= 0
    assert json.loads((tmp_path / "deploy.json").read_text(encoding="utf-8"))["outcome"] == "rolled_back"


# ------------------------------------------------------------------ approve_cli

def _ask(answers):
    it = iter(answers)

    def input_fn(prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return input_fn


@pytest.mark.parametrize("answers, expected", [(["approve"], "approve"), (["maybe", " Reject "], "reject"), ([], "no_answer"),
                                               (["﻿approve"], "approve")])
def test_approve_cli_records_answer_user_and_time(tmp_path, answers, expected):
    shown = []
    rec = deploy.approve_cli(ESC, "--- a/x\n+++ b/x\n", input_fn=_ask(answers), out=shown.append,
                             user="tester", run_dir=tmp_path)
    assert rec["answer"] == expected and rec["user"] == "tester" and rec["time"].endswith("+00:00")
    assert rec["approval_source"] == "human_cli"
    assert "--- a/x\n+++ b/x" in shown and any("diff touches a sensitive path" in s for s in shown)
    assert json.loads((tmp_path / "approval.json").read_text(encoding="utf-8")) == rec


def test_approve_cli_records_scripted_source_and_refuses_unknown_ones(tmp_path):
    rec = deploy.approve_cli(ESC, "d", input_fn=_ask(["approve"]), out=lambda s: None, source="scripted_test")
    assert rec["approval_source"] == "scripted_test"
    with pytest.raises(ValueError, match="approval source"):
        deploy.approve_cli(ESC, "d", input_fn=_ask(["approve"]), out=lambda s: None, source="human")


def test_image_tags_are_valid_docker_tags():
    assert deploy.image_tag("Demo F06/Correct 2026-10-19T12:00:00Z") == "order-service:demo-f06-correct-2026-10-19t12-00-00z"


def test_deploy_module_never_runs_git():
    tree = ast.parse(Path(deploy.__file__).read_text(encoding="utf-8"))
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "git" not in strings and not any(s.startswith("git ") for s in strings)


# ------------------------------------------------------------------ S3: smoke test, image identity, window p95

def prom(count_fast, count_slow):
    """Prometheus text: count_fast requests under 0.1 s and count_slow requests between 2.5 and 5 s."""
    total = count_fast + count_slow
    lines = []
    for le, c in (("0.1", count_fast), ("2.5", count_fast), ("5.0", total), ("+Inf", total)):
        lines.append(f'http_server_requests_seconds_bucket{{uri="/api/orders",status="200",le="{le}"}} {c}')
    lines.append(f'http_server_requests_seconds_count{{uri="/api/orders",status="200"}} {total}')
    return "\n".join(lines) + "\n"


def http_with_metrics(snapshots):
    """HEALTHY routes plus /actuator/prometheus returning the given texts in order (last one repeats)."""
    state = {"i": 0}

    def get(url, timeout=None):
        path = url.split("18080", 1)[1]
        if path == "/actuator/prometheus":
            text = snapshots[min(state["i"], len(snapshots) - 1)]
            state["i"] += 1
            return Resp(200, text)
        return Resp(*HEALTHY[path])
    return get


METRICS_CFG = {**CFG, "metrics": {"min_requests": 20}}


def test_window_p95_over_limit_is_a_breach():
    # base: nothing yet; then 10 fast + 30 slow requests -> p95 lands in the 2.5-5 s bucket
    res = window(http_with_metrics([prom(0, 0), prom(10, 30)]), cfg=METRICS_CFG)
    assert res["passed"] is False
    assert any("window p95" in b for b in res["breach"]["breaches"])


def test_window_p95_under_limit_passes_and_is_recorded():
    res = window(http_with_metrics([prom(0, 0), prom(40, 0)]), cfg=METRICS_CFG)
    assert res["passed"] is True and res["checks"][-1]["window_p95"]["requests"] == 40


def test_window_p95_with_too_few_requests_is_not_judged():
    res = window(http_with_metrics([prom(0, 0), prom(0, 5)]), cfg=METRICS_CFG)
    assert res["passed"] is True                      # 5 slow requests < min_requests: no verdict from metrics


def test_missing_metrics_are_neither_pass_nor_breach():
    res = window(fake_http({**HEALTHY, "/actuator/prometheus": (503, "down")}), cfg=METRICS_CFG)
    assert res["passed"] is True and "window_p95" not in res["checks"][0]   # no baseline snapshot: p95 not used


def test_failed_smoke_test_means_no_cutover(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(deploy, "current_image", lambda: "order-service:baseline")
    monkeypatch.setattr(deploy, "build_image", lambda src, tag: 1.0)
    monkeypatch.setattr(deploy, "image_id", lambda tag: f"sha256:{tag[-4:]}")
    monkeypatch.setattr(deploy, "smoke_test", lambda tag, cfg: {"passed": False, "reason": "candidate not healthy"})
    monkeypatch.setattr(deploy, "_run_app", lambda tag, cfg: calls.append(("run", tag)))
    monkeypatch.setattr(deploy, "_stop_app", lambda: calls.append(("stop",)))
    res = deploy.release(AUTO, tmp_path, "r", run_dir=tmp_path, cfg=CFG)
    assert calls == []                                 # the live app was never touched
    assert res["deployed"] is False and res["outcome"] == "smoke_failed" and res["rolled_back"] is None
    rec = json.loads((tmp_path / "deploy.json").read_text(encoding="utf-8"))
    assert rec["outcome"] == "smoke_failed" and rec["cutover"] is False and rec["new_image_id"]


def test_smoke_test_uses_a_separate_container_and_port_and_always_cleans_up(monkeypatch):
    seen = []
    monkeypatch.setattr(deploy, "_docker", lambda args, timeout=120: seen.append(args) or
                        type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, timeout=0: (_ for _ in ()).throw(
        deploy.DeployError("not healthy")))
    monkeypatch.setattr(deploy, "_health", lambda cfg, *a, **k: {"ok": False, "http": 503})
    res = deploy.smoke_test("order-service:x", CFG)
    run = next(a for a in seen if a[0] == "run")
    assert deploy.CANDIDATE_CONTAINER in run and "18081:8080" in run and deploy.APP_CONTAINER not in run
    assert seen[-1] == ["rm", "-f", deploy.CANDIDATE_CONTAINER] and res["passed"] is False


def test_rollback_is_verified_by_image_id(monkeypatch):
    monkeypatch.setattr(deploy, "rollback", lambda *a, **k: {"restored_image": "order-service:baseline"})
    monkeypatch.setattr(deploy, "running_image_id", lambda container=deploy.APP_CONTAINER: "sha256:aaa")
    ok = deploy.rollback_verified("order-service:baseline", "order-service:new", {}, 0.0, CFG, "sha256:aaa")
    bad = deploy.rollback_verified("order-service:baseline", "order-service:new", {}, 0.0, CFG, "sha256:bbb")
    none = deploy.rollback_verified("order-service:baseline", "order-service:new", {}, 0.0, CFG, None)
    assert (ok["restored_image_verified"], bad["restored_image_verified"], none["restored_image_verified"]) == \
        (True, False, None)


def test_fault_injection_skips_the_smoke_test_and_still_cuts_over(monkeypatch):
    """Regression (live F04 run 20261108): an injected unhealthy build must still be deployed so the fault is seen."""
    calls = []
    monkeypatch.setattr(deploy, "current_image", lambda: "order-service:baseline")
    monkeypatch.setattr(deploy, "build_image", lambda src, tag: 1.0)
    monkeypatch.setattr(deploy, "image_id", lambda tag: "sha256:x")
    monkeypatch.setattr(deploy, "smoke_test", lambda tag, cfg: pytest.fail("smoke test must not run for a fault"))
    monkeypatch.setattr(deploy, "_run_app", lambda tag, cfg: calls.append(tag))
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, **k: 1.0)
    dep = deploy.deploy(Path("."), "r-faulty", CFG, smoke=False)
    assert dep["cutover"] is True and calls == ["order-service:r-faulty"] and dep["smoke"]["passed"] is None


# ------------------------------------------------------------------ Idempotent Baseline Restoration

def test_restore_baseline_reuses_existing_healthy_container(monkeypatch):
    """Test 1: Existing healthy baseline container is reused without restart."""
    seen_docker = []
    monkeypatch.setattr(deploy, "current_image", lambda: deploy.BASELINE_TAG)
    monkeypatch.setattr(deploy, "_health", lambda cfg, *a, **k: {"ok": True, "http": 200, "status": "UP"})
    monkeypatch.setattr(deploy, "_docker", lambda args, timeout=120: seen_docker.append(args))
    
    res = deploy.restore_baseline(CFG)
    assert res["status"] == "already_healthy"
    assert res["image"] == deploy.BASELINE_TAG
    assert res["seconds"] == 0.0
    assert res["health"]["ok"] is True
    assert "running, health check UP" in res["message"]
    # Ensure no docker run or rm was called
    assert not any("run" in a or "rm" in a for a in seen_docker)


def test_restore_baseline_removes_faulty_container_and_starts_baseline(monkeypatch):
    """Test 2: Existing faulty container is stopped/removed and baseline is started and verified."""
    state = {"image": "order-service:f01-faulty"}
    monkeypatch.setattr(deploy, "current_image", lambda: state["image"])
    monkeypatch.setattr(deploy, "_health", lambda cfg, *a, **k: {"ok": True, "http": 200, "status": "UP"})
    docker_calls = []
    def fake_docker(args, timeout=120):
        docker_calls.append(args)
        if args[0] == "inspect" and args[1] == deploy.APP_CONTAINER:
            ret = 1 if len([c for c in docker_calls if c[0] == "rm"]) > 0 else 0
            return type("R", (), {"returncode": ret, "stdout": "", "stderr": ""})()
        if args[0] == "run":
            state["image"] = deploy.BASELINE_TAG
            return type("R", (), {"returncode": 0, "stdout": "cid", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(deploy, "_docker", fake_docker)
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, **k: 2.5)

    res = deploy.restore_baseline(CFG)
    assert res["status"] == "restored"
    assert res["image"] == deploy.BASELINE_TAG
    assert res["seconds"] == 2.5
    assert res["health"]["ok"] is True
    assert "restored, health check UP after 2.5s" in res["message"]
    assert any("rm" in c for c in docker_calls)
    assert any("run" in c and deploy.BASELINE_TAG in c for c in docker_calls)


def test_restore_baseline_handles_container_name_conflict(monkeypatch):
    """Test 3: Name conflict on docker run is handled idempotently with retry."""
    state = {"image": "order-service:f01-faulty"}
    monkeypatch.setattr(deploy, "current_image", lambda: state["image"])
    monkeypatch.setattr(deploy, "_health", lambda cfg, *a, **k: {"ok": True, "http": 200, "status": "UP"})
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, **k: 1.8)
    
    run_attempts = []
    def fake_docker(args, timeout=120):
        if args[0] == "run":
            run_attempts.append(args)
            if len(run_attempts) == 1:
                return type("R", (), {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": f'Conflict. The container name "/{deploy.APP_CONTAINER}" is already in use by container "abc".'
                })()
            state["image"] = deploy.BASELINE_TAG
            return type("R", (), {"returncode": 0, "stdout": "cid123", "stderr": ""})()
        return type("R", (), {"returncode": 1 if args[0] == "inspect" else 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(deploy, "_docker", fake_docker)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    res = deploy.restore_baseline(CFG)
    assert res["status"] == "restored"
    assert len(run_attempts) == 2


def test_restore_baseline_fails_on_startup_error(monkeypatch):
    """Test 4: Permanent docker run error raises DeployError."""
    monkeypatch.setattr(deploy, "current_image", lambda: "order-service:f01-faulty")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    def fake_docker(args, timeout=120):
        if args[0] == "run":
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": "docker daemon fatal error: image corrupted"})()
        return type("R", (), {"returncode": 1 if args[0] == "inspect" else 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(deploy, "_docker", fake_docker)

    with pytest.raises(deploy.DeployError, match="docker run order-service:baseline failed"):
        deploy.restore_baseline(CFG)


def test_restore_baseline_fails_on_health_verification(monkeypatch):
    """Test 5: Failed /actuator/health verification raises DeployError and does not claim restored."""
    state = {"image": "order-service:f01-faulty"}
    monkeypatch.setattr(deploy, "current_image", lambda: state["image"])
    def fake_docker(args, timeout=120):
        if args[0] == "run":
            state["image"] = deploy.BASELINE_TAG
            return type("R", (), {"returncode": 0, "stdout": "cid", "stderr": ""})()
        return type("R", (), {"returncode": 1 if args[0] == "inspect" else 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(deploy, "_docker", fake_docker)
    monkeypatch.setattr(deploy, "wait_until", lambda cfg, healthy, **k: 1.0)
    monkeypatch.setattr(deploy, "_health", lambda cfg, *a, **k: {"ok": False, "http": 503, "status": "DOWN"})

    with pytest.raises(deploy.DeployError, match="Baseline health verification failed: status=DOWN"):
        deploy.restore_baseline(CFG)
