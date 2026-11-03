"""Tests for BG Recon v2.3 TLS/map/history logic. No network.

Created by Parth Patel, founder of BenchBrex.com.
"""
import importlib.util
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("recon", str(PLUGIN))
recon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recon)


class DaysRemainingTests(unittest.TestCase):
    def test_future_date(self):
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        left = recon.days_remaining("Apr 12 05:37:33 2027 GMT", now=now)
        self.assertEqual(left, 161)

    def test_expired_is_negative(self):
        now = datetime(2027, 5, 1, tzinfo=timezone.utc)
        self.assertLess(recon.days_remaining("Apr 12 05:37:33 2027 GMT", now=now), 0)

    def test_garbage_is_none(self):
        self.assertIsNone(recon.days_remaining("not a date"))


class ProtocolErrorTests(unittest.TestCase):
    def test_client_limit_is_not_a_server_fact(self):
        self.assertEqual(
            recon.classify_protocol_error("no protocols available"),
            "client-unsupported",
        )

    def test_server_alert_is_rejection(self):
        self.assertEqual(
            recon.classify_protocol_error("tlsv1 alert protocol version"),
            "server-rejected",
        )


class ExtractLinksTests(unittest.TestCase):
    def test_same_host_only_and_scheme_filtered(self):
        html = (
            '<a href="/about-us.html">x</a>'
            '<a href="mailto:a@b.c">m</a>'
            '<a href="javascript:void(0)">j</a>'
            '<img src="https://cdn.other.example/x.png">'
            '<form action="http://shreeramaerospace.com/contact.html">'
        )
        base = "http://shreeramaerospace.com/"
        links = recon.extract_links(html, base)
        self.assertEqual(links, ["http://shreeramaerospace.com/about-us.html",
                                 "http://shreeramaerospace.com/contact.html"])


class HistoryTests(unittest.TestCase):
    def test_save_and_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = recon.WEB_HISTORY_DIR
            recon.WEB_HISTORY_DIR = Path(tmp)
            try:
                recon.web_history_save({"target": "t.example", "path": "/",
                                        "high_count": 1, "findings": [{"id": "a"}]})
                recon.web_history_save({"target": "t.example", "path": "/",
                                        "high_count": 2,
                                        "findings": [{"id": "a"}, {"id": "b"}]})
                diff = recon.web_history_diff("t.example")
                self.assertEqual(diff["runs"], 2)
                self.assertEqual(diff["new_findings"], ["b"])
                self.assertEqual(diff["resolved_findings"], [])
            finally:
                recon.WEB_HISTORY_DIR = original


if __name__ == "__main__":
    unittest.main()
