"""BeGuardit Recon (bg-recon) Hermes plugin backend — mounted at /api/plugins/bg-recon/.
Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Surfaces:
  POST /scan     TCP connect scan + banner grab. Targets are restricted to
                 private/loopback addresses unless the caller passes
                 ``allow_external: true`` (explicit authorization acknowledgment).
  GET  /posture  Local host posture audit: TCP listeners, LAN-exposure flags,
                 AI-runtime identification, sensitive-file permission checks.
  GET  /health   Liveness for the desktop pane.

Core logic is stdlib-only so the module can be exercised directly in tests;
fastapi is imported lazily only to build the router.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

MAX_PORTS = 2048
DEFAULT_TIMEOUT_S = 0.4
MAX_WORKERS = 512
LSOF = "/usr/sbin/lsof"

# Ports scanned when the caller does not specify a set (well-known + common
# dev/infra/AI-serving ports).
TOP_PORTS: list[int] = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 465, 587, 631,
    993, 995, 1080, 1234, 1433, 1521, 2049, 2375, 2376, 3000, 3306, 3389, 4444,
    5000, 5432, 5555, 5900, 6379, 7860, 8000, 8008, 8080, 8081, 8443, 8888,
    9000, 9090, 9200, 11211, 11434, 27017, 50000,
]

SERVICE_NAMES: dict[int, str] = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http",
    110: "pop3", 111: "rpcbind", 135: "msrpc", 139: "netbios-ssn", 143: "imap",
    443: "https", 445: "smb", 465: "smtps", 587: "submission", 631: "ipp",
    993: "imaps", 995: "pop3s", 1080: "socks", 1234: "lm-studio",
    1433: "mssql", 1521: "oracle", 2049: "nfs", 2375: "docker-api",
    2376: "docker-tls", 3000: "http-dev", 3306: "mysql", 3389: "rdp",
    4444: "metasploit-default", 5000: "http-alt/flask", 5432: "postgres",
    5555: "adb", 5900: "vnc", 6379: "redis", 7860: "gradio", 8000: "http-alt",
    8008: "http-alt", 8080: "http-proxy", 8081: "http-alt", 8443: "https-alt",
    8888: "jupyter", 9000: "http-alt", 9090: "prometheus",
    9200: "elasticsearch", 11211: "memcached", 11434: "ollama",
    27017: "mongodb", 50000: "db2",
}

AI_RUNTIMES: dict[int, str] = {
    11434: "Ollama",
    1234: "LM Studio",
    7860: "Gradio",
    8000: "vLLM/uvicorn",
    8888: "Jupyter",
    3000: "Node dev server",
    5173: "Vite dev server",
}

# Files whose permissions matter: group/other readable secrets are findings.
SENSITIVE_PATHS: list[str] = [
    ".ssh",
    ".ssh/authorized_keys",
    ".ssh/id_dsa", ".ssh/id_ecdsa", ".ssh/id_ed25519", ".ssh/id_rsa",
    ".ssh/known_hosts",
    ".aws/credentials",
    ".kube/config",
    ".netrc",
    ".config/gcloud/application_default_credentials.json",
    ".docker/config.json",
    ".local/share/opencode/auth.json",
    ".hermes/auth.json",
    ".hermes/config.yaml",
]

_PARSE_PORT_RE = re.compile(r"^\d+$")


def parse_port_spec(spec: str | None) -> list[int]:
    """Parse "80,443,8000-8100" / "top" into a deduped, capped, sorted port list."""
    if not spec or spec.strip().lower() in ("", "top", "default"):
        return sorted(set(TOP_PORTS))
    ports: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo_s, _, hi_s = chunk.partition("-")
            if not (lo_s.isdigit() and hi_s.isdigit()):
                raise ValueError(f"bad port range: {chunk!r}")
            lo, hi = int(lo_s), int(hi_s)
            if not (0 < lo <= 65535 and 0 < hi <= 65535 and lo <= hi):
                raise ValueError(f"bad port range: {chunk!r}")
            ports.update(range(lo, hi + 1))
        elif _PARSE_PORT_RE.match(chunk):
            port = int(chunk)
            if not 0 < port <= 65535:
                raise ValueError(f"bad port: {chunk!r}")
            ports.add(port)
        else:
            raise ValueError(f"bad port token: {chunk!r}")
    if len(ports) > MAX_PORTS:
        raise ValueError(f"too many ports ({len(ports)}); cap is {MAX_PORTS}")
    return sorted(ports)


def resolve_target(target: str) -> tuple[list[str], str | None]:
    """Resolve a host to IP addresses. Returns (ips, error)."""
    target = target.strip().strip("[]")
    if target.startswith("http://") or target.startswith("https://"):
        target = re.sub(r"^[a-z]+://", "", target, flags=re.IGNORECASE).split("/")[0]
        target = target.split(":")[0]
    if not target:
        return [], "empty target"
    try:
        infos = socket.getaddrinfo(target, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return [], f"cannot resolve {target!r}: {exc}"
    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips, None


def _is_local_scope(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private


def authorization(target: str, allow_external: bool) -> dict[str, Any]:
    """Enforce the authorized-scope policy: private/loopback by default.

    Public targets require an explicit ``allow_external: true`` — the caller's
    acknowledgment that it owns or has written scope for the target.
    """
    ips, err = resolve_target(target)
    if err:
        return {"allowed": False, "reason": err}
    if not ips:
        return {"allowed": False, "reason": "no addresses resolved"}
    if all(_is_local_scope(ip) for ip in ips):
        return {"allowed": True, "reason": "private/loopback target", "resolved": ips}
    if allow_external:
        return {
            "allowed": True,
            "reason": "allow_external acknowledged by caller",
            "resolved": ips,
        }
    return {
        "allowed": False,
        "reason": (
            f"{target} resolves to public address(es) {', '.join(ips)}; pass "
            "allow_external=true only for systems you own or are authorized to test"
        ),
        "resolved": ips,
    }


def _grab_banner(sock: socket.socket) -> str:
    try:
        sock.settimeout(0.6)
        data = sock.recv(256)
        printable = "".join(chr(b) if 32 <= b < 127 or b in (9, 10) else "." for b in data)
        return printable.strip()[:200]
    except OSError:
        return ""


def _probe_port(ip: str, port: int, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {"port": port, "service": SERVICE_NAMES.get(port, "")}
    start = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            result["state"] = "open"
            result["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
            banner = _grab_banner(sock)
            if banner:
                result["banner"] = banner
    except ConnectionRefusedError:
        result["state"] = "closed"
    except (socket.timeout, TimeoutError):
        result["state"] = "filtered"
    except OSError as exc:
        result["state"] = "error"
        result["error"] = str(exc)
    return result


def scan_target(
    target: str,
    ports: list[int],
    timeout: float = DEFAULT_TIMEOUT_S,
    max_workers: int = 256,
) -> dict[str, Any]:
    """TCP connect scan one resolved IP; returns a serializable report."""
    workers = max(1, min(int(max_workers), MAX_WORKERS))
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: _probe_port(target, p, timeout), ports))
    open_rows = [r for r in results if r.get("state") == "open"]
    return {
        "target": target,
        "scanned": len(results),
        "open": open_rows,
        "open_count": len(open_rows),
        "closed_count": sum(1 for r in results if r.get("state") == "closed"),
        "filtered_count": sum(1 for r in results if r.get("state") == "filtered"),
        "error_count": sum(1 for r in results if r.get("state") == "error"),
        "duration_ms": round((time.monotonic() - start) * 1000, 1),
    }


def listeners() -> list[dict[str, Any]]:
    """Parse `lsof -nP -iTCP -sTCP:LISTEN` into listener rows (macOS)."""
    try:
        proc = subprocess.run(
            [LSOF, "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [{"error": f"lsof failed: {exc}"}]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for line in proc.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 9:
            continue
        name = fields[-2] if fields[-1] == "(LISTEN)" else fields[-1]
        if name == "(LISTEN)":
            continue
        host, _, port_s = name.rpartition(":")
        if not port_s.isdigit():
            continue
        port = int(port_s)
        process, pid_s, user = fields[0], fields[1], fields[2]
        key = (process, port, host)
        if key in seen:
            continue
        seen.add(key)
        loopback = host in ("127.0.0.1", "::1", "localhost") or host == "*"
        # '*' means all interfaces → reachable from the LAN.
        exposed = host == "*" or not loopback
        rows.append({
            "process": process,
            "pid": pid_s,
            "user": user,
            "addr": host,
            "port": port,
            "service": SERVICE_NAMES.get(port, ""),
            "exposed": exposed,
            "ai_runtime": AI_RUNTIMES.get(port),
        })
    rows.sort(key=lambda r: (not r.get("exposed", False), r.get("port", 0)))
    return rows


def secrets_findings() -> list[dict[str, Any]]:
    """Flag sensitive files readable by group/other, and SSH dirs wider than 0700."""
    findings: list[dict[str, Any]] = []
    home = Path.home()
    for rel in SENSITIVE_PATHS:
        path = home / rel
        if not path.exists():
            continue
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            continue
        wide = mode & 0o077
        if wide:
            findings.append({
                "path": str(path),
                "mode": oct(mode),
                "issue": "readable beyond owner" if path.is_file() else "wider than 0700",
            })
    return findings


def posture() -> dict[str, Any]:
    """Local posture audit: listeners, exposure, AI runtimes, secrets perms."""
    rows = listeners()
    real_rows = [r for r in rows if "error" not in r]
    exposed = [r for r in real_rows if r.get("exposed")]
    host = socket.gethostname()
    ai = [
        {"port": r["port"], "runtime": r["ai_runtime"], "addr": r["addr"], "process": r["process"]}
        for r in real_rows if r.get("ai_runtime")
    ]
    secrets = secrets_findings()
    return {
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "listeners": real_rows,
        "listener_errors": [r["error"] for r in rows if "error" in r],
        "host": host,
        "exposed_count": len(exposed),
        "exposed": exposed,
        "ai_runtimes": ai,
        "secrets_findings": secrets,
        "summary": (
            f"{len(real_rows)} listeners, {len(exposed)} LAN-exposed, "
            f"{len(ai)} AI runtime(s), {len(secrets)} secrets permission finding(s)"
        ),
    }


# ---------------------------------------------------------------- router ----

def build_router():
    """Build the FastAPI router (lazy import: core logic runs without fastapi)."""
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "plugin": "bg-recon", "author": "Parth Patel, founder of BenchBrex.com"}

    @router.post("/scan")
    def scan(payload: dict[str, Any]) -> dict[str, Any]:
        target = str(payload.get("target", "")).strip()
        if not target:
            return {"error": "target is required"}
        try:
            ports = parse_port_spec(payload.get("ports"))
        except ValueError as exc:
            return {"error": str(exc)}
        auth = authorization(target, bool(payload.get("allow_external")))
        if not auth.get("allowed"):
            return {"error": "unauthorized target", "detail": auth.get("reason")}
        try:
            timeout_ms = int(payload.get("timeout_ms", DEFAULT_TIMEOUT_S * 1000))
        except (TypeError, ValueError):
            return {"error": "timeout_ms must be an integer"}
        timeout = min(max(timeout_ms, 50), 2000) / 1000.0
        report = scan_target(
            auth["resolved"][0], ports, timeout=timeout,
            max_workers=int(payload.get("max_workers", 256)),
        )
        report["authorization"] = auth
        return report

    @router.get("/posture")
    def get_posture() -> dict[str, Any]:
        return posture()

    return router


try:  # gateway/dashboard runtime has fastapi; bare test runs may not
    router = build_router()
except ImportError:  # pragma: no cover
    router = None


# ---------------------------------------------------------------------------
# v2: posture baseline, diff and HTML report (created by Parth Patel, founder
# of BenchBrex.com (BeGuardit / BenchBrex)).
# ---------------------------------------------------------------------------

BASELINE_PATH = Path(__file__).resolve().parent.parent / "state" / "baseline.json"


def _snapshot() -> dict[str, Any]:
    """Compact machine-comparable snapshot of the current posture."""
    snap = posture()
    listeners = [
        {"port": l["port"], "bound": l.get("bound", ""), "process": l.get("process", ""),
         "exposed": bool(l.get("exposed"))}
        for l in snap.get("listeners", [])
    ]
    listeners.sort(key=lambda d: (d["port"], d["bound"]))
    return {"taken_at": snap.get("taken_at", ""), "listeners": listeners}


def baseline_save() -> dict[str, Any]:
    """Persist the current posture as the comparison baseline."""
    snap = _snapshot()
    snap["host"] = socket.gethostname()
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(snap, indent=1) + "\n")
    return {"saved": str(BASELINE_PATH), "listeners": len(snap["listeners"])}


def baseline_diff() -> dict[str, Any]:
    """Diff current posture against the saved baseline (new/gone/changed)."""
    if not BASELINE_PATH.exists():
        return {"error": "no baseline saved yet - run baseline_save() first"}
    base = json.loads(BASELINE_PATH.read_text())
    now = _snapshot()

    def key(l):
        return (l["port"], l["bound"], l["exposed"])

    bset, nset = {key(l) for l in base["listeners"]}, {key(l) for l in now["listeners"]}
    added = [l for l in now["listeners"] if key(l) not in bset]
    removed = [l for l in base["listeners"] if key(l) not in nset]
    new_exposed = [l for l in added if l["exposed"]]
    verdict = "clean - no changes"
    if added or removed:
        verdict = str(len(added)) + " added, " + str(len(removed)) + " removed"
        if new_exposed:
            verdict += ", " + str(len(new_exposed)) + " NEW LAN-EXPOSED"
    return {"baseline_taken_at": base["taken_at"], "diff_taken_at": now["taken_at"],
            "unchanged": len(nset & bset), "added": added, "removed": removed,
            "new_lan_exposed": new_exposed, "verdict": verdict}


def report_html(path: str | None = None) -> str:
    """One-page HTML posture report (BeGuardit assessment style)."""
    snap = posture()
    trs = []
    exposed = 0
    for l in snap.get("listeners", []):
        is_exposed = bool(l.get("exposed"))
        if is_exposed:
            exposed += 1
        cls = "risk" if is_exposed else "ok"
        label = "LAN-exposed" if is_exposed else "loopback-only"
        trs.append("<tr><td>" + str(l.get("port")) + "</td><td>"
                   + str(l.get("process", "")) + "</td><td>" + str(l.get("bound", ""))
                   + '</td><td class="' + cls + '">' + label + "</td></tr>")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>BeGuardit Posture Report</title><style>"
            "body{font-family:-apple-system,Helvetica,Arial,sans-serif;margin:2rem;max-width:820px;color:#1a1a2e}"
            "h1{font-size:1.4rem;border-bottom:3px solid #16213e;padding-bottom:.4rem}"
            "table{border-collapse:collapse;width:100%;margin:1rem 0}"
            "th,td{border:1px solid #ccd;padding:.45rem .6rem;text-align:left;font-size:.85rem}"
            "th{background:#16213e;color:#fff}.risk{color:#b00020;font-weight:600}.ok{color:#1b5e20}"
            ".meta{color:#555;font-size:.8rem}"
            ".foot{margin-top:2rem;color:#777;font-size:.75rem;border-top:1px solid #ddd;padding-top:.6rem}"
            "</style></head><body>"
            "<h1>BeGuardit Posture Assessment - " + str(snap.get("host", "localhost")) + "</h1>"
            "<p class='meta'>Generated " + str(snap.get("taken_at", "")) + " - "
            + str(len(snap.get("listeners", []))) + " listeners, " + str(exposed) + " LAN-exposed</p>"
            "<table><tr><th>Port</th><th>Process</th><th>Bound to</th><th>Exposure</th></tr>"
            + "".join(trs) + "</table>"
            "<p><b>Findings:</b> " + str(exposed) + " service(s) reachable from the local network. "
            "Review each against the owner allow-list; loopback-only services need no action.</p>"
            "<div class='foot'>Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).<br>"
            "CONFIDENTIAL - authorized posture assessment of an owned host.</div></body></html>")
    out = Path(path) if path else BASELINE_PATH.parent / "posture_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return str(out)


if __name__ == "__main__":
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="BG Recon posture CLI")
    ap.add_argument("action", choices=["posture", "baseline-save", "baseline-diff", "report"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.action == "posture":
        print(_json.dumps(posture(), indent=1))
    elif a.action == "baseline-save":
        print(_json.dumps(baseline_save(), indent=1))
    elif a.action == "baseline-diff":
        print(_json.dumps(baseline_diff(), indent=1))
    else:
        print(report_html(a.out))
