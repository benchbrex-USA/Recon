"""Parser tests for BG Recon web posture. No network.

Created by Parth Patel, founder of BenchBrex.com.
"""
import importlib.util
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("recon", str(PLUGIN))
recon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recon)


class WebPostureTests(unittest.TestCase):
    def test_cookie_value_is_not_returned(self):
        flags = recon.inspect_set_cookie("PHPSESSID=secretvalue; path=/")
        self.assertEqual(flags["name"], "PHPSESSID")
        self.assertNotIn("secretvalue", str(flags))
        self.assertFalse(flags["secure"])
        self.assertFalse(flags["httponly"])

    def test_cleartext_cookie_is_high(self):
        findings = recon.assess_probe("http", {
            "status": 200,
            "headers": {"set-cookie": ["PHPSESSID=secretvalue; path=/"]},
        })
        ids = [f["id"] for f in findings]
        self.assertIn("http-no-redirect", ids)
        self.assertIn("cookie-cleartext", ids)
        self.assertNotIn("secretvalue", str(findings))

    def test_https_redirect_is_not_a_cleartext_finding(self):
        findings = recon.assess_probe("http", {
            "status": 301,
            "headers": {"location": ["https://example.test/"]},
        })
        self.assertEqual(findings, [])

    def test_hsts_absent_on_https(self):
        findings = recon.assess_probe("https", {"status": 200, "headers": {}})
        self.assertEqual(findings[0]["id"], "hsts-absent")


if __name__ == "__main__":
    unittest.main()
