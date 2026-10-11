"""Fresh setup-result admission; all addresses and failures are synthetic."""
import copy
import importlib.util
from pathlib import Path
import unittest

from ansible.parsing.dataloader import DataLoader

SPEC = importlib.util.spec_from_file_location(
    "lifecycle_network", Path(__file__).resolve().parents[1]
    / "roles/decommissioned_services/filter_plugins/policy.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
VALID = {"ansible_facts": {"ansible_default_ipv4": {"network": "192.0.2.0"}}}


class NetworkTests(unittest.TestCase):
    def test_plain_and_ansible_tagged_results(self):
        self.assertTrue(POLICY.network_fallback(VALID))
        self.assertTrue(POLICY.network_fallback(DataLoader().load(
            'ansible_facts: {ansible_default_ipv4: {network: "192.0.2.0"}}')))

    def test_absent_malformed_and_noncanonical_fallbacks(self):
        for value in (None, "", {}, {"ansible_facts": {}},
                      {"ansible_facts": {"ansible_default_ipv4": None}}):
            with self.assertRaisesRegex(Exception, "Invalid system lifecycle networking result"):
                POLICY.network_fallback(value)
        for address in (None, [], "192.0.2.1", "2001:db8::", "SYNTHETIC_SECRET_SENTINEL"):
            result = copy.deepcopy(VALID)
            result["ansible_facts"]["ansible_default_ipv4"]["network"] = address
            with self.assertRaisesRegex(Exception, "^Invalid system lifecycle networking result$"):
                POLICY.network_fallback(result)

    def test_failure_metadata_with_partial_facts_is_rejected(self):
        # failed_when:false redacts native setup failures; fail_json's message
        # must still reject a result even if partial valid facts are present.
        for metadata in ({"failed": True}, {"skipped": True},
                         {"msg": "SYNTHETIC_SECRET_SENTINEL", "failed": False},
                         {"exception": "SYNTHETIC_SECRET_SENTINEL"}, {"rc": 42}):
            with self.assertRaisesRegex(Exception, "^Invalid system lifecycle networking result$"):
                POLICY.network_fallback({**VALID, **metadata})


if __name__ == "__main__":
    unittest.main()
