import hashlib
import json
from pathlib import Path

import pytest
import requests

from pipeline import providers
from pipeline.providers import Diagnosis, Cause, ProviderError, get_provider

REPO = Path(__file__).resolve().parents[1]
SERVICE = "app/src/main/java/com/autoimmune/orders/OrderService.java"
CONTROLLER = "app/src/main/java/com/autoimmune/orders/OrderController.java"
ENV = {"LLM_BASE_URL": "http://llm.invalid/v1", "LLM_MODEL": "test-model", "LLM_API_KEY": "not-a-real-key"}

# Shape of the F01 container log (Spring Boot 3.5, logback), trimmed. Line 46 is customer.trim() after inject.diff.
NPE_TRACE = """\
2026-10-19T05:29:06.208Z ERROR 1 --- [order-service] [nio-8080-exec-2] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed: java.lang.NullPointerException: Cannot invoke "String.trim()" because "customer" is null] with root cause

java.lang.NullPointerException: Cannot invoke "String.trim()" because "customer" is null
\tat com.autoimmune.orders.OrderService.searchByCustomer(OrderService.java:46) ~[!/:0.1.0]
\tat com.autoimmune.orders.OrderController.search(OrderController.java:39) ~[!/:0.1.0]
\tat java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:103) ~[na:na]
\tat org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:258) ~[spring-web-6.2.11.jar!/:6.2.11]
\tat org.apache.tomcat.util.threads.TaskThread$WrappingRunnable.run(TaskThread.java:63) ~[tomcat-embed-core-10.1.46.jar!/:na]
\tat java.base/java.lang.Thread.run(Thread.java:1583) ~[na:na]
"""


def sources():
    return {p: (REPO / p).read_text(encoding="utf-8") for p in (SERVICE, CONTROLLER)}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network call attempted")

    monkeypatch.setattr(providers.requests, "post", fail)
    return calls


class FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def fake_llm(monkeypatch, replies):
    """Mock requests.post: returns replies in order (last one repeats). Returns the list of request bodies."""
    bodies = []

    def post(url, json=None, headers=None, timeout=None):
        bodies.append(json)
        return FakeResponse(replies[min(len(bodies), len(replies)) - 1])

    monkeypatch.setattr(providers.requests, "post", post)
    return bodies


# ---------------------------------------------------------------- rule mode

def test_rule_mode_uses_top_app_frame_of_stack_trace():
    diag = get_provider("rule").diagnose({"kind": "exception", "fault_id": "F01", "status": 500,
                                          "stack_trace": NPE_TRACE}, sources())
    assert diag.provider_mode == "rule"
    assert diag.model is None
    assert diag.oracle_localisation is False
    top = diag.causes[0]
    assert (top.rank, top.file, top.line) == (1, SERVICE, 46)
    assert "NullPointerException" in top.evidence and "searchByCustomer" in top.reason
    assert [(c.rank, c.file, c.line) for c in diag.causes[1:]] == [(2, CONTROLLER, 39)]
    assert all(not c.file.startswith(("java", "org")) for c in diag.causes)


def test_rule_mode_probe_incident_falls_back_to_fault_json():
    incident = {"kind": "probe_mismatch", "fault_id": "F06", "endpoint": "/api/orders/2/discount",
                "status": 200, "expected": "900.00", "actual": "1000.00"}
    diag = get_provider("rule").diagnose(incident, sources())
    assert diag.oracle_localisation is True
    assert diag.to_dict()["oracle_localisation"] is True
    assert len(diag.causes) == 1
    cause = diag.causes[0]
    assert (cause.rank, cause.file, cause.line) == (1, SERVICE, None)
    assert "oracle localisation" in cause.reason
    assert '"actual": "1000.00"' in cause.evidence


def test_rule_mode_health_down_uses_config_file():
    diag = get_provider("rule").diagnose({"kind": "health_down", "fault_id": "F04", "status": 503}, {})
    assert diag.oracle_localisation is True
    assert diag.causes[0].file == "app/src/main/resources/application.properties"


def test_rule_mode_without_trace_or_fault_fails_cleanly():
    with pytest.raises(ProviderError, match="no stack trace"):
        get_provider("rule").diagnose({"kind": "probe_mismatch"}, {})


# ---------------------------------------------------------------- scripted mode

def test_scripted_mode_loads_f06_candidates():
    diag = Diagnosis(causes=[Cause(1, SERVICE, None, "r", "e")], provider_mode="rule")
    patches = get_provider("scripted").draft_patches(diag, sources(), "F06", n=None)
    kinds = [p.candidate_kind for p in patches]
    assert kinds == ["correct", "ineffective", "insecure", "overfitting", "regressive", "slow"]
    for p in patches:
        assert p.provider_mode == "scripted" and p.model is None
        assert p.applies is True, p.apply_error
        assert p.diff == (REPO / "faults/F06/candidates" / f"{p.candidate_kind}.diff").read_text(encoding="utf-8")
        assert p.candidate_kind not in p.candidate_id      # ids stay opaque to the decision engine
    assert len({p.candidate_id for p in patches}) == 6
    assert len(get_provider("scripted").draft_patches(diag, sources(), "F06")) == 3


@pytest.mark.parametrize("fault", ["F06", "F01", "F04"])
def test_every_scripted_candidate_applies_on_top_of_its_fault(fault):
    # Regression: text-mode stdin on Windows rewrote \n as \r\n and made some F04 hunks fail to apply.
    diag = Diagnosis(causes=[Cause(1, SERVICE, None, "r", "e")], provider_mode="rule")
    patches = get_provider("scripted").draft_patches(diag, {}, fault, n=None)
    assert patches and [(p.candidate_kind, p.applies, p.apply_error) for p in patches if not p.applies] == []


def test_scripted_mode_never_opens_labels_or_hidden_tests(monkeypatch):
    opened = []
    real_read_text = Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(self.as_posix())
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    diag = Diagnosis(causes=[Cause(1, SERVICE, None, "r", "e")], provider_mode="rule")
    get_provider("scripted").draft_patches(diag, {}, "F06", n=None)
    assert opened and not [p for p in opened if "labels.json" in p or "hidden_tests" in p]


def test_hidden_tests_are_refused_as_source_files():
    with pytest.raises(ProviderError, match="hidden tests"):
        get_provider("rule").diagnose({"kind": "health_down", "fault_id": "F04"},
                                      {"faults/F04/hidden_tests/F04HiddenTest.java": "class X {}"})


# ---------------------------------------------------------------- replay mode

def test_replay_mode_reads_cache_and_makes_no_network_call(tmp_path, no_network):
    prov = get_provider("replay", cache_dir=tmp_path, env=ENV)
    incident = {"kind": "exception", "fault_id": "F01", "stack_trace": NPE_TRACE}
    key = prov.cache_key(prov.diagnosis_messages(incident, sources()))
    answer = {"causes": [{"rank": 1, "file": SERVICE, "line": 46, "reason": "customer is not null-checked",
                          "evidence": "NullPointerException at OrderService.java:46"}]}
    response = json.dumps(answer)
    (tmp_path / f"{key}.json").write_text(json.dumps({"key": key, "cache_key_version": providers.CACHE_KEY_VERSION,
                                                      "response": response}), encoding="utf-8")

    diag = prov.diagnose(incident, sources())

    assert no_network == []
    assert diag.provider_mode == "replay" and diag.model == "test-model"
    assert (diag.causes[0].file, diag.causes[0].line) == (SERVICE, 46)
    assert diag.attempts == [{"attempt": 1, "cache_key": key, "raw_sha256": sha(response), "ok": True,
                              "error": None, "parse_repairs": []}]


def test_replay_cache_miss_is_a_clear_error(tmp_path, no_network):
    prov = get_provider("replay", cache_dir=tmp_path, env=ENV)
    with pytest.raises(ProviderError, match="replay cache miss"):
        prov.diagnose({"kind": "exception", "stack_trace": NPE_TRACE}, sources())
    assert no_network == []


def test_cache_key_ignores_fault_id_and_changes_with_temperature(tmp_path):
    a = get_provider("replay", cache_dir=tmp_path, env=ENV)
    b = get_provider("replay", cache_dir=tmp_path, env=ENV, temperature=0.7)
    m1 = a.diagnosis_messages({"kind": "x", "fault_id": "F01"}, {})
    m2 = a.diagnosis_messages({"kind": "x", "fault_id": "F06"}, {})
    assert m1 == m2 and "F01" not in json.dumps(m1)
    assert a.cache_key(m1) != b.cache_key(m1)


def test_llm_modes_need_env_vars(tmp_path):
    with pytest.raises(ProviderError, match="LLM_MODEL"):
        get_provider("live", cache_dir=tmp_path, env={"LLM_BASE_URL": "http://x/v1"})


# ---------------------------------------------------------------- live mode (HTTP mocked)

def test_invalid_json_is_retried_then_fails_cleanly(tmp_path, monkeypatch):
    bodies = fake_llm(monkeypatch, ["this is not json"])
    prov = get_provider("live", cache_dir=tmp_path, env=ENV)
    with pytest.raises(ProviderError) as exc:
        prov.diagnose({"kind": "exception", "stack_trace": NPE_TRACE}, sources())
    assert len(bodies) == 3                                   # first attempt + 2 retries
    assert "no valid response after 3 attempts" in str(exc.value)
    assert len(list(tmp_path.glob("*.json"))) == 3            # every response saved
    assert "That answer was invalid" in bodies[1]["messages"][-1]["content"]


def test_too_many_causes_is_retried_then_accepted(tmp_path, monkeypatch):
    cause = {"rank": 1, "file": SERVICE, "line": 46, "reason": "r", "evidence": "e"}
    four = {"causes": [dict(cause, rank=i) for i in range(1, 5)]}
    ok = {"causes": [cause]}
    bodies = fake_llm(monkeypatch, [json.dumps(four), "```json\n" + json.dumps(ok) + "\n```"])
    diag = get_provider("live", cache_dir=tmp_path, env=ENV).diagnose({"kind": "exception"}, sources())
    assert len(bodies) == 2
    assert [a["ok"] for a in diag.attempts] == [False, True]
    assert "too long" in diag.attempts[0]["error"]
    assert diag.provider_mode == "live" and diag.causes[0].line == 46
    saved = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.json")]
    assert {s["model"] for s in saved} == {"test-model"} and len(saved) == 2
    assert all("not-a-real-key" not in json.dumps(s) for s in saved)   # key never written to cache


def test_live_patches_are_apply_checked(tmp_path, monkeypatch):
    good = (REPO / "faults/F06/candidates/correct.diff").read_text(encoding="utf-8")
    bad = good.replace("compareTo(DISCOUNT_THRESHOLD) > 0", "compareTo(SOMETHING_ELSE) > 0")
    fake_llm(monkeypatch, [json.dumps({"patches": [{"diff": good, "explanation": "restore >="},
                                                   {"diff": bad, "explanation": "wrong context"}]})])
    diag = Diagnosis(causes=[Cause(1, SERVICE, 41, "r", "e")], provider_mode="live")
    patches = get_provider("live", cache_dir=tmp_path, env=ENV).draft_patches(diag, sources(), "F06", n=2)
    assert [p.candidate_id for p in patches] == ["F06-live-1", "F06-live-2"]
    assert patches[0].applies is True and patches[0].apply_error is None
    assert patches[1].applies is False and "patch does not apply" in patches[1].apply_error
    assert all(p.candidate_kind is None and p.attempts[-1]["ok"] for p in patches)


def test_cache_files_contain_no_secrets():
    cache_dir = REPO / "cache"
    patterns = ["Bearer ", "sk-", "api_key"]
    for path in cache_dir.glob("*.json"):
        content = path.read_text(encoding="utf-8")
        for pat in patterns:
            assert pat.lower() not in content.lower(), f"Secret pattern {pat!r} found in {path}"


# --------------------------------------------------------------------------- prompt leakage guard (audit F-15)

def test_prompts_never_carry_fault_ids_or_oracle_words():
    """Nothing the model sees may name the fault, a candidate kind, or the oracle (roadmap S4 leakage rule)."""
    import re
    p = providers.LLMProvider("replay", env=ENV)
    incident = {"fault_id": "F06", "kind": "probe_mismatch", "rule": "probe_mismatch",
                "endpoint": "/api/orders/2/discount", "status": 200, "expected": "900.00", "actual": "1000.00"}
    diag = Diagnosis(causes=[Cause(rank=1, file=SERVICE, line=40, reason="threshold check", evidence="probe returned 1000.00")], provider_mode="replay")
    messages = p.diagnosis_messages(incident, sources()) + p.patch_messages(diag, sources(), 3)
    text = json.dumps(messages)
    assert not re.search(r"\bF\d\d\b", text), "fault id reached the prompt"
    for word in ("hidden_tests", "HiddenTest", "labels.json", "overfitting", "regressive", "insecure",
                 "ineffective", "candidate_kind", "expected_symptom", "diagnosed_file"):
        assert word not in text, word


# --------------------------------------------------------------------------- S2: diff structure / normalizer

F06_CORRECT = (REPO / "faults/F06/candidates/correct.diff").read_text(encoding="utf-8")
F06_HUNK_ONLY = F06_CORRECT[F06_CORRECT.index("@@"):]       # the qwen2.5-coder:7b failure shape (audit F-14)


@pytest.mark.parametrize("fault", ["F01", "F04", "F06"])
def test_every_scripted_candidate_is_structurally_valid(fault):
    for path in sorted((REPO / "faults" / fault / "candidates").glob("*.diff")):
        assert providers.validate_diff_structure(path.read_text(encoding="utf-8")) == [], path.name


def test_validator_names_each_structural_problem():
    v = providers.validate_diff_structure
    assert v("") == ["empty diff"]
    assert "no ---/+++ file header" in v(F06_HUNK_ONLY)
    assert any("no ---/+++ file header before it" in p for p in v(F06_HUNK_ONLY))
    assert "CRLF line endings" in v(F06_CORRECT.replace("\n", "\r\n"))
    assert "no trailing newline" in v(F06_CORRECT.rstrip("\n"))
    malformed = F06_CORRECT.replace("@@ -36,7 +36,7 @@", "@@ -36,7 +36,7")
    assert any("malformed header" in p for p in v(malformed))
    too_few = F06_CORRECT.replace("@@ -36,7 +36,7 @@", "@@ -36,9 +36,9 @@")
    assert any("does not match header" in p for p in v(too_few))
    too_many = F06_CORRECT.replace("@@ -36,7 +36,7 @@", "@@ -36,5 +36,5 @@")
    assert any("more body lines than header" in p for p in v(too_many))
    assert "no hunks" in v("--- a/x\n+++ b/x\n")


def test_normalizer_adds_headers_only_for_a_single_target_file():
    text, rules = providers.normalize_diff(F06_HUNK_ONLY, {SERVICE})
    assert rules == ["add_file_headers"]
    assert text == f"--- a/{SERVICE}\n+++ b/{SERVICE}\n" + F06_HUNK_ONLY
    assert providers.validate_diff_structure(text) == []
    assert providers.normalize_diff(F06_HUNK_ONLY, {SERVICE, CONTROLLER}) == (F06_HUNK_ONLY, [])
    assert providers.normalize_diff(F06_HUNK_ONLY, set()) == (F06_HUNK_ONLY, [])


def test_normalizer_is_deterministic_and_fixes_line_endings():
    crlf = F06_CORRECT.replace("\n", "\r\n").rstrip("\r\n")
    first = providers.normalize_diff(crlf, {SERVICE})
    assert first == providers.normalize_diff(crlf, {SERVICE})
    assert first == (F06_CORRECT, ["crlf_to_lf", "trailing_newline"])


def draft(monkeypatch, tmp_path, diffs, causes_files=(SERVICE,)):
    response = json.dumps({"patches": [{"diff": d, "explanation": "x"} for d in diffs]})
    fake_llm(monkeypatch, [response])
    causes = [Cause(i, f, None, "r", "e") for i, f in enumerate(causes_files, start=1)]
    diag = Diagnosis(causes=causes, provider_mode="live")
    prov = get_provider("live", cache_dir=tmp_path, env=ENV)
    return prov.draft_patches(diag, sources(), "F06", n=len(diffs)), response


def test_raw_valid_patch_is_used_unchanged(tmp_path, monkeypatch):
    (p,), response = draft(monkeypatch, tmp_path, [F06_CORRECT])
    assert p.format_status == "raw_valid" and p.format_problems == []
    assert p.diff == F06_CORRECT and p.raw_diff is None
    assert p.raw_diff_sha256 == p.diff_sha256 == sha(F06_CORRECT)
    assert p.normalizer_version is None and p.normalizer_rules == []
    assert p.raw_output_sha256 == sha(response) == p.attempts[-1]["raw_sha256"]
    assert p.applies is True


def test_headerless_hunk_is_normalized_and_both_hashes_are_kept(tmp_path, monkeypatch):
    (p,), response = draft(monkeypatch, tmp_path, [F06_HUNK_ONLY])
    assert p.format_status == "normalized"
    assert p.normalizer_rules == ["add_file_headers"]
    assert p.normalizer_version == providers.NORMALIZER_VERSION
    assert any("file header" in prob for prob in p.format_problems)
    assert p.raw_diff == F06_HUNK_ONLY and p.diff.startswith(f"--- a/{SERVICE}\n+++ b/{SERVICE}\n@@")
    assert p.raw_diff_sha256 == sha(F06_HUNK_ONLY) and p.diff_sha256 == sha(p.diff) != p.raw_diff_sha256
    assert p.raw_output_sha256 == sha(response)
    assert p.applies is True, p.apply_error           # the normalized diff really applies


def test_unfixable_diffs_are_marked_invalid_and_left_untouched(tmp_path, monkeypatch):
    miscounted = F06_CORRECT.replace("@@ -36,7 +36,7 @@", "@@ -36,9 +36,9 @@")
    patches, _ = draft(monkeypatch, tmp_path, [F06_HUNK_ONLY, miscounted], causes_files=(SERVICE, CONTROLLER))
    for p, raw in zip(patches, [F06_HUNK_ONLY, miscounted]):
        assert p.format_status == "invalid"
        assert p.diff == raw and p.raw_diff is None and p.normalizer_rules == []
        assert p.diff_sha256 == p.raw_diff_sha256 == sha(raw)
        assert p.normalizer_version == providers.NORMALIZER_VERSION and p.format_problems
        assert p.applies is False and p.apply_error     # failure is an outcome, not hidden


def test_scripted_patches_carry_no_llm_format_status():
    diag = Diagnosis(causes=[Cause(1, SERVICE, None, "r", "e")], provider_mode="rule")
    for p in get_provider("scripted").draft_patches(diag, {}, "F06", n=None):
        assert p.format_status is None and p.raw_output_sha256 is None


def test_every_attempt_records_raw_sha_and_cache_key(tmp_path, monkeypatch):
    cause = {"rank": 1, "file": SERVICE, "line": 46, "reason": "r", "evidence": "e"}
    replies = ["not json", json.dumps({"causes": [cause]})]
    fake_llm(monkeypatch, replies)
    diag = get_provider("live", cache_dir=tmp_path, env=ENV).diagnose({"kind": "exception"}, sources())
    assert [a["raw_sha256"] for a in diag.attempts] == [sha(r) for r in replies]
    assert all(len(a["cache_key"]) == 64 for a in diag.attempts)
    assert len({a["cache_key"] for a in diag.attempts}) == 2   # the retry prompt differs, so does its key


def test_transport_error_attempt_has_no_raw_sha(tmp_path, monkeypatch):
    answer = json.dumps({"causes": [{"rank": 1, "file": SERVICE, "line": 46, "reason": "r", "evidence": "e"}]})
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            raise requests.ConnectionError("refused")
        return FakeResponse(answer)

    monkeypatch.setattr(providers.requests, "post", post)
    diag = get_provider("live", cache_dir=tmp_path, env=ENV).diagnose({"kind": "exception"}, sources())
    first, second = diag.attempts
    assert first["ok"] is False and first["raw_sha256"] is None and "ConnectionError" in first["error"]
    assert second["ok"] is True and second["raw_sha256"] == sha(answer)


# --------------------------------------------------------------------------- S2: versioned cache key

def test_cache_key_includes_version_and_new_entries_record_it(tmp_path, monkeypatch):
    prov = get_provider("live", cache_dir=tmp_path, env=ENV)
    msgs = prov.diagnosis_messages({"kind": "x"}, {})
    assert prov.cache_key(msgs) != prov.cache_key(msgs, version=1)
    assert prov.cache_key(msgs) != prov.cache_key(msgs, version=providers.CACHE_KEY_VERSION + 1)

    cause = {"rank": 1, "file": SERVICE, "line": 46, "reason": "r", "evidence": "e"}
    fake_llm(monkeypatch, [json.dumps({"causes": [cause]})])
    diag = prov.diagnose({"kind": "exception"}, sources())
    (entry_path,) = tmp_path.glob("*.json")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    assert entry["cache_key_version"] == providers.CACHE_KEY_VERSION
    assert entry["key"] == entry_path.stem == diag.attempts[0]["cache_key"]


def test_replay_of_old_key_scheme_names_the_version_mismatch(tmp_path, no_network):
    prov = get_provider("replay", cache_dir=tmp_path, env=ENV)
    incident = {"kind": "exception", "stack_trace": NPE_TRACE}
    old_key = prov.cache_key(prov.diagnosis_messages(incident, sources()), version=1)
    (tmp_path / f"{old_key}.json").write_text(json.dumps({"key": old_key, "response": "{}"}), encoding="utf-8")
    with pytest.raises(ProviderError, match="version mismatch.*cache key version 1"):
        prov.diagnose(incident, sources())
    assert no_network == []


def test_replay_entry_without_matching_version_field_is_refused(tmp_path, no_network):
    prov = get_provider("replay", cache_dir=tmp_path, env=ENV)
    incident = {"kind": "exception", "stack_trace": NPE_TRACE}
    key = prov.cache_key(prov.diagnosis_messages(incident, sources()))
    (tmp_path / f"{key}.json").write_text(json.dumps({"key": key, "response": "{}"}), encoding="utf-8")
    with pytest.raises(ProviderError, match="version mismatch.*cache_key_version=None"):
        prov.diagnose(incident, sources())


# --------------------------------------------------------------------------- recorded parse repairs, rate limits

def test_parse_json_records_every_repair():
    assert providers._parse_json('{"a": 1}') == ({"a": 1}, [])
    assert providers._parse_json('```json\n{"a": 1}\n```') == ({"a": 1}, ["code_fence_removed"])
    data, rep = providers._parse_json('{"causes":[{"rank":1}]}]')        # gpt-oss-120b's stray bracket
    assert data == {"causes": [{"rank": 1}]} and rep == ["trailing_text_ignored:']'"]
    data, rep = providers._parse_json('Here you go: {"a": 2} thanks')
    assert data == {"a": 2} and rep[0] == "leading_text_ignored" and rep[1].startswith("trailing_text_ignored")
    with pytest.raises(ValueError):
        providers._parse_json("no json here")
    with pytest.raises(ValueError):
        providers._parse_json('{"a": ')


def test_rate_limit_waits_with_retry_after_and_is_recorded(monkeypatch):
    waited = []
    monkeypatch.setattr(providers, "_sleep", lambda s: waited.append(s))
    resp = requests.Response()
    resp.status_code, resp.headers["Retry-After"] = 429, "7"
    assert providers._rate_limit_wait(requests.HTTPError(response=resp), 1) == 7.0 and waited == [7.0]
    resp.headers["Retry-After"] = "999"
    assert providers._rate_limit_wait(requests.HTTPError(response=resp), 1) == providers.RATE_LIMIT_MAX_WAIT_S
    other = requests.Response()
    other.status_code = 404
    assert providers._rate_limit_wait(requests.HTTPError(response=other), 1) is None
    assert providers._rate_limit_wait(requests.ConnectionError("x"), 1) is None


# --------------------------------------------------------------------------- normalizer v2: '@@' without ranges

SRC_PATH = "app/src/main/java/X.java"
SRC = "class X {\n    int a = 1;\n    int b = 2;\n    int c = 3;\n    int d = 4;\n}\n"


def test_rangeless_hunk_with_context_gets_correct_ranges():
    diff = f"--- a/{SRC_PATH}\n+++ b/{SRC_PATH}\n@@\n-    int b = 2;\n+    int b = 20;\n     int c = 3;\n"
    fixed, rules = providers.normalize_diff(diff, {SRC_PATH}, {SRC_PATH: SRC})
    assert "compute_hunk_ranges" in rules and providers.validate_diff_structure(fixed) == []
    assert "@@ -1,4 +1,4 @@" in fixed                      # 2 lines of added leading context + block of 2
    assert "+    int b = 20;" in fixed and "-    int b = 2;" in fixed   # content untouched


def test_zero_context_hunk_gets_real_source_context_and_markers_are_dropped():
    diff = f"--- a/{SRC_PATH}\n+++ b/{SRC_PATH}\n@@\n-    int c = 3;\n+    int c = 30;\n*** End of File"
    fixed, rules = providers.normalize_diff(diff, {SRC_PATH}, {SRC_PATH: SRC})
    assert rules == ["drop_patch_markers", "trailing_newline", "compute_hunk_ranges"]
    assert "*** End of File" not in fixed and providers.validate_diff_structure(fixed) == []
    assert "     int b = 2;" in fixed and "     int d = 4;" in fixed   # context taken from the real source


def test_rangeless_hunk_is_left_invalid_when_it_cannot_be_placed_uniquely():
    dup = "x;\nx;\n"
    diff = f"--- a/{SRC_PATH}\n+++ b/{SRC_PATH}\n@@\n-x;\n+y;\n"
    for sources in ({SRC_PATH: dup}, {}, {SRC_PATH: "nothing matches\n"}):
        fixed, rules = providers.normalize_diff(diff, {SRC_PATH}, sources)
        assert "compute_hunk_ranges" not in rules and providers.validate_diff_structure(fixed) != []


def test_full_apply_patch_format_is_converted_and_end_of_file_context_is_real():
    """gpt-oss-120b on F01: '*** Begin Patch / *** Update File: <path> / @@ / ... / *** End Patch', replacing the
    last method of the file. Context must never include the phantom line after the final newline."""
    diff = (f"*** Begin Patch\n*** Update File: {SRC_PATH}\n@@\n-    int d = 4;\n-}}\n+    int d = 40;\n+}}\n"
            "*** End Patch")
    fixed, rules = providers.normalize_diff(diff, set(), {SRC_PATH: SRC})
    assert rules[:2] == ["apply_patch_file_headers", "drop_patch_markers"] and "compute_hunk_ranges" in rules
    assert fixed.startswith(f"--- a/{SRC_PATH}\n+++ b/{SRC_PATH}\n") and providers.validate_diff_structure(fixed) == []
    assert "@@ -2,5 +2,5 @@" in fixed            # 3 context lines + lines 5-6 of a 6-line file: no phantom line 7
