"""Pinned systemd module control flow; every command/host lookup is intercepted."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("backend", ROOT / "tests/fixtures/decommission_backend.py")
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)
UNIT = "fixture-alias@retained.home.service"
LINK = "/etc/systemd/system/multi-user.target.wants/" + UNIT
ARGS = {"name": UNIT, "state": "stopped", "enabled": False, "scope": "system"}


class NativeTests(unittest.TestCase):
    def test_loaded_first_cleanup_and_repeat_with_preservation(self):
        units = {UNIT: {"load_state": "loaded", "running": True, "enabled": True},
                 "fixture-daemon.service": {"running": True, "enabled": True}}
        unrelated = "/etc/systemd/system/multi-user.target.wants/fixture-daemon.service"
        links = [LINK, unrelated]
        result = BACKEND.native_systemd(ARGS, units, links)
        self.assertFalse(result.get("failed", False))
        self.assertTrue(result["changed"])
        self.assertFalse(units[UNIT]["running"])
        self.assertFalse(units[UNIT]["enabled"])
        self.assertEqual(links, [unrelated])
        self.assertEqual(units["fixture-daemon.service"], {"running": True, "enabled": True})
        self.assertFalse(BACKEND.native_systemd(ARGS, units, links)["changed"])

    def test_native_missing_definition_control_requires_separate_resident_path(self):
        for active in ("inactive", "failed", "active"):
            units = {UNIT: {"load_state": "not-found", "active_state": active,
                            "running": active == "active", "enabled": True}}
            before = copy.deepcopy(units)
            links = [LINK]
            result = BACKEND.native_systemd(ARGS, units, links)
            self.assertTrue(result["failed"])
            self.assertIn("Could not find the requested service", result["msg"])
            self.assertEqual(units, before)
            self.assertEqual(links, [LINK])

    def test_native_check_mode_predicts_without_mutation(self):
        units = {UNIT: {"load_state": "loaded", "running": True, "enabled": True}}
        before = copy.deepcopy(units)
        links = [LINK]
        result = BACKEND.native_systemd(ARGS, units, links, check_mode=True)
        self.assertTrue(result["changed"])
        self.assertEqual(units, before)
        self.assertEqual(links, [LINK])


if __name__ == "__main__":
    unittest.main()
