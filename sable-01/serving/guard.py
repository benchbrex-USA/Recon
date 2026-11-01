#!/usr/bin/env python3
"""Sable-01 envelope guard — reverse proxy in front of mlx_lm.server.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Listens on 127.0.0.1:8001 (public); forwards to mlx_lm.server on 127.0.0.1:8002.

Contract (spec r3, designs/sable-agent-integration.md):
  POST /v1/chat/completions
    - validate: model present (rewritten to "default_model" on forward), messages
      non-empty [{role, content}], max_tokens int 1..8192 (default 512),
      temperature 0..2 if present -> else 400 field-specific
    - token gate: chat-template-exact count via the BASE tokenizer
      (mlx_lm.tokenizer_utils.load — the same path mlx_lm.load uses) <= 8192
      -> forward; else 413 with the count
    - backend 404 (verified zombie signature) -> 503 + X-Sable-Zombie + atomic marker
    - backend down -> 502; generation timeout 180 s -> 504
    - self-healing: a 200 forward deletes the zombie marker
  GET /v1/models -> forwarded verbatim
  GET /health    -> guard-local JSON (guard up even if backend dead)
  GET /ready     -> 200 iff last successful forward < 120 s ago
  Backpressure: 2 in-flight + 4 queued (503 busy); 60 req/min sliding window (429).
  Lifecycle: atomic PID file + stale-PID check; SIGTERM/SIGINT drain <= 30 s.

Run with the project venv: venv/bin/python3 serving/guard.py
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SABLE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_HOST, PUBLIC_PORT = "127.0.0.1", 8001
BACKEND = "http://127.0.0.1:8002"
ENVELOPE_TOKENS = 8192
GEN_TIMEOUT_S = 180
MAX_INFLIGHT, MAX_QUEUED = 2, 4
RATE_LIMIT, RATE_WINDOW_S = 60, 60
MAX_BODY_BYTES = 1_048_576  # 1 MiB — oversized bodies are rejected, never buffered
READY_WINDOW_S = 120
MARKER_TTL_S = 600
REQLOG_MAX_BYTES = 5_242_880  # 5 MiB — rotated (truncated) on write

# --- metrics (v2, single-lock discipline shared with all state below) --------
metrics_lock_inherited = True  # all metric mutations happen under _lock
m_started = time.time()
m_total = 0
m_by_status: dict[int, int] = {}
m_latencies: list[float] = []  # last 200 generation latencies (s)
SERVING_DIR = SABLE_DIR / "serving"
MARKER = SERVING_DIR / "zombie"
PIDFILE = SERVING_DIR / "guard.pid"
REQLOG = SERVING_DIR / "requests.log"
ATTRIBUTION = "Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex)."

_lock = threading.Lock()
_cond = threading.Condition(_lock)
in_flight = 0
queued = 0
rate_window: deque[float] = deque()
last_backend_ok: float | None = None
shutting_down = False

# --- tokenizer (backend-exact: mlx_lm.tokenizer_utils.load) -------------------
# Source is env-configurable (SABLE_TOKENIZER_SOURCE): production uses the
# local base/ directory; CI uses the public HF tokenizer id (no weights).
# Loading is LAZY — import must not require the model artifacts (Goldfish-D
# CI finding: unit tests stub count_tokens but still import this module).

_TOKENIZER = None


def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        from mlx_lm.tokenizer_utils import load as _mlx_load_tokenizer

        source = os.environ.get("SABLE_TOKENIZER_SOURCE", str((SABLE_DIR / "base").resolve()))
        try:
            _TOKENIZER = _mlx_load_tokenizer(Path(source))
        except Exception as exc:  # fail fast with an actionable error
            print(f"[guard] FATAL: cannot load tokenizer from {source}: {exc}\n"
                  f"[guard] is the external volume mounted and base/ complete?",
                  file=sys.stderr)
            sys.exit(1)
    return _TOKENIZER


def count_tokens(messages: list[dict]) -> int:
    ids = _get_tokenizer().apply_chat_template(messages, add_generation_prompt=True)
    return len(ids)


# --- small helpers ------------------------------------------------------------

def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def write_marker() -> None:
    try:
        atomic_write(MARKER, str(time.time()))
    except OSError as exc:
        print(f"[guard] marker write failed (continuing): {exc}", file=sys.stderr)


def clear_marker() -> None:
    try:
        MARKER.unlink(missing_ok=True)
    except OSError:
        pass


def marker_fresh() -> bool:
    if not MARKER.exists():
        return False
    return (time.time() - MARKER.stat().st_mtime) < MARKER_TTL_S


def log_request(body: str) -> None:
    """Outbound body log — the AC-007 observation mechanism (single-user host)."""
    try:
        if REQLOG.exists() and REQLOG.stat().st_size > REQLOG_MAX_BYTES:
            REQLOG.write_text("")  # rotate (truncate) — single-user diagnostic log
        with REQLOG.open("a") as f:
            f.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{body}\n")
    except OSError:
        pass


# --- backend forward ----------------------------------------------------------

class GenTimeout(Exception):
    """Backend accepted the connection but generation exceeded GEN_TIMEOUT_S."""


def forward(body_bytes: bytes) -> tuple[int, bytes, str]:
    req = urllib.request.Request(
        f"{BACKEND}/v1/chat/completions", data=body_bytes,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=GEN_TIMEOUT_S) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
    except (TimeoutError, socket.timeout) as exc:
        raise GenTimeout(str(exc)) from None


# --- request handler ----------------------------------------------------------

class Guard(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet default logging; serve.log via mlx
        pass

    def _send(self, code: int, payload: bytes | str, ctype: str = "application/json",
              extra: dict | None = None) -> None:
        body = payload.encode() if isinstance(payload, str) else payload
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict, extra: dict | None = None) -> None:
        self._send(code, json.dumps(obj), extra=extra)

    def do_GET(self):
        global last_backend_ok
        if self.path == "/health":
            with _lock:
                age = None if last_backend_ok is None else round(time.time() - last_backend_ok, 1)
                zombie = marker_fresh()
                n = in_flight
            self._json(200, {"guard": "up", "author": ATTRIBUTION, "zombie": zombie,
                             "in_flight": n, "last_backend_ok_age_s": age,
                             "envelope_tokens": ENVELOPE_TOKENS})
            return
        if self.path == "/ready":
            with _lock:
                ok = last_backend_ok is not None and (time.time() - last_backend_ok) < READY_WINDOW_S
            self._json(200 if ok else 503, {"ready": ok})
            return
        if self.path == "/metrics":
            with _lock:
                lats = sorted(m_latencies)
                n = len(lats)
                pct = lambda q: (lats[min(n - 1, int(n * q))] if n else None)  # noqa: E731
                self._json(200, {
                    "uptime_s": round(time.time() - m_started, 1),
                    "requests_total": m_total,
                    "by_status": dict(sorted(m_by_status.items())),
                    "latency_s": {"p50": pct(0.50), "p95": pct(0.95), "count": n},
                })
            return
        # every other GET forwards to the backend unchanged
        try:
            with urllib.request.urlopen(f"{BACKEND}{self.path}", timeout=15) as resp:
                self._send(resp.status, resp.read(), resp.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self._send(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"))
        except Exception as exc:
            self._json(502, {"error": f"mlx server not reachable: {exc} — run serve.sh start"})

    def do_POST(self):
        global in_flight, queued, last_backend_ok, m_total, m_by_status, m_latencies
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": "not found"})
            return
        if shutting_down:
            self._json(503, {"error": "shutting down — drain in progress"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": f"request body too large ({length} bytes; cap {MAX_BODY_BYTES})"})
            return
        # rate limit (sliding window)
        now = time.time()
        with _lock:
            while rate_window and now - rate_window[0] > RATE_WINDOW_S:
                rate_window.popleft()
            if len(rate_window) >= RATE_LIMIT:
                self._json(429, {"error": "rate limit exceeded"})
                return
            rate_window.append(now)
            # admission: 2 in-flight + 4 queued
            if in_flight >= MAX_INFLIGHT:
                if queued >= MAX_QUEUED or shutting_down:
                    self._send(503, json.dumps({"error": "server busy"}),
                               extra={"Retry-After": "5"})
                    return
                queued += 1
                while in_flight >= MAX_INFLIGHT and not shutting_down:
                    _cond.wait(timeout=5)
                queued -= 1
                if shutting_down:
                    self._json(503, {"error": "shutting down"})
                    return
            in_flight += 1
        try:
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "body is not valid JSON"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"error": "body must be a JSON object"})
                return
            # validation (F-007)
            if "model" not in payload:
                self._json(400, {"error": "'model' is required"})
                return
            messages = payload.get("messages")
            if (not isinstance(messages, list) or not messages
                    or not all(isinstance(m, dict) and "role" in m and "content" in m
                               for m in messages)):
                self._json(400, {"error": "'messages' must be a non-empty array of {role, content}"})
                return
            # defensive: coerce non-string content (models emit objects sometimes)
            for m in messages:
                if not isinstance(m["content"], str):
                    m["content"] = json.dumps(m["content"], ensure_ascii=False)
            mt = payload.get("max_tokens", 512)
            if not isinstance(mt, int) or not 1 <= mt <= 8192:
                self._json(400, {"error": "'max_tokens' must be an integer in [1, 8192]"})
                return
            temp = payload.get("temperature", 0.3)
            if not isinstance(temp, (int, float)) or not 0 <= temp <= 2:
                self._json(400, {"error": "'temperature' must be a number in [0, 2]"})
                return
            # model rewrite (F-001) + token gate (INV-5)
            payload["model"] = "default_model"
            try:
                n_tokens = count_tokens(messages)
            except Exception as exc:
                self._json(400, {"error": f"could not tokenize messages: {exc}"})
                return
            if n_tokens > ENVELOPE_TOKENS:
                self._json(413, {"error": (
                    f"prompt is {n_tokens} tokens; Sable-01 envelope is {ENVELOPE_TOKENS} — "
                    "send a short, self-contained question")})
                return
            body = json.dumps(payload).encode()
            log_request(body.decode(errors="replace"))
            t0 = time.monotonic()
            try:
                status, resp_body, ctype = forward(body)
            except GenTimeout:
                with _lock:
                    m_total += 1
                    m_by_status[504] = m_by_status.get(504, 0) + 1
                    m_latencies.append(time.monotonic() - t0)
                    if len(m_latencies) > 200:
                        del m_latencies[0]
                self._json(504, {"error": "generation timeout — run serve.sh restart if it persists"})
                return
            with _lock:
                m_total += 1
                m_by_status[status] = m_by_status.get(status, 0) + 1
                m_latencies.append(time.monotonic() - t0)
                if len(m_latencies) > 200:
                    del m_latencies[0]
            if status == 200:
                with _lock:
                    last_backend_ok = time.time()
                clear_marker()
                self._send(status, resp_body, ctype)
            elif status == 404:
                # verified zombie signature (generation thread dead)
                write_marker()
                self._json(503, {"error": "generation thread dead — run ~/sable-01/serve.sh restart"},
                           extra={"X-Sable-Zombie": "true"})
            else:
                self._send(status, resp_body, ctype)
        except Exception as exc:
            self._json(502, {"error": f"backend failure: {exc} — run serve.sh start"})
        finally:
            with _lock:
                in_flight -= 1
                _cond.notify_all()

    def do_DELETE(self):
        self._json(404, {"error": "not found"})


# --- lifecycle ----------------------------------------------------------------

def write_pid() -> None:
    stale = None
    if PIDFILE.exists():
        try:
            stale = int(PIDFILE.read_text().strip())
            os.kill(stale, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            stale = None  # dead or unreadable -> rewrite
    atomic_write(PIDFILE, str(os.getpid()))


def drain_and_exit(signum, frame):
    global shutting_down
    shutting_down = True
    print("[guard] draining in-flight requests (<=30 s)…", file=sys.stderr)
    deadline = time.time() + 30
    while time.time() < deadline:
        with _lock:
            if in_flight == 0:
                break
        time.sleep(0.25)
    threading.Thread(target=httpd.shutdown, daemon=True).start()


class GuardServer(ThreadingHTTPServer):
    # default backlog (5) resets bursts at the TCP level before the admission
    # caps can answer with a clean 503 — hold them in the backlog instead.
    request_queue_size = 32
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    SERVING_DIR.mkdir(parents=True, exist_ok=True)
    write_pid()
    # startup zombie re-validation (D-3): GET /v1/models answers 200 even when the
    # generation thread is dead (verified), so the only sound probe is a real tiny
    # generation. 200 -> the thread is alive, marker cleared; 404/down -> marker kept.
    if MARKER.exists():
        probe = json.dumps({"model": "default_model",
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 8, "temperature": 0.0}).encode()
        preq = urllib.request.Request(f"{BACKEND}/v1/chat/completions", data=probe,
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(preq, timeout=90) as resp:
                if resp.status == 200:
                    clear_marker()
                    print("[guard] startup generation probe OK — zombie marker cleared",
                          file=sys.stderr)
        except urllib.error.HTTPError as exc:
            print(f"[guard] startup probe: backend HTTP {exc.code} — marker kept",
                  file=sys.stderr)
        except Exception as exc:
            print(f"[guard] startup probe failed ({exc.__class__.__name__}) — marker kept",
                  file=sys.stderr)
    httpd = GuardServer((PUBLIC_HOST, PUBLIC_PORT), Guard)
    signal.signal(signal.SIGTERM, drain_and_exit)
    signal.signal(signal.SIGINT, drain_and_exit)
    print(f"[guard] {ATTRIBUTION}", file=sys.stderr)
    print(f"[guard] up on {PUBLIC_HOST}:{PUBLIC_PORT} -> {BACKEND} "
          f"(envelope {ENVELOPE_TOKENS} tok, gen timeout {GEN_TIMEOUT_S} s)", file=sys.stderr)
    httpd.serve_forever()
    print("[guard] exited", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
