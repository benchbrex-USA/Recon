#!/usr/bin/env python3
"""BG Lab — DVWA exploit scripts runner + lab manager.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Manages the local lab targets (Docker) and dispatches the exploit scripts.
Every target goes through the authorization gate in check_target.py.

Usage:
  python3 lab.py up                    # start DVWA + Juice Shop containers
  python3 lab.py status                # what's running, where
  python3 lab.py down                  # stop lab containers
  python3 lab.py sqli [--target 127.0.0.1:8081]   # DVWA SQL injection dump
  python3 lab.py cmdi [--target 127.0.0.1:8081]   # DVWA command injection
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from check_target import assert_authorized  # noqa: E402

CONTAINERS = {
    "dvwa": {
        "image": "vulnerables/web-dvwa",
        "name": "bg-dvwa",
        "port": ("8081", "80"),
        "platform": "linux/amd64",
    },
    "juice": {
        "image": "bkimminich/juice-shop",
        "name": "bg-juice",
        "port": ("3001", "3000"),
        "platform": None,
    },
}


def sh(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=capture, text=True)


def docker_running() -> bool:
    return sh(["docker", "info"]).returncode == 0


def ensure_docker_daemon() -> bool:
    """Docker Desktop is not installed here — the daemon is colima. Start it if down."""
    if docker_running():
        return True
    import shutil

    colima = shutil.which("colima")
    if colima:
        print("[docker] daemon down — starting colima (this can take a minute)…")
        start = sh([colima, "start"], capture=True)
        if docker_running():
            return True
        print(f"[docker] colima start failed: {(start.stderr or start.stdout).strip()[-200:]}")
    return False


def container_up(name: str) -> bool:
    out = sh(["docker", "ps", "--format", "{{.Names}}"]).stdout
    return name in out.split()


def cmd_up(args: argparse.Namespace) -> int:
    if not ensure_docker_daemon():
        print("docker daemon not running and colima could not start it")
        return 1
    for key, spec in CONTAINERS.items():
        if not container_up(spec["name"]):
            exists = sh(["docker", "ps", "-a", "--format", "{{.Names}}"]).stdout
            if spec["name"] in exists.split():
                sh(["docker", "start", spec["name"]])
                print(f"[{key}] started existing container")
            else:
                print(f"[{key}] pulling {spec['image']} (first run only)…")
                pull = sh(["docker", "pull", *([f"--platform={spec['platform']}"] if spec["platform"] else []), spec["image"]])
                if pull.returncode != 0:
                    print(f"[{key}] pull failed: {pull.stderr.strip()[:200]}")
                    return 1
                run = sh([
                    "docker", "run", "-d",
                    *([f"--platform={spec['platform']}"] if spec["platform"] else []),
                    "--name", spec["name"],
                    "-p", f"{spec['port'][0]}:{spec['port'][1]}",
                    spec["image"],
                ])
                if run.returncode != 0:
                    print(f"[{key}] run failed: {run.stderr.strip()[:200]}")
                    return 1
        else:
            print(f"[{key}] container already running")
        _wait_http(f"http://127.0.0.1:{spec['port'][0]}")
        if key == "dvwa":
            ensure_dvwa_db(f"http://127.0.0.1:{spec['port'][0]}")
        print(f"[{key}] ready: http://127.0.0.1:{spec['port'][0]}")
    return 0


def _wait_http(url: str, tries: int = 30, delay: float = 2.0) -> bool:
    import urllib.request

    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    return True
        except Exception:
            time.sleep(delay)
    return False


def ensure_dvwa_db(base: str) -> bool:
    """Initialize (or reset) DVWA's database via setup.php. Idempotent.

    A fresh container has no `users` table — login.php just redirects to
    setup.php until this runs once.
    """
    import re
    from exploits.dvwa_sqli import _request

    status, html, setc = _request(f"{base}/setup.php")
    m = re.search(r"name=['\"]user_token['\"]\s+value=['\"]([0-9a-f]{32})['\"]", html, re.I)
    sid = next((p for p in setc.split("; ") if p.startswith("PHPSESSID=")), "")
    if not m or not sid:
        print(f"[dvwa] setup page unreadable (status {status})")
        return False
    status, html, _ = _request(
        f"{base}/setup.php",
        data={"create_db": "Create / Reset Database", "user_token": m.group(1)},
        cookie=sid,
    )
    ok = "Database has been created" in html or "setup successful" in html.lower() or status == 200
    print(f"[dvwa] database initialized (status {status})" if ok else f"[dvwa] setup response unclear (status {status}) — continuing")
    return ok


def cmd_status(_: argparse.Namespace) -> int:
    if not docker_running():
        print("docker daemon not running (colima stopped?) — `python3 lab.py up` starts it")
        return 1
    out = sh(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"]).stdout
    for key, spec in CONTAINERS.items():
        row = next((line for line in out.splitlines() if line.startswith(spec["name"])), None)
        print(f"[{key}] {row if row else 'not running'}")
    return 0


def cmd_down(_: argparse.Namespace) -> int:
    for key, spec in CONTAINERS.items():
        if container_up(spec["name"]):
            sh(["docker", "stop", spec["name"]])
            print(f"[{key}] stopped")
        else:
            print(f"[{key}] not running")
    return 0


def cmd_sqli(args: argparse.Namespace) -> int:
    ips = assert_authorized(args.target.split(":")[0], args.allow_external)
    print(f"target authorized: {args.target} -> {ips}")
    from exploits.dvwa_sqli import run
    return run(args.target, user=args.user, password=args.password, level=args.level)


def cmd_cmdi(args: argparse.Namespace) -> int:
    ips = assert_authorized(args.target.split(":")[0], args.allow_external)
    print(f"target authorized: {args.target} -> {ips}")
    from exploits.dvwa_cmdi import run
    return run(args.target, user=args.user, password=args.password, level=args.level)


def main() -> int:
    ap = argparse.ArgumentParser(description="BG Lab — local CTF lab manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("up").set_defaults(func=cmd_up)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("down").set_defaults(func=cmd_down)

    for name, func in (("sqli", cmd_sqli), ("cmdi", cmd_cmdi)):
        p = sub.add_parser(name)
        p.add_argument("--target", default="127.0.0.1:8081")
        p.add_argument("--user", default="admin")
        p.add_argument("--password", default="password")
        p.add_argument("--level", default="low", choices=["low", "medium", "high"])
        p.add_argument("--allow-external", action="store_true")
        p.set_defaults(func=func)

    args = ap.parse_args()
    print("BG Lab — created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex)")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
