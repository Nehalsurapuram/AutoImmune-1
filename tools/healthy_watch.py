"""A2 false-alarm check: run the real detector against the HEALTHY baseline under steady load.

    python tools/healthy_watch.py --seconds 300 --rps 20

Starts tools/load.py (default mix: normal requests plus 10% customer-less searches that a healthy app answers 400) in the background, runs detector.watch() for --seconds,
and writes runs/healthy-watch-<stamp>/healthy_watch.json:
  result "no_incident"  -> the detector stayed quiet for the whole window (what A2 requires)
  result "incident"     -> a false alarm; the incident is saved next to it
  result "invalid"      -> the baseline was not running/healthy, or the detector reported an invalid window
A missing or failed check is never reported as "no_incident".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pipeline import deploy, detector, provenance  # noqa: E402


def verdict(incident: dict | None, baseline_ok: bool) -> str:
    if not baseline_ok:
        return "invalid"
    if incident is None:
        return "no_incident"
    return "invalid" if incident.get("status") == "invalid" else "incident"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--rps", type=float, default=20)
    a = ap.parse_args(argv)
    cfg = deploy.load_config()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"healthy-watch-{stamp.lower()}"
    out = REPO / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    image = deploy.current_image()
    baseline_ok = image == deploy.BASELINE_TAG and deploy._health(cfg)["ok"]
    record = {"run_id": run_id, "started_at": stamp, "image": image, "baseline_healthy_at_start": baseline_ok,
              "window_s": a.seconds, "rps": a.rps, "load": "tools/load.py default mix, incl. 10% searches without a customer (healthy answer: HTTP 400)",
              "provenance": provenance.collect(cfg)}
    incident, load_out = None, ""
    if baseline_ok:
        load = subprocess.Popen([sys.executable, str(REPO / "tools" / "load.py"), "--seconds", str(a.seconds + 20),
                                 "--rps", str(a.rps)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(5)   # let traffic start before the first metrics window
        t0 = time.monotonic()
        incident = detector.watch(a.seconds, run_id=run_id,
                                  on_check=lambda obs, fired: print(f"  +{time.monotonic() - t0:5.0f}s  "
                                                                    f"{'FIRED: ' + str(fired) if fired else 'ok'}",
                                                                    flush=True))
        record["watched_s"] = round(time.monotonic() - t0, 1)
        load.terminate()
        try:
            load_out = load.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            load.kill()
            load_out = "(load generator did not exit cleanly)"
    record.update(result=verdict(incident, baseline_ok), incident=incident,
                  load_summary=load_out.strip().splitlines()[-3:] if load_out else [],
                  ended_at=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    (out / "healthy_watch.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    print(f"\nRESULT: {record['result']}  ({record.get('watched_s', 0)} s watched)  -> runs/{run_id}/healthy_watch.json")
    return 0 if record["result"] == "no_incident" else 1


if __name__ == "__main__":
    raise SystemExit(main())
