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
import shutil
import socket
import ssl
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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


# ---------------------------------------------------------------------------
# v2.2: authorized web posture (created by Parth Patel, founder of BenchBrex.com).
# Checks the defect class proved on an owned host: cleartext page, missing HSTS,
# session cookie set without Secure/HttpOnly. Does not log in, post, or store
# cookie values.
# ---------------------------------------------------------------------------

def parse_response_headers(raw: str) -> dict[str, Any]:
    """Parse a curl -D header block. Last HTTP status wins (proxy hops)."""
    status = None
    headers: dict[str, list[str]] = {}
    for line in raw.splitlines():
        if line.startswith("HTTP/"):
            parts = line.split()
            status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            headers = {}
        elif ":" in line:
            key, value = line.split(":", 1)
            headers.setdefault(key.strip().lower(), []).append(value.strip())
    return {"status": status, "headers": headers}


def inspect_set_cookie(value: str) -> dict[str, Any]:
    """Return cookie flags only. The value is never copied into the result."""
    pieces = [p.strip() for p in value.split(";") if p.strip()]
    name = pieces[0].split("=", 1)[0].strip() if pieces else ""
    attrs: dict[str, Any] = {}
    for piece in pieces[1:]:
        if "=" in piece:
            key, val = piece.split("=", 1)
            attrs[key.strip().lower()] = val.strip()
        else:
            attrs[piece.strip().lower()] = True
    samesite = attrs.get("samesite")
    return {
        "name": name,
        "secure": "secure" in attrs,
        "httponly": "httponly" in attrs,
        "samesite": samesite if isinstance(samesite, str) else None,
    }


def assess_probe(scheme: str, probe: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn one response into findings. Sources: RFC 6797 §8.1, MDN Set-Cookie."""
    findings: list[dict[str, Any]] = []
    headers = probe.get("headers") or {}
    status = probe.get("status")
    if scheme == "http" and status == 200 and not headers.get("location"):
        findings.append({
            "id": "http-no-redirect",
            "severity": "high",
            "detail": (
                "HTTP returned 200 with no Location. RFC 6797 §8.1: a browser "
                "notes HSTS only from a response received over a secure transport, "
                "so this response cannot start that policy."
            ),
        })
    if scheme == "https" and not headers.get("strict-transport-security"):
        findings.append({
            "id": "hsts-absent",
            "severity": "high",
            "detail": (
                "HTTPS response has no Strict-Transport-Security header "
                "(RFC 6797 §8.1)."
            ),
        })
    for flags in probe.get("cookies") or [inspect_set_cookie(raw) for raw in headers.get("set-cookie", [])]:
        if scheme == "http" and not flags["secure"]:
            findings.append({
                "id": "cookie-cleartext",
                "severity": "high",
                "detail": (
                    f"{flags['name']} was set on HTTP without Secure. "
                    "MDN Set-Cookie: without Secure the cookie is not limited "
                    "to secure requests."
                ),
                "cookie": flags,
            })
        if not flags["httponly"]:
            findings.append({
                "id": "cookie-not-httponly",
                "severity": "medium",
                "detail": (
                    f"{flags['name']} has no HttpOnly. MDN Set-Cookie: without "
                    "HttpOnly, page script can read the cookie."
                ),
                "cookie": flags,
            })
    powered = headers.get("x-powered-by")
    if powered:
        findings.append({
            "id": "version-disclosure",
            "severity": "low",
            "detail": "X-Powered-By is present: " + ", ".join(powered),
        })
    return findings


def _probe_url(url: str) -> dict[str, Any]:
    """Fetch response headers only. Does not follow redirects. Does not keep a body."""
    proc = subprocess.run(
        ["curl", "-sS", "-D", "-", "-o", "/dev/null", "--http1.1",
         "--max-time", "20", "--path-as-is", url],
        capture_output=True, text=True, timeout=25, check=False,
    )
    parsed = parse_response_headers(proc.stdout or "")
    parsed["url"] = url
    parsed["curl_exit"] = proc.returncode
    if proc.returncode != 0 and parsed["status"] is None:
        parsed["error"] = (proc.stderr or "").strip()[:200]
    # Drop raw Set-Cookie so a cookie value cannot leak into the report.
    raw_cookies = list((parsed["headers"] or {}).get("set-cookie", []))
    if parsed["headers"] and "set-cookie" in parsed["headers"]:
        parsed["headers"]["set-cookie"] = [
            inspect_set_cookie(item)["name"] + "=<redacted>" for item in raw_cookies
        ]
    parsed["cookies"] = [inspect_set_cookie(item) for item in raw_cookies]
    return parsed


def web_posture(target: str, allow_external: bool, path: str = "/") -> dict[str, Any]:
    """Authorized header posture of one owned host. GET only, two schemes, one path."""
    if not path.startswith("/"):
        path = "/" + path
    auth = authorization(target, allow_external)
    if not auth.get("allowed"):
        return {"error": "unauthorized target", "detail": auth.get("reason"), "authorization": auth}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            scheme: pool.submit(_probe_url, f"{scheme}://{target}{path}")
            for scheme in ("http", "https")
        }
        probes = []
        findings: list[dict[str, Any]] = []
        for scheme in ("http", "https"):
            probe = futures[scheme].result()
            probe["findings"] = assess_probe(scheme, probe)
            findings.extend(probe["findings"])
            probes.append(probe)
    high = [f for f in findings if f.get("severity") == "high"]
    return {
        "author": "Created by Parth Patel, founder of BenchBrex.com",
        "target": target,
        "path": path,
        "authorization": auth,
        "probes": probes,
        "findings": findings,
        "high_count": len(high),
        "verdict": "ATTENTION" if high else "NO HIGH FINDINGS",
    }


# ---------------------------------------------------------------------------
# v2.3: TLS posture, site map, web history (created by Parth Patel, founder of
# BenchBrex.com). All checks are GET-only and authorization-gated. No login,
# no POST, no credential attacks. TLS standards: RFC 8996 deprecates TLS
# 1.0/1.1; RFC 6797 §8.1 for HSTS; MDN Set-Cookie for cookie flags.
# ---------------------------------------------------------------------------

_TLS_PROBES = [
    ("TLSv1.0", ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1),
    ("TLSv1.1", ssl.TLSVersion.TLSv1_1, ssl.TLSVersion.TLSv1_1),
    ("TLSv1.2", ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2),
    ("TLSv1.3", ssl.TLSVersion.TLSv1_3, ssl.TLSVersion.TLSv1_3),
]


def days_remaining(notafter: str, now: datetime | None = None) -> int | None:
    """Days from `now` until an openssl notAfter string. None when unparseable."""
    text = notafter.strip()
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        reference = now or datetime.now().astimezone()
        return (parsed - reference).days
    return None


def classify_protocol_error(message: str) -> str:
    """Label a failed handshake honestly. Client limits are not server facts."""
    lowered = message.lower()
    if "no protocols available" in lowered or "unsupported protocol" in lowered:
        return "client-unsupported"
    if "alert" in lowered and "protocol version" in lowered:
        return "server-rejected"
    return "rejected"


def probe_tls_version(
    ip: str, port: int, servername: str,
    minimum: ssl.TLSVersion, maximum: ssl.TLSVersion, timeout: float = 6.0,
) -> dict[str, Any]:
    """Attempt one pinned-version handshake. Returns a state + raw error."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = minimum
        ctx.maximum_version = maximum
    except (ValueError, ssl.SSLError):
        return {"state": "client-unsupported", "error": "context refused version range"}
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=servername):
                return {"state": "accepted", "error": None}
    except ssl.SSLError as exc:
        return {"state": classify_protocol_error(str(exc)), "error": str(exc)[:140]}
    except (ConnectionRefusedError, socket.timeout, TimeoutError, OSError) as exc:
        return {"state": "unreachable", "error": str(exc)[:140]}


def fetch_certificate(
    ip: str, port: int, servername: str, timeout: float = 8.0,
) -> dict[str, Any]:
    """Leaf certificate fields. No chain validation here; verify is separate."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=servername) as tls:
                der = tls.getpeercert(binary_form=True)
    except (ssl.SSLError, OSError) as exc:
        return {"error": str(exc)[:140]}
    if not der:
        return {"error": "no certificate presented"}
    # LibreSSL needs -inform DER for binary stdin; -text works across LibreSSL/OpenSSL.
    proc = subprocess.run(
        ["openssl", "x509", "-inform", "DER", "-noout", "-text"],
        input=der, capture_output=True, timeout=10, check=False,
    )
    text = proc.stdout.decode("utf-8", "replace")
    fields: dict[str, Any] = {}
    subject = re.search(r"Subject:\s*(.+)", text)
    issuer = re.search(r"Issuer:\s*(.+)", text)
    not_before = re.search(r"Not Before:\s*(.+)", text)
    not_after = re.search(r"Not After\s*:\s*(.+)", text)
    if subject:
        fields["subject"] = subject.group(1).strip()
    if issuer:
        fields["issuer"] = issuer.group(1).strip()
    if not_before:
        fields["notBefore"] = not_before.group(1).strip()
    if not_after:
        fields["notAfter"] = not_after.group(1).strip()
    san = re.search(r"X509v3 Subject Alternative Name:\s*(?:critical)?\s*\n\s*(.+)", text)
    if san:
        fields["san"] = san.group(1).strip()
    fields["days_remaining"] = (
        days_remaining(fields.get("notAfter", "")) if fields.get("notAfter") else None
    )
    return fields


def verify_chain(ip: str, port: int, servername: str, timeout: float = 10.0) -> str | None:
    """openssl s_client verification line, e.g. 'Verify return code: 0 (ok)'."""
    try:
        proc = subprocess.run(
            ["openssl", "s_client", "-connect", f"{ip}:{port}",
             "-servername", servername],
            input=b"", capture_output=True, timeout=timeout, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    for line in (proc.stdout + proc.stderr).decode("utf-8", "replace").splitlines():
        if "Verify return code" in line:
            return line.strip()
    return None


def tls_posture(target: str, allow_external: bool, port: int = 443) -> dict[str, Any]:
    """Authorized TLS check of one owned host. Standards: RFC 8996, RFC 6797."""
    auth = authorization(target, allow_external)
    if not auth.get("allowed"):
        return {"error": "unauthorized target", "detail": auth.get("reason"), "authorization": auth}
    ip = auth["resolved"][0]
    cert = fetch_certificate(ip, port, target)
    chain = verify_chain(ip, port, target)
    versions = {}
    with ThreadPoolExecutor(max_workers=len(_TLS_PROBES)) as pool:
        futures = {
            name: pool.submit(probe_tls_version, ip, port, target, low, high)
            for name, low, high in _TLS_PROBES
        }
        versions = {name: fut.result() for name, fut in futures.items()}
    findings: list[dict[str, Any]] = []
    if cert.get("days_remaining") is not None:
        left = cert["days_remaining"]
        if left < 0:
            findings.append({"id": "cert-expired", "severity": "critical", "detail": f"expired {-left} days ago"})
        elif left < 30:
            findings.append({"id": "cert-expiring", "severity": "high", "detail": f"{left} days left"})
        elif left < 90:
            findings.append({"id": "cert-expiring-soon", "severity": "low", "detail": f"{left} days left"})
    if chain and "Verify return code" in chain:
        code_text = chain.split(":", 1)[1].strip()
        if not code_text.startswith("0 "):
            findings.append({"id": "chain-verify-failed", "severity": "high", "detail": chain})
    for name, probe in versions.items():
        if probe["state"] == "accepted" and name in ("TLSv1.0", "TLSv1.1"):
            findings.append({
                "id": "deprecated-tls",
                "severity": "high" if name == "TLSv1.0" else "medium",
                "detail": f"{name} accepted. RFC 8996 formally deprecates TLS 1.0 and 1.1.",
            })
    high = [f for f in findings if f["severity"] in ("high", "critical")]
    return {
        "author": "Created by Parth Patel, founder of BenchBrex.com",
        "target": target,
        "port": port,
        "authorization": auth,
        "certificate": cert,
        "chain": chain,
        "protocols": versions,
        "findings": findings,
        "high_count": len(high),
        "verdict": "ATTENTION" if high else "NO HIGH FINDINGS",
    }


# Bounded mistake-path list from live findings on owned hosts. GET-only.
MISTAKE_PATHS = [
    "/.env", "/.git/HEAD", "/.git/config", "/.htaccess", "/.htpasswd",
    "/backup.zip", "/www.zip", "/site.zip", "/backup.tar.gz",
    "/phpinfo.php", "/info.php", "/server-status", "/cgi-bin/",
    "/cpanel", "/wp-login.php", "/phpmyadmin/", "/admin",
]


def _fetch_page(url: str, max_bytes: int = 200_000) -> dict[str, Any]:
    """GET one page. No redirects followed, no cookies, no POST."""
    proc = subprocess.run(
        ["curl", "-sS", "-D", "-", "-o", "-", "--http1.1", "--max-time", "15",
         "--path-as-is", "--max-filesize", str(max_bytes), url],
        capture_output=True, timeout=20, check=False,
    )
    raw = proc.stdout
    sep = raw.find(b"\r\n\r\n")
    if sep < 0:
        return {"url": url, "status": None, "error": (proc.stderr or "")[:140]}
    parsed = parse_response_headers(raw[:sep].decode("latin1"))
    parsed["url"] = url
    parsed["body"] = raw[sep + 4:]
    return parsed


def extract_links(html: str, base_url: str) -> list[str]:
    """Same-host href/src/action links, absolutized. Nothing else."""
    from urllib.parse import urljoin, urlparse
    base = urlparse(base_url)
    host = (base.hostname or "").lower()
    links: list[str] = []
    for match in re.findall(r"(?:href|src|action)=[\"']([^\"'#\s]+)", html, re.I):
        ref = match.strip()
        if ref.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = urljoin(base_url, ref)
        parsed = urlparse(absolute)
        if (parsed.hostname or "").lower() != host or parsed.scheme not in ("http", "https"):
            continue
        links.append(parsed.scheme + "://" + parsed.netloc + parsed.path)
    return links


def site_map(target: str, allow_external: bool, max_requests: int = 80) -> dict[str, Any]:
    """Authorized inventory of one owned site: sitemap, links, mistake paths.

    Sequential on purpose: this class of host is shared, and a parallel burst
    tripped its connection limit during a live engagement.
    """
    auth = authorization(target, allow_external)
    if not auth.get("allowed"):
        return {"error": "unauthorized target", "detail": auth.get("reason"), "authorization": auth}
    budget = {"left": max_requests}
    results: dict[str, dict[str, Any]] = {}

    def get(path: str) -> dict[str, Any] | None:
        if budget["left"] <= 0:
            return None
        budget["left"] -= 1
        if path not in results:
            results[path] = _fetch_page(f"http://{target}{path}")
        return results[path]

    home = get("/")
    html = (home.get("body") or b"").decode("utf-8", "replace")
    queue = list(dict.fromkeys(
        [urlparse(link).path or "/" for link in extract_links(html, f"http://{target}/")]
    ))[:40]
    sitemap = get("/sitemap.xml")
    if sitemap and sitemap.get("status") == 200:
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap.get("body", b"").decode("utf-8", "replace"))
        queue = list(dict.fromkeys(queue + [
            urlparse(loc).path or "/" for loc in locs
            if urlparse(loc).hostname == target or urlparse(loc).hostname == "www." + target
        ]))[:40]
    queue = list(dict.fromkeys(queue + MISTAKE_PATHS))
    for path in queue:
        get(path)
    pages, assets, blocked, missing, mistakes = {}, {}, [], [], []
    home_body = None
    if home and home.get("status") == 200:
        home_body = home["body"]
    for path, row in sorted(results.items()):
        status, ctype = row.get("status"), (row.get("headers") or {}).get("content-type", [""])[0]
        entry = {"status": status, "type": ctype, "bytes": len(row.get("body") or b"")}
        same_as_home = bool(home_body) and row.get("body") == home_body and path not in ("/", "/index.html")
        if path in MISTAKE_PATHS:
            if status == 200 and not same_as_home:
                mistakes.append({"path": path, **entry})
            elif status == 403:
                blocked.append({"path": path, **entry})
            continue
        if status == 200 and same_as_home:
            continue
        if status == 200:
            if "html" in ctype:
                pages[path] = entry
            else:
                assets[path] = entry
        elif status == 403:
            blocked.append({"path": path, **entry})
        elif status == 404:
            missing.append(path)
    findings: list[dict[str, Any]] = []
    for item in mistakes:
        findings.append({
            "id": "mistake-path-exposed",
            "severity": "critical" if item["path"] in ("/.env", "/.git/HEAD", "/.git/config") else "high",
            "detail": f"{item['path']} returned 200 ({item['type']}, {item['bytes']} bytes)",
        })
    if sitemap is None or sitemap.get("status") != 200:
        findings.append({"id": "sitemap-missing", "severity": "low", "detail": "no /sitemap.xml"})
    critical = [f for f in findings if f["severity"] == "critical"]
    high = [f for f in findings if f["severity"] == "high"]
    return {
        "author": "Created by Parth Patel, founder of BenchBrex.com",
        "target": target,
        "authorization": auth,
        "requests_used": max_requests - budget["left"],
        "pages": pages, "assets": assets,
        "blocked": blocked, "missing": missing, "mistakes": mistakes,
        "findings": findings,
        "high_count": len(high) + len(critical),
        "verdict": "ATTENTION" if (high or critical) else "NO HIGH FINDINGS",
    }


# ---------------------------------------------------------------------------
# Web posture history (created by Parth Patel, founder of BenchBrex.com)
# ---------------------------------------------------------------------------

WEB_HISTORY_DIR = Path(__file__).resolve().parent.parent / "state" / "web-history"


def web_history_save(report: dict[str, Any]) -> dict[str, Any]:
    """Append one web-posture report for its host. Cookie values were never stored."""
    host = str(report.get("target", "")).strip()
    if not host:
        return {"error": "report has no target"}
    directory = WEB_HISTORY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "path": report.get("path"),
        "high_count": report.get("high_count"),
        "finding_ids": sorted(f.get("id") for f in report.get("findings", [])),
    }
    destination = directory / f"{host}.jsonl"
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return {"saved": str(destination), "entry": entry}


def web_history_diff(target: str) -> dict[str, Any]:
    """Last two runs for one host: what appeared and what went away."""
    destination = WEB_HISTORY_DIR / f"{target}.jsonl"
    if not destination.exists():
        return {"error": f"no history for {target}"}
    entries = [json.loads(line) for line in destination.read_text().splitlines() if line.strip()]
    if not entries:
        return {"error": "history file empty"}
    latest, previous = entries[-1], (entries[-2] if len(entries) >= 2 else None)
    old_ids = set(previous["finding_ids"]) if previous else set()
    new_ids = set(latest["finding_ids"])
    return {
        "target": target,
        "runs": len(entries),
        "latest": latest,
        "new_findings": sorted(new_ids - old_ids),
        "resolved_findings": sorted(old_ids - new_ids),
        "stable": sorted(new_ids & old_ids),
    }


# ---------------------------------------------------------------------------
# v2.4: Tailscale posture (created by Parth Patel, founder of BenchBrex.com).
# Read-only local check. Never starts, stops, logs in/out, or changes
# Serve/Funnel/ACLs — those are owner-approval actions.
# ---------------------------------------------------------------------------

def classify_serve_json(payload: Any) -> str:
    """`tailscale serve status --json` → off | on | unknown.

    Known shapes: newer builds return {"ServeConfig": null|{...}}; 1.102.x
    returns the config map itself, so {} means no serve config.
    """
    if payload is None or not isinstance(payload, dict):
        return "unknown"
    if "ServeConfig" in payload:
        config = payload["ServeConfig"]
        if config in (None, {}):
            return "off"
        if isinstance(config, dict) and config:
            return "on"
        return "unknown"
    if payload == {}:
        return "off"
    # 1.102.x config map: keys are host:port, values are config objects.
    return "on" if any(isinstance(v, dict) for v in payload.values()) else "unknown"


def classify_exposure_text(exit_code: int, stdout: str, stderr: str) -> str:
    """Serve/funnel status text → off | on | unknown. Raw text stays in the report."""
    text = f"{stdout}\n{stderr}".lower()
    if "proxying" in text or ("https://" in text and "disabled" not in text):
        return "on"
    if "no serve config" in text or "disabled" in text or "none" in text:
        return "off"
    return "unknown"


def _tailscale_findings(
    backend_state: str | None,
    serve_state: str,
    funnel_state: str,
    ssh_enabled: bool | None,
    advertised_routes: list[str],
) -> list[dict[str, Any]]:
    """Severity rules for Tailscale surface. Funnel is public-internet exposure."""
    findings: list[dict[str, Any]] = []
    if funnel_state == "on":
        findings.append({
            "id": "tailscale-funnel-public",
            "severity": "critical",
            "detail": "Funnel is active: a public ts.net URL reaches this machine from the internet.",
        })
    if serve_state == "on":
        findings.append({
            "id": "tailscale-serve-active",
            "severity": "medium",
            "detail": "Serve is active: a local service is exposed to the tailnet.",
        })
    if ssh_enabled:
        findings.append({
            "id": "tailscale-ssh-enabled",
            "severity": "low",
            "detail": "Tailscale SSH is enabled: tailnet devices can open a shell on this host.",
        })
    if "0.0.0.0/0" in advertised_routes or "::/0" in advertised_routes:
        findings.append({
            "id": "tailscale-exit-node",
            "severity": "low",
            "detail": "Exit node advertised: other tailnet devices may route traffic through this host.",
        })
    if backend_state in ("NeedsLogin", "NoState", "Stopped", None):
        findings.append({
            "id": "tailscale-not-connected",
            "severity": "info",
            "detail": f"Backend state {backend_state!r}: installed but not connected; no tailnet exposure.",
        })
    return findings


def tailscale_posture() -> dict[str, Any]:
    """Read-only Tailscale attack-surface check of this machine."""
    author = "Created by Parth Patel, founder of BenchBrex.com"
    cli = shutil.which("tailscale")
    if not cli and Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale").exists():
        cli = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if not cli:
        return {
            "author": author, "installed": False, "cli": None,
            "findings": [{"id": "tailscale-not-installed", "severity": "info",
                          "detail": "No tailscale CLI or app found on this machine."}],
            "high_count": 0, "verdict": "NO HIGH FINDINGS",
        }

    def run(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
        try:
            proc = subprocess.run([cli, *args], capture_output=True, text=True,
                                  timeout=timeout, check=False)
            return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
        except (subprocess.TimeoutExpired, OSError) as exc:
            return 1, "", str(exc)[:140]

    _, version_out, _ = run("version")
    version = version_out.splitlines()[0].strip() if version_out else None

    backend_state = None
    tailnet_ips: list[str] = []
    self_dns = None
    peer_count = None
    rc, out, err = run("status", "--json")
    try:
        status = json.loads(out) if out else {}
    except json.JSONDecodeError:
        status = {}
    if isinstance(status, dict) and status:
        backend_state = status.get("BackendState")
        tailnet_ips = list(status.get("TailscaleIPs") or [])
        self_dns = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".") or None
        peers = status.get("Peer") or {}
        peer_count = len(peers) if isinstance(peers, dict) else None

    rc, out, err = run("serve", "status", "--json")
    serve_raw = out or err
    try:
        serve_state = classify_serve_json(json.loads(out)) if out and rc == 0 else None
    except json.JSONDecodeError:
        serve_state = None
    if serve_state is None:
        rc2, out2, err2 = run("serve", "status")
        serve_raw = out2 or err2
        serve_state = classify_exposure_text(rc2, out2, err2)

    rc, out, err = run("funnel", "status")
    funnel_state = classify_exposure_text(rc, out, err)
    funnel_raw = out or err

    ssh_enabled = None
    advertised_routes: list[str] = []
    rc, out, err = run("debug", "prefs")
    try:
        prefs = json.loads(out) if out else {}
    except json.JSONDecodeError:
        prefs = {}
    if isinstance(prefs, dict) and prefs:
        ssh_enabled = bool(prefs.get("RunSSH"))
        routes = prefs.get("AdvertiseRoutes") or []
        advertised_routes = [str(r) for r in routes]

    findings = _tailscale_findings(backend_state, serve_state, funnel_state,
                                   ssh_enabled, advertised_routes)
    severe = [f for f in findings if f["severity"] in ("high", "critical")]
    return {
        "author": author,
        "installed": True,
        "cli": cli,
        "version": version,
        "backend_state": backend_state,
        "self": {"dns": self_dns, "tailscale_ips": tailnet_ips},
        "peer_count": peer_count,
        "serve": {"state": serve_state, "raw": serve_raw[:200]},
        "funnel": {"state": funnel_state, "raw": funnel_raw[:200]},
        "ssh_enabled": ssh_enabled,
        "advertised_routes": advertised_routes,
        "findings": findings,
        "high_count": len(severe),
        "verdict": "ATTENTION" if severe else "NO HIGH FINDINGS",
    }


if __name__ == "__main__":
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="BG Recon posture CLI")
    ap.add_argument("action", choices=["posture", "baseline-save", "baseline-diff", "report", "scan", "web", "tls", "map", "web-history", "tailscale"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--target", default=None)
    ap.add_argument("--ports", default=None)
    ap.add_argument("--path", default="/")
    ap.add_argument("--allow-external", action="store_true")
    a = ap.parse_args()
    if a.action == "scan":
        if not a.target:
            raise SystemExit("scan requires --target")
        auth = authorization(a.target, allow_external=a.allow_external)
        if not auth.get("allowed"):
            print(_json.dumps({"error": "unauthorized target", "detail": auth.get("reason")}, indent=1))
            raise SystemExit(1)
        try:
            ports = parse_port_spec(a.ports)
        except ValueError as exc:
            raise SystemExit(str(exc))
        report = scan_target(auth["resolved"][0], ports)
        report["authorization"] = auth
        print(_json.dumps(report, indent=1))
    elif a.action == "web":
        if not a.target:
            raise SystemExit("web requires --target")
        report = web_posture(a.target, a.allow_external, a.path)
        if not report.get("error"):
            web_history_save(report)
        print(_json.dumps(report, indent=1))
        raise SystemExit(1 if report.get("error") or report.get("high_count") else 0)
    elif a.action == "tls":
        if not a.target:
            raise SystemExit("tls requires --target")
        report = tls_posture(a.target, a.allow_external)
        print(_json.dumps(report, indent=1))
        raise SystemExit(1 if report.get("error") or report.get("high_count") else 0)
    elif a.action == "map":
        if not a.target:
            raise SystemExit("map requires --target")
        report = site_map(a.target, a.allow_external)
        print(_json.dumps(report, indent=1))
        raise SystemExit(1 if report.get("error") or report.get("high_count") else 0)
    elif a.action == "web-history":
        if not a.target:
            raise SystemExit("web-history requires --target")
        result = web_history_diff(a.target)
        print(_json.dumps(result, indent=1))
        raise SystemExit(1 if result.get("error") else 0)
    elif a.action == "tailscale":
        report = tailscale_posture()
        print(_json.dumps(report, indent=1))
        raise SystemExit(1 if report.get("high_count") else 0)
    elif a.action == "posture":
        print(_json.dumps(posture(), indent=1))
    elif a.action == "baseline-save":
        print(_json.dumps(baseline_save(), indent=1))
    elif a.action == "baseline-diff":
        print(_json.dumps(baseline_diff(), indent=1))
    else:
        print(report_html(a.out))
