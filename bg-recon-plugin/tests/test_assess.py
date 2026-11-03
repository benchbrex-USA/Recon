"""Tests for BG Recon v2.5 assessment orchestrator. No network.

Created by Parth Patel, founder of BenchBrex.com.
"""
import importlib.util
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("recon", str(PLUGIN))
recon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recon)


class AggregateTests(unittest.TestCase):
    def test_sources_attached_and_sorted_by_severity(self):
        checks = {
            "web": {"findings": [{"id": "hsts-absent", "severity": "high"}]},
            "map": {"findings": [{"id": "mistake-path-exposed", "severity": "critical"}]},
            "tls": {"findings": [{"id": "cert-expiring", "severity": "low"}]},
        }
        rows = recon.aggregate_findings(checks)
        self.assertEqual([r["severity"] for r in rows], ["critical", "high", "low"])
        self.assertEqual(rows[0]["source"], "map")
        self.assertEqual(rows[-1]["source"], "tls")


class SlugTests(unittest.TestCase):
    def test_host_slug(self):
        self.assertEqual(recon._slug("ShreeramaAerospace.com"), "shreeramaaerospace.com")
        self.assertEqual(recon._slug("weird host//x"), "weird-host-x")
        self.assertEqual(recon._slug("###"), "host")


class TestsslJsonTests(unittest.TestCase):
    def test_dict_shape_scanresult(self):
        raw = '{"scanResult": [{"id": "SSLv1", "severity": "HIGH", "finding": "offered"}, {"id": "x", "severity": "INFO", "finding": "skip"}]}'
        rows = recon.parse_testssl_json(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "testssl-SSLv1")
        self.assertEqual(rows[0]["severity"], "high")

    def test_list_shape_and_lowercase(self):
        raw = '[{"id": "y", "severity": "low", "finding": "f"}]'
        self.assertEqual(recon.parse_testssl_json(raw)[0]["severity"], "low")

    def test_malformed_is_empty(self):
        self.assertEqual(recon.parse_testssl_json("not json"), [])
        self.assertEqual(recon.parse_testssl_json('{"nope": 1}'), [])


class EscTests(unittest.TestCase):
    def test_html_escaped(self):
        out = recon._esc("<script>")
        self.assertNotIn("<script>", out)
        # build the expected entity without a literal entity in this file
        expected = chr(38) + "lt;script" + chr(38) + "gt;"
        self.assertEqual(out, expected)


class ChallengeTests(unittest.TestCase):
    def test_interstitial_detected_by_title(self):
        body = b"<html><title>One moment, please...</title></html>"
        self.assertTrue(recon.is_bot_challenge({}, body))

    def test_detected_by_cf_edge_cache_header(self):
        self.assertTrue(recon.is_bot_challenge({"cf-edge-cache": ["no-cache"]}, b"<html></html>"))

    def test_normal_page_not_flagged(self):
        self.assertFalse(recon.is_bot_challenge({}, b"<html><title>Shreeram</title></html>"))
        self.assertFalse(recon.is_bot_challenge({}, None))


if __name__ == "__main__":
    unittest.main()
