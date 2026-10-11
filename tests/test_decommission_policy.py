"""Synthetic policy admission; no inventory, discovery or backend access."""
import copy
import importlib.util
from pathlib import Path
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / "roles/decommissioned_services/filter_plugins/policy.py"


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("decommission_policy", PLUGIN)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.validate = staticmethod(module.validate_policy)

    def setUp(self):
        self.retired = [{"name": "alias", "unit_globs": ["fixture-alias@*.service"],
                         "unit_files": ["/etc/systemd/system/fixture-alias@.service"],
                         "firewalld_rules": [{"rich_rule": 'rule family="ipv4" source address="192.0.2.0/24" port port="5353" protocol="udp" accept'}],
                         "ufw_rules": [{"from_ip": "192.0.2.0/24", "port": "5353", "proto": "udp"}]}]
        self.preserved = ["fixture-daemon.service"]

    def rejects(self, retired=None, active=None, preserved=None):
        with self.assertRaisesRegex(Exception, "Invalid system lifecycle policy"):
            self.validate(self.retired if retired is None else retired,
                          [] if active is None else active,
                          self.preserved if preserved is None else preserved)

    def test_valid_owned_template_and_empty_retirement(self):
        self.assertTrue(self.validate(self.retired, [], self.preserved))
        self.assertTrue(self.validate([], [], self.preserved))

    def test_top_level_types_and_missing_context(self):
        for bad in (None, "", {}, [None]):
            with self.subTest(bad=bad):
                self.rejects(retired=bad if bad is not None else "null")
                with self.assertRaisesRegex(Exception, "Invalid system lifecycle policy"):
                    self.validate(self.retired, bad, self.preserved)

    def test_unsafe_patterns_and_paths(self):
        for pattern in ("*", "*.service", "", "fixture*", "ssh*.service", "fixture@?.service", "fixture@*.service\n"):
            bad = copy.deepcopy(self.retired)
            bad[0]["unit_globs"] = [pattern]
            self.rejects(retired=bad)
        for path in ("/etc/systemd/system/../other.service", "/tmp/fixture.service", "/etc/systemd/system", "/etc/systemd/system/unrelated.service"):
            bad = copy.deepcopy(self.retired)
            bad[0]["unit_files"] = [path]
            self.rejects(retired=bad)

    def test_unknown_fields_and_malformed_rules(self):
        for key in ("packages", "data", "command", "hooks"):
            bad = copy.deepcopy(self.retired)
            bad[0][key] = []
            self.rejects(retired=bad)
        for field, value in (("proto", "any"), ("port", "0"), ("port", "65536"), ("port", "53:5353"), ("from_ip", "any"), ("from_ip", "192.0.2.1/24"), ("unknown", True)):
            bad = copy.deepcopy(self.retired)
            bad[0]["ufw_rules"][0][field] = value
            self.rejects(retired=bad)
        for rule in ("", 12, 'rule family="ipv6" source address="192.0.2.0/24" port port="5353" protocol="udp" accept', self.retired[0]["firewalld_rules"][0]["rich_rule"] + " log"):
            bad = copy.deepcopy(self.retired)
            bad[0]["firewalld_rules"] = [{"rich_rule": rule}]
            self.rejects(retired=bad)

    def test_conflicts_ignore_display_name(self):
        for active in ([{"name": "different", "unit_globs": ["fixture-alias@*.service"], "unit_files": []}],
                       [{"name": "different", "unit_globs": ["fixture-alias@live.service"], "unit_files": []}],
                       [{"name": "different", "unit_globs": [], "unit_files": self.retired[0]["unit_files"]}],
                       [{"name": "alias", "unit_globs": ["other.service"], "unit_files": []}]):
            self.rejects(active=active)
        self.assertTrue(self.validate(self.retired, [{"name": "other", "unit_globs": ["other.service"], "unit_files": []}], self.preserved))

    def test_protection_and_redacted_failure(self):
        bad = copy.deepcopy(self.retired)
        bad[0]["unit_globs"] = ["fixture-daemon.service"]
        bad[0]["unit_files"] = []
        self.rejects(retired=bad)
        bad[0]["command"] = "SYNTHETIC_SECRET_SENTINEL"
        try:
            self.validate(bad, [], self.preserved)
        except Exception as error:
            self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", str(error))
        else:
            self.fail("unsafe input accepted")

    def test_overlapping_records_with_different_names(self):
        duplicate = copy.deepcopy(self.retired[0])
        duplicate["name"] = "another"
        self.rejects(retired=self.retired + [duplicate])
        for left, right in (("fixture-alias@*.service", "fixture-alias@one.service"),
                            ("fixture-alias@*.service", "fixture-alias@*.service"),
                            ("fixture.service", "fixture.service")):
            active = [{"name": "first", "unit_globs": [left], "unit_files": []},
                      {"name": "second", "unit_globs": [right], "unit_files": []}]
            self.rejects(active=active)
        active = [{"name": "first", "unit_globs": ["other.service"], "unit_files": []},
                  {"name": "second", "unit_globs": [], "unit_files": ["/etc/systemd/system/other.service"]}]
        self.rejects(active=active)

    def test_tagged_dataloader_values_and_strict_nested_types(self):
        from ansible.parsing.dataloader import DataLoader
        import yaml
        retired = DataLoader().load(yaml.safe_dump(self.retired))
        active = DataLoader().load("[]")
        preserved = DataLoader().load(yaml.safe_dump(self.preserved))
        self.assertTrue(self.validate(retired, active, preserved))
        for key in ("unit_globs", "unit_files", "firewalld_rules", "ufw_rules"):
            for value in (None, "invalid", {}, [False]):
                bad = copy.deepcopy(self.retired)
                bad[0][key] = value
                self.rejects(retired=bad)
        for value in (True, [], {}, None):
            bad = copy.deepcopy(self.retired)
            bad[0]["ufw_rules"][0]["port"] = value
            self.rejects(retired=bad)

    def test_null_contexts_duplicates_and_bounds(self):
        for retired, active, protected in ((None, [], self.preserved),
                                           (self.retired, None, self.preserved),
                                           (self.retired, [], None)):
            with self.assertRaisesRegex(Exception, "Invalid system lifecycle policy"):
                self.validate(retired, active, protected)
        self.rejects(retired=self.retired * 129)
        bad = copy.deepcopy(self.retired)
        bad[0]["unit_globs"] *= 2
        self.rejects(retired=bad)


if __name__ == "__main__":
    unittest.main()
