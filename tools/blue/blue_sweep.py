#!/usr/bin/env python3
# Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
"""Blue sweep — endpoint change detection for the owned Mac + BeGuardit toolchain.

Replaces 'what changed since the last known-good state' across five surfaces:
  listeners (osquery), launchd jobs (osquery), user accounts (osquery),
  crontab (osquery), and toolchain file integrity (sha256).

Usage:
  blue_sweep.py --baseline-save     # record current state as known-good
  blue_sweep.py                     # diff now vs baseline; silent when clean, exit 1 on new findings
  blue_sweep.py --json              # always print the full report JSON

Silent-when-clean matches the web_watchdog convention: the cron delivers
nothing unless there is something to say. Findings never print secrets.
"""
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

AUTHOR = "Created by Parth Patel, founder of BenchBrex.com"
HERE = Path(__file__).resolve().parent
VOL = HERE.parent.parent  # /Volumes/Parth Patel/BeGuardit Hacking Tools
OSQUERYI = HERE / "osquery" / "bin" / "osqueryi"
STATE_DIR = HERE / "state"
BASELINE = STATE_DIR / "blue-baseline.json"
LAST_RUN = STATE_DIR / "blue-last-run.json"

# Loopback service ports that are expected to exist. A non-loopback bind of
# any of these is still a finding (LAN exposure), matching bgx posture logic.
EXPECTED_LOOPBACK_PORTS = {8001, 8002, 8081}

# IANA ephemeral range. System daemons (sharingd, identityservicesd, awdl…)
# open transient sockets here that move constantly — tracking them produces
# nothing but noise, so they are excluded from the diff. Real services bind
# below this range.
EPHEMERAL_MIN = 49152

# Toolchain integrity set — code and security-relevant docs, not evidence state.
INTEGRITY_FILES = [
    "tools/bg",
    "bg-recon-plugin/dashboard/plugin_api.py",
    "bg-redteam/harness.py",
    "bg-lab/lab.py",
    "sable-01/serve.sh",
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "tools/blue/blue_sweep.py",
]


def osquery(sql: str):
    if not OSQUERYI.exists():
        raise FileNotFoundError(f"osqueryi missing at {OSQUERYI}")
    out = subprocess.run(
        [str(OSQUERYI), "-json", sql], capture_output=True, text=True, timeout=60
    )
    if out.returncode != 0:
        raise RuntimeError(f"osquery failed: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout or "[]")


def collect_listeners():
    rows = osquery(
        "SELECT DISTINCT lp.address AS address, lp.port AS port, "
        "coalesce(p.name, 'unknown') AS proc FROM listening_ports lp "
        "LEFT JOIN processes p ON lp.pid = p.pid WHERE lp.port != 0;"
    )
    items = []
    for r in rows:
        addr = (r.get("address") or "").strip()
        port = int(r["port"])
        if port >= EPHEMERAL_MIN:
            continue
        expected = port in EXPECTED_LOOPBACK_PORTS and addr in ("127.0.0.1", "::1")
        if expected:
            continue
        items.append(
            {"address": addr, "port": port, "proc": r.get("proc", "?"),
             "lan_exposed": addr in ("0.0.0.0", "::", "*") or (addr and not addr.startswith("127.") and addr != "::1")}
        )
    return {f"{i['address']}:{i['port']}:{i['proc']}": i for i in items}


def collect_launchd():
    rows = osquery("SELECT label, path FROM launchd WHERE path LIKE '/Library/Launch%' OR path LIKE '/System/Library/Launch%' OR path LIKE '/Users/%/Library/Launch%';")
    return {f"{r['label']}|{r['path']}": {"label": r["label"], "path": r["path"]} for r in rows}


def collect_users():
    rows = osquery("SELECT username, uid FROM users WHERE uid >= 500 AND username NOT LIKE '\\_%';")
    return {r["username"]: {"username": r["username"], "uid": int(r["uid"])} for r in rows}


def collect_crontab():
    rows = osquery("SELECT command FROM crontab;")
    return {r["command"]: {"command": r["command"]} for r in rows}


def collect_integrity():
    out = {}
    for rel in INTEGRITY_FILES:
        p = VOL / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[rel] = "MISSING"
    return out


def sweep():
    return {
        "listeners": collect_listeners(),
        "launchd": collect_launchd(),
        "users": collect_users(),
        "crontab": collect_crontab(),
        "integrity": collect_integrity(),
    }


def diff(now: dict, base: dict):
    findings = []
    for cat in ("listeners", "launchd", "users", "crontab"):
        base_keys = set(base.get(cat, {}) or {})
        for key in now[cat]:
            if key not in base_keys:
                findings.append({"category": cat, "kind": "NEW", "key": key, "detail": now[cat][key]})
    for rel, h in now["integrity"].items():
        bh = (base.get("integrity") or {}).get(rel)
        if bh is None:
            findings.append({"category": "integrity", "kind": "UNBASELINED", "key": rel, "detail": {"sha256": h}})
        elif h != bh:
            findings.append({"category": "integrity", "kind": "CHANGED" if h != "MISSING" else "MISSING",
                             "key": rel, "detail": {"was": bh[:16], "now": h[:16]}})
    return findings


def stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-save", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now = sweep()
    report = {
        "schema_version": 1,
        "author": AUTHOR,
        "observed_at": stamp(),
        "counts": {k: len(v) for k, v in now.items()},
    }

    if args.baseline_save:
        baseline = dict(now)
        baseline["schema_version"] = 1
        baseline["author"] = AUTHOR
        baseline["saved_at"] = stamp()
        BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True))
        report["action"] = "baseline-saved"
        report["findings"] = []
        LAST_RUN.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"blue-sweep: baseline saved — "
              f"{report['counts']['listeners']} listeners, {report['counts']['launchd']} launchd jobs, "
              f"{report['counts']['users']} users, {report['counts']['crontab']} crontabs, "
              f"{report['counts']['integrity']} integrity files")
        return 0

    if not BASELINE.exists():
        print("blue-sweep: no baseline. Run once with --baseline-save.", file=sys.stderr)
        return 2

    base = json.loads(BASELINE.read_text())
    findings = diff(now, base)
    report["action"] = "diff"
    report["findings"] = findings
    LAST_RUN.write_text(json.dumps(report, indent=2, sort_keys=True))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if findings else 0

    if not findings:
        return 0  # silent when clean — cron convention

    lines = [f"blue-sweep: {len(findings)} new finding(s) at {report['observed_at']}"]
    for f in findings:
        if f["category"] == "listeners" and f["detail"].get("lan_exposed"):
            lines.append(f"  [LAN-EXPOSED] {f['key']}")
        elif f["category"] == "integrity":
            lines.append(f"  [{f['kind']}] {f['key']}")
        else:
            lines.append(f"  [{f['category']}] NEW {f['key']}")
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
