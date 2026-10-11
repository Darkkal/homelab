"""Bounded native output parsing; all names/state are synthetic."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("policy", ROOT / "roles/decommissioned_services/filter_plugins/policy.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
RETIREMENT = [{"name": "fixture", "unit_globs": ["fixture-alias@*.service"]}]


def result(*lines, rc=0):
    return [{"rc": rc, "stdout_lines": list(lines)}]


class DiscoveryTests(unittest.TestCase):
    def parse(self, files=None, loaded=None, links=None):
        return POLICY.retired_instances(result() if files is None else files,
                                        result() if loaded is None else loaded,
                                        {"files": [], "skipped_paths": {}} if links is None else links,
                                        RETIREMENT)

    def test_union_template_file_loaded_and_enabled_instances(self):
        names = self.parse(result("fixture-alias@.service disabled enabled", "fixture-alias@direct.home.service disabled -"),
                           result("fixture-alias@running.home.service loaded active running Fixture"),
                           {"files": [{"path": "/etc/systemd/system/multi-user.target.wants/fixture-alias@stale.home.service"},
                                      {"path": "/run/systemd/system/other.target.requires/fixture-alias@running.home.service"}]})
        self.assertEqual(names, ["fixture-alias@direct.home.service", "fixture-alias@running.home.service", "fixture-alias@stale.home.service"])
        self.assertNotIn("fixture-alias@.service", names)

    def test_empty_success_and_template_only_are_not_errors(self):
        self.assertEqual(self.parse(), [])
        self.assertEqual(self.parse(result("fixture-alias@.service disabled enabled")), [])

    def test_native_empty_file_listing_status_is_confined_to_files(self):
        empty = {"rc": 1, "stdout": "", "stdout_lines": [], "stderr": "",
                 "msg": "The command exited with a non-zero return code."}
        self.assertTrue(POLICY.unit_file_discovery_ok(empty))
        self.assertEqual(self.parse(files=[empty]), [])
        with self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
            self.parse(loaded=[empty])
        for patch in ({"rc": 42}, {"stdout": "unexpected"},
                      {"stdout_lines": ["unexpected"]}, {"stderr": "SYNTHETIC_SECRET_SENTINEL"},
                      {"skipped": True}, {"unreachable": True}, {"msg": "Error executing command."}):
            bad = {**empty, **patch}
            self.assertFalse(POLICY.unit_file_discovery_ok(bad))
            with self.assertRaisesRegex(Exception, "^Invalid system instance discovery$"):
                self.parse(files=[bad])
        for missing in ("stdout", "stdout_lines", "stderr", "msg"):
            bad = {key: value for key, value in empty.items() if key != missing}
            self.assertFalse(POLICY.unit_file_discovery_ok(bad))

    def test_discovery_errors_unrelated_and_malformed_output_fail(self):
        for files in (result(rc=42), result("unrelated.service enabled enabled"), result("fixture-alias@one.service"),
                      result("fixture-alias@one.service unknown enabled"), result("fixture-alias@one.service enabled unknown")):
            with self.subTest(files=files), self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
                self.parse(files=files)
        for loaded in (result(rc=42), result("fixture-alias@one.service unknown active running Fixture"),
                       result("fixture-alias@one.service loaded unknown running Fixture")):
            with self.subTest(loaded=loaded), self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
                self.parse(loaded=loaded)

    def test_links_cannot_escape_enablement_or_admission(self):
        for path in ("/etc/systemd/system/../outside/fixture-alias@one.service",
                     "/etc/systemd/system/fixture-alias@one.service",
                     "/etc/systemd/system/multi-user.target.wants/unrelated.service",
                     "/etc/systemd/system/multi-user.target.wants/fixture-alias@.service"):
            with self.subTest(path=path), self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
                self.parse(links={"files": [{"path": path}]})
        with self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
            self.parse(links={"files": [], "skipped_paths": {"/etc/systemd/system": "unreadable"}})

    def test_bounds_and_redacted_errors(self):
        with self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
            self.parse(files=result(*(["fixture-alias@one.service enabled enabled"] * 129)))
        with self.assertRaisesRegex(Exception, "Invalid system instance discovery") as caught:
            self.parse(files=result("SYNTHETIC_SECRET_SENTINEL"))
        self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", str(caught.exception))

    def test_firewall_zone_schema(self):
        self.assertTrue(POLICY.firewall_zones("public internal\n"))
        for value in (None, "", "public public", "public; command", "../escape"):
            with self.subTest(value=value), self.assertRaisesRegex(Exception, "Invalid firewall zone discovery"):
                POLICY.firewall_zones(value)

    def test_missing_definition_plans_preserve_all_names(self):
        files = result("fixture-alias@.service disabled enabled")
        loaded = result("fixture-alias@failed.home.service not-found failed failed Fixture",
                        "fixture-alias@running.home.service not-found active running Fixture",
                        "fixture-alias@inactive.home.service not-found inactive dead Fixture",
                        "fixture-alias@defined.home.service loaded active running Fixture")
        links = {"files": [{"path": "/etc/systemd/system/multi-user.target.wants/fixture-alias@stale.home.service"}]}
        arguments = (files, loaded, links, RETIREMENT)
        self.assertEqual(len(POLICY.retired_instances(*arguments)), 5)
        self.assertEqual(POLICY.retired_instances(*arguments, "defined"),
                         ["fixture-alias@defined.home.service", "fixture-alias@stale.home.service"])
        self.assertEqual(POLICY.retired_instances(*arguments, "missing-running"),
                         ["fixture-alias@running.home.service"])
        self.assertEqual(POLICY.retired_instances(*arguments, "links"), [links["files"][0]["path"]])
        self.assertEqual(POLICY.retired_instances(result(), result(), links, RETIREMENT, "defined"), [])
        for mode in ("invalid", None):
            with self.assertRaisesRegex(Exception, "Invalid system instance discovery"):
                POLICY.retired_instances(*arguments, mode)


if __name__ == "__main__":
    unittest.main()
