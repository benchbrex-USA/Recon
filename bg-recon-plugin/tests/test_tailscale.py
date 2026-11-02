"""Tests for BG Recon v2.4 Tailscale posture logic. No network, no tailscale CLI.

Created by Parth Patel, founder of BenchBrex.com.
"""
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location(
    "recon",
    "/Volumes/Parth Patel/BeGuardit Hacking Tools/bg-recon-plugin/dashboard/plugin_api.py",
)
recon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recon)


class ServeJsonTests(unittest.TestCase):
    def test_null_config_is_off(self):
        self.assertEqual(recon.classify_serve_json({"ServeConfig": None}), "off")

    def test_empty_config_is_off(self):
        self.assertEqual(recon.classify_serve_json({"ServeConfig": {}}), "off")

    def test_present_config_is_on(self):
        self.assertEqual(
            recon.classify_serve_json({"ServeConfig": {"TCP": {"443": {}}}}), "on")

    def test_wrong_shape_is_unknown(self):
        self.assertEqual(recon.classify_serve_json({"Other": 1}), "unknown")
        self.assertEqual(recon.classify_serve_json(None), "unknown")

    def test_102x_empty_map_is_off(self):
        # 1.102.x returns the config map itself; {} means no serve config.
        self.assertEqual(recon.classify_serve_json({}), "off")

    def test_102x_nonempty_map_is_on(self):
        self.assertEqual(
            recon.classify_serve_json({"mac.tail1234.ts.net:443": {"Handlers": {}}}), "on")


class ExposureTextTests(unittest.TestCase):
    def test_no_serve_config_is_off(self):
        self.assertEqual(recon.classify_exposure_text(0, "No serve config", ""), "off")

    def test_funnel_url_is_on(self):
        text = "https://mac.tail1234.ts.net (proxying to http://127.0.0.1:8443)"
        self.assertEqual(recon.classify_exposure_text(0, text, ""), "on")

    def test_disabled_is_off(self):
        self.assertEqual(recon.classify_exposure_text(0, "Funnel is disabled.", ""), "off")

    def test_backend_error_is_unknown(self):
        self.assertEqual(recon.classify_exposure_text(1, "", "backend is not running"), "unknown")


class FindingRulesTests(unittest.TestCase):
    def test_funnel_is_critical(self):
        findings = recon._tailscale_findings("Running", "off", "on", False, [])
        ids = {f["id"]: f["severity"] for f in findings}
        self.assertEqual(ids.get("tailscale-funnel-public"), "critical")

    def test_connected_clean_machine_has_no_severe_findings(self):
        findings = recon._tailscale_findings("Running", "off", "off", False, [])
        self.assertEqual([f for f in findings if f["severity"] in ("high", "critical")], [])

    def test_logged_out_is_info_only(self):
        findings = recon._tailscale_findings("NeedsLogin", "off", "off", None, [])
        self.assertEqual([f["severity"] for f in findings], ["info"])

    def test_exit_node_and_ssh_flagged(self):
        findings = recon._tailscale_findings("Running", "off", "off", True, ["0.0.0.0/0"])
        ids = {f["id"] for f in findings}
        self.assertIn("tailscale-ssh-enabled", ids)
        self.assertIn("tailscale-exit-node", ids)


if __name__ == "__main__":
    unittest.main()
