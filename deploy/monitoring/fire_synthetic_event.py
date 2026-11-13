# Phase 7 – C3 Step 5: write ONE synthetic llm_run log entry (a hallucination) to prove alert A1 really fires.
# It uses the same resource + payload shape as a real Cloud Run event, so it flows through the same log-based
# metrics. It's clearly labeled: trace_id "synthetic-…" (excluded from BigQuery views and promote.py),
# prompt_version "synthetic" (distinguishable on the dashboard), and a SYNTHETIC message.
#
#   python deploy/monitoring/fire_synthetic_event.py <project>

import datetime
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid


def main(project: str) -> None:
    gcloud = shutil.which("gcloud")
    token = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, check=True).stdout.strip()
    trace_id = f"synthetic-{uuid.uuid4()}"
    entry = {
        "logName": f"projects/{project}/logs/" + urllib.parse.quote("run.googleapis.com/stdout", safe=""),
        "resource": {"type": "cloud_run_revision", "labels": {
            "project_id": project, "service_name": "agentsville-trip-planner", "revision_name": "synthetic-alert-test",
            "configuration_name": "agentsville-trip-planner", "location": "asia-south1"}},
        "severity": "WARNING",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "jsonPayload": {
            "app": "agentsville", "event": "llm_run", "schema_version": "1", "source": "prod",
            "message": "SYNTHETIC ALERT TEST (Phase 7 – C3): fake hallucination to verify alert A1 – not a real run",
            "trace_id": trace_id, "prompt_version": "synthetic", "model": "gpt-4.1-mini",
            "latency_ms": 1000.0, "prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.000001,
            "parsed": True, "error": None, "task_success": False, "hallucination": True,
            "hard_failed": ["activity_exists"], "graders": [], "raw_response": None,
        },
    }
    req = urllib.request.Request("https://logging.googleapis.com/v2/entries:write", method="POST",
                                 data=json.dumps({"entries": [entry]}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()
    print(f"wrote synthetic event trace_id={trace_id} at {entry['timestamp']}")


if __name__ == "__main__":
    main(sys.argv[1])
