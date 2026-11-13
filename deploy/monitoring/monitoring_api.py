# Phase 7 – C3: minimal Cloud Monitoring REST client (notification channel + alert policies, create-or-update).
# Uses the REST API with the caller's gcloud token, because `gcloud alpha/beta monitoring` components need
# admin rights to install on Windows. Idempotent: matches existing resources by displayName.
#
#   python deploy/monitoring/monitoring_api.py channel  <project> <display name> <email>  → prints channel name
#   python deploy/monitoring/monitoring_api.py dashboard <project>
#   python deploy/monitoring/monitoring_api.py policies <project> <channel name>

import glob
import json
import shutil
import subprocess
import sys
import urllib.request

import yaml

API = "https://monitoring.googleapis.com/v3"


def token() -> str:
    gcloud = shutil.which("gcloud")
    return subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=True).stdout.strip()


def call(method: str, url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        sys.exit(f"{method} {url} failed: {err.code} {err.read().decode()[:800]}")


def list_all(url: str, key: str) -> list[dict]:
    items, page = [], ""
    while True:
        data = call("GET", url + (f"?pageToken={page}" if page else ""))
        items += data.get(key, [])
        page = data.get("nextPageToken", "")
        if not page:
            return items


def ensure_channel(project: str, display: str, email: str) -> str:
    for ch in list_all(f"{API}/projects/{project}/notificationChannels", "notificationChannels"):
        if ch.get("displayName") == display:
            return ch["name"]
    return call("POST", f"{API}/projects/{project}/notificationChannels",
                {"type": "email", "displayName": display, "labels": {"email_address": email},
                 "userLabels": {"app": "agentsville"}})["name"]


def ensure_dashboard(project: str) -> str:
    cfg = json.load(open("deploy/monitoring/dashboard.json", encoding="utf-8"))
    base = f"https://monitoring.googleapis.com/v1/projects/{project}/dashboards"
    for d in list_all(base, "dashboards"):
        if d.get("displayName") == cfg["displayName"]:
            cfg["etag"] = d["etag"]
            return call("PATCH", f"https://monitoring.googleapis.com/v1/{d['name']}", cfg)["name"]
    return call("POST", base, cfg)["name"]


def ensure_policies(project: str, channel: str) -> None:
    existing = {p["displayName"]: p["name"] for p in list_all(f"{API}/projects/{project}/alertPolicies", "alertPolicies")}
    for path in sorted(glob.glob("deploy/monitoring/alerts/*.yaml")):
        policy = yaml.safe_load(open(path, encoding="utf-8"))
        policy["notificationChannels"] = [channel]
        name = existing.get(policy["displayName"])
        if name:
            call("PATCH", f"{API}/{name}", policy)
            print("updated", policy["displayName"])
        else:
            call("POST", f"{API}/projects/{project}/alertPolicies", policy)
            print("created", policy["displayName"])


if __name__ == "__main__":
    cmd, project = sys.argv[1], sys.argv[2]
    if cmd == "channel":
        print(ensure_channel(project, sys.argv[3], sys.argv[4]))
    elif cmd == "dashboard":
        print(ensure_dashboard(project))
    elif cmd == "policies":
        ensure_policies(project, sys.argv[3])
    else:
        sys.exit(f"unknown command {cmd}")
