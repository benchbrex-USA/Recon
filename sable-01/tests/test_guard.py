"""Unit battery for the Sable-01 envelope guard — real handler, stubbed backend.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Run: venv/bin/python3 tests/test_guard.py   (from ~/sable-01)
Every test instantiates the REAL Guard handler with a stubbed socket and a
stubbed forward(); module state is reset between tests.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("guard", ROOT / "serving" / "guard.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

PASS_BODY = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()


def reset_state():
    with g._lock:
        g.in_flight = 0
        g.queued = 0
        g.rate_window.clear()
        g.last_backend_ok = None
        g.shutting_down = False
        g.m_total = 0
        g.m_by_status = {}
        g.m_latencies = []
    g.clear_marker()
    if g.REQLOG.exists():
        g.REQLOG.unlink()


def make_handler(body: bytes, path: str = "/v1/chat/completions",
                 headers: dict | None = None):
    class FakeHandler(g.Guard):
        def __init__(self):
            pass
        def send_response(self, code):
            self.code = code
        def send_header(self, k, v):
            pass
        def end_headers(self):
            pass
        def _send(self, code, payload, ctype="application/json", extra=None):
            self.out = (code, payload if isinstance(payload, str) else payload.decode(),
                        dict(extra or {}))
        def _json(self, code, obj, extra=None):
            self.out = (code, json.dumps(obj), dict(extra or {}))

    h = FakeHandler()
    h.rfile = type("R", (), {"read": staticmethod(lambda n: body)})()
    h.headers = {"Content-Length": str(len(body)), **(headers or {})}
    h.path = path
    return h


def ok_forward(body_bytes):
    return 200, PASS_BODY, "application/json"


class TestGuard(unittest.TestCase):

    def setUp(self):
        reset_state()

    def run_post(self, body_obj, forward_impl=ok_forward):
        raw = json.dumps(body_obj).encode() if not isinstance(body_obj, bytes) else body_obj
        h = make_handler(raw)
        with patch.object(g, "forward", forward_impl), \
             patch.object(g, "log_request", lambda b: None):
            h.do_POST()
        code, text, extra = h.out
        return code, json.loads(text) if text.startswith("{") else text, extra

    # -- happy path / contracts ------------------------------------------------

    def test_t01_valid_request_forwards_and_rewrites_model(self):
        sent = {}
        def fwd(body):
            sent.update(json.loads(body))
            return 200, PASS_BODY, "application/json"
        code, body, _ = self.run_post(
            {"model": "anything", "messages": [{"role": "user", "content": "q"}]},
            forward_impl=fwd)
        self.assertEqual(code, 200)
        self.assertEqual(sent["model"], "default_model")  # INV-1 rewrite

    def test_t02_health_shape(self):
        h = make_handler(b"", path="/health")
        h.do_GET()
        code, text, _ = h.out
        d = json.loads(text)
        self.assertEqual(code, 200)
        for key in ("guard", "zombie", "in_flight", "envelope_tokens"):
            self.assertIn(key, d)

    # -- validation matrix (400s) ----------------------------------------------

    def test_t03_missing_model(self):
        code, body, _ = self.run_post({"messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t04_empty_messages(self):
        code, body, _ = self.run_post({"model": "m", "messages": []})
        self.assertEqual(code, 400)

    def test_t05_messages_not_list(self):
        code, body, _ = self.run_post({"model": "m", "messages": "hello"})
        self.assertEqual(code, 400)

    def test_t06_message_missing_content(self):
        code, body, _ = self.run_post({"model": "m", "messages": [{"role": "user"}]})
        self.assertEqual(code, 400)

    def test_t07_max_tokens_zero(self):
        code, _, _ = self.run_post({"model": "m", "max_tokens": 0,
                                    "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t08_max_tokens_huge(self):
        code, _, _ = self.run_post({"model": "m", "max_tokens": 10_000_000,
                                    "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t09_max_tokens_string(self):
        code, _, _ = self.run_post({"model": "m", "max_tokens": "512",
                                    "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t10_temperature_out_of_range(self):
        code, _, _ = self.run_post({"model": "m", "temperature": 5,
                                    "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t11_invalid_json_body(self):
        code, body, _ = self.run_post(b"{not json")
        self.assertEqual(code, 400)

    # -- coercion (D-1) ---------------------------------------------------------

    def test_t12_dict_content_coerced_and_forwarded(self):
        sent = {}
        def fwd(body):
            sent.update(json.loads(body))
            return 200, PASS_BODY, "application/json"
        code, _, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": {"a": 1}}]},
            forward_impl=fwd)
        self.assertEqual(code, 200)
        self.assertIsInstance(sent["messages"][0]["content"], str)

    # -- envelope gate ----------------------------------------------------------

    def test_t13_over_envelope_413_thread_logic(self):
        code, body, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "x" * 40}]},
            forward_impl=ok_forward)
        # force the count high via a big real message instead:
        big = self.run_post({"model": "m",
                             "messages": [{"role": "user", "content": "word " * 12000}]})
        self.assertEqual(big[0], 413)
        self.assertIn("8192", str(big[1]))

    # -- zombie lifecycle -------------------------------------------------------

    def test_t14_backend_404_zombie_503_and_marker(self):
        def zombie_forward(body):
            return 404, b'{"error": "x"}', "application/json"
        code, body, extra = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]},
            forward_impl=zombie_forward)
        self.assertEqual(code, 503)
        self.assertEqual(extra.get("X-Sable-Zombie"), "true")
        self.assertTrue(g.MARKER.exists())  # marker written

    def test_t15_success_clears_marker(self):
        g.write_marker()
        self.assertTrue(g.MARKER.exists())
        code, _, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 200)
        self.assertFalse(g.MARKER.exists())  # self-clearing

    # -- timeout branch ---------------------------------------------------------

    def test_t16_generation_timeout_504(self):
        def hanging(body):
            raise g.GenTimeout("timed out")
        code, body, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]},
            forward_impl=hanging)
        self.assertEqual(code, 504)
        self.assertIn("generation timeout", str(body))

    def test_t17_backend_down_502(self):
        def dead(body):
            raise urllib_err()
        import urllib.error
        def urllib_err():
            raise urllib.error.URLError("connection refused")
        code, body, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]},
            forward_impl=dead)
        self.assertEqual(code, 502)

    # -- backpressure -----------------------------------------------------------

    def test_t18_in_flight_cap_busy_503(self):
        with g._lock:
            g.in_flight = g.MAX_INFLIGHT
            g.queued = g.MAX_QUEUED
        code, body, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 503)

    def test_t19_rate_limit_429(self):
        def fast(body):
            return 200, PASS_BODY, "application/json"
        last = None
        for i in range(g.RATE_LIMIT + 2):
            last = self.run_post(
                {"model": "m", "messages": [{"role": "user", "content": "q"}]},
                forward_impl=fast)
        self.assertEqual(last[0], 429)  # limit reached within the window

    # -- shutdown ---------------------------------------------------------------

    def test_t20_shutdown_rejects(self):
        with g._lock:
            g.shutting_down = True
        code, _, _ = self.run_post(
            {"model": "m", "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 503)
        with g._lock:
            g.shutting_down = False


    def test_t21_oversized_body_rejected_before_buffering(self):
        code, body, _ = self.run_post(b"x" * (2 * 1024 * 1024))
        self.assertEqual(code, 413)
        self.assertIn("too large", str(body))

    def test_t22_metrics_endpoint_shape(self):
        h = make_handler(b"", path="/metrics")
        h.do_GET()
        code, text, _ = h.out
        d = json.loads(text)
        self.assertEqual(code, 200)
        for key in ("uptime_s", "requests_total", "by_status", "latency_s"):
            self.assertIn(key, d)

    def test_t23_metrics_recorded_on_forward(self):
        def fast(body):
            return 200, PASS_BODY, "application/json"
        self.run_post({"model": "m", "messages": [{"role": "user", "content": "q"}]},
                      forward_impl=fast)
        h = make_handler(b"", path="/metrics")
        h.do_GET()
        d = json.loads(h.out[1])
        self.assertEqual(d["requests_total"], 1)
        self.assertEqual(d["by_status"].get("200"), 1)  # JSON keys are strings
        self.assertEqual(d["latency_s"]["count"], 1)

    def test_t24_negative_content_length_rejected(self):
        h = make_handler(b"{}", headers={"Content-Length": "-1"})
        with patch.object(g, "forward", ok_forward), patch.object(g, "log_request", lambda b: None):
            h.do_POST()
        self.assertEqual(h.out[0], 400)
        self.assertIn(">= 0", h.out[1])

    def test_t25_bool_max_tokens_rejected(self):
        code, _, _ = self.run_post(
            {"model": "m", "max_tokens": True,
             "messages": [{"role": "user", "content": "q"}]})
        self.assertEqual(code, 400)

    def test_t26_non_v1_get_not_proxied(self):
        h = make_handler(b"", path="/admin")
        h.do_GET()
        self.assertEqual(h.out[0], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
