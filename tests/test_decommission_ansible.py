"""Actual isolated Ansible launcher with finite controller-only backend doubles.

The source play/role admission, loops, conditions, registrations and handlers
run normally. Copied backend module calls are replaced with one test action;
no production module, SSH, sudo, inventory, vault or host backend is reached.
Set ANSIBLE_TEST_COLLECTIONS to a pinned worker-owned collection directory.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {"ansible.builtin.command", "ansible.builtin.find", "ansible.builtin.file",
            "ansible.builtin.setup",
            "ansible.builtin.systemd", "ansible.builtin.service_facts",
            "ansible.posix.firewalld", "community.general.ufw"}
CONTROLLER = {"ansible.builtin.assert", "ansible.builtin.set_fact",
              "ansible.builtin.include_tasks", "ansible.builtin.import_tasks"}
RULE = 'rule family="ipv4" source address="192.0.2.0/24" port port="5353" protocol="udp" accept'
TEMPLATE = "/etc/systemd/system/avahi-alias@.service"
UNIT = "avahi-alias@stale.home.service"


def state(backend="firewalld", clean=False):
    return {"backend": backend, "unit_files": [] if clean else ["avahi-alias@.service"],
            "units": {} if clean else {UNIT: {"running": True, "enabled": True},
                                       "avahi-alias@loaded.home.service": {"running": True, "enabled": False},
                                       "avahi-daemon.service": {"running": True, "enabled": True},
                                       "unrelated.service": {"running": True, "enabled": True}},
            "links": [] if clean else ["/etc/systemd/system/multi-user.target.wants/" + UNIT],
            "files": ["/etc/systemd/system/unrelated.service"] + ([] if clean else [TEMPLATE]),
            "firewalld": {"public": ["unrelated-rule"] + ([] if clean else [RULE]),
                          "internal": [] if clean else [RULE]},
            "ufw": [{"from_ip": "198.51.100.0/24", "port": "22", "proto": "tcp"}]
                   + ([] if clean else [{"from_ip": "192.0.2.0/24", "port": "5353", "proto": "udp"}]),
            "events": []}


def adapt(tasks):
    for task in tasks:
        for section in ("block", "rescue", "always"):
            if section in task:
                adapt(task[section])
        keys = [key for key in task if key.startswith("ansible.") or key.startswith("community.")]
        if len(keys) != 1 or keys[0] not in BACKENDS | CONTROLLER:
            raise AssertionError("unclassified fixture task")
        module = keys[0]
        if module in BACKENDS:
            args = task.pop(module)
            task["fixture_backend"] = {"original_module": module, "original_args": args}
            task["become"] = False
    return tasks


class AnsibleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="decommission-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        shutil.copytree(ROOT / "roles/decommissioned_services", self.work / "roles/decommissioned_services")
        shutil.copytree(ROOT / "playbooks", self.work / "playbooks")
        (self.work / "action_plugins").mkdir()
        shutil.copy(ROOT / "tests/fixtures/decommission_backend.py", self.work / "action_plugins/fixture_backend.py")
        for folder in ("tasks", "handlers"):
            for file in (self.work / "roles/decommissioned_services" / folder).glob("*.yml"):
                file.write_text(yaml.safe_dump(adapt(yaml.safe_load(file.read_text())), sort_keys=False))
        (self.work / "roles/base/tasks").mkdir(parents=True)
        (self.work / "roles/base/tasks/main.yml").write_text(yaml.safe_dump([
            {"name": "Synthetic base marker", "fixture_backend": {"original_module": "base", "original_args": {}}}]))
        # Later factual gathers and unrelated plays are not this cleanup fixture.
        # The actual first preflight play, including its barrier, is unchanged.
        site = yaml.safe_load((self.work / "playbooks/site.yml").read_text())[:3]
        for play in site[1:]:
            play["gather_facts"] = False
        (self.work / "playbooks/site.yml").write_text(yaml.safe_dump(site, sort_keys=False))
        self.paths = {name: self.work / (name + ".json") for name in ("one", "two")}
        for path in self.paths.values():
            path.write_text(json.dumps(state()))
        collections = os.environ.get("ANSIBLE_TEST_COLLECTIONS", "")
        self.assertTrue(collections and Path(collections).is_dir(), "pinned test collections required")
        (self.work / "ansible.cfg").write_text(
            "[defaults]\ninventory=inventory.yml\nroles_path=roles\naction_plugins=action_plugins\n"
            + "collections_path=" + collections + "\nretry_files_enabled=False\n"
            + "[privilege_escalation]\nbecome=False\n")
        self.inventory()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.work),
                    "ANSIBLE_CONFIG": str(self.work / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(self.work / "local-temp"),
                    "ANSIBLE_REMOTE_TEMP": str(self.work / "remote-temp"),
                    "ANSIBLE_NOCOLOR": "1"}
        self.logs = []

    def inventory(self, overrides=None, default_subnet=False):
        hosts = {name: {"ansible_connection": "local", "ansible_become": False,
                        "ansible_python_interpreter": os.sys.executable,
                        "fixture_state_file": str(path), "lan_subnet": "192.0.2.0/24"}
                 for name, path in self.paths.items()}
        if default_subnet:
            # Select only the reviewed public default, never load inventory or
            # other group vars into the isolated Ansible invocation.
            with (ROOT / "inventory/group_vars/all/vars.yml").open() as source:
                declaration = next(line for line in source if line.startswith("lan_subnet:"))
            default = yaml.safe_load(declaration)["lan_subnet"]
            for host in hosts.values():
                host["lan_subnet"] = default
        for name, values in (overrides or {}).items():
            hosts[name].update(values)
        (self.work / "inventory.yml").write_text(yaml.safe_dump({"all": {"hosts": hosts}}))

    def run_play(self, *extra, success=True):
        result = subprocess.run(["ansible-playbook", "playbooks/site.yml", *extra],
                                cwd=self.work, env=self.env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        self.logs.append(result.stdout)
        self.assertEqual(result.returncode == 0, success, result.stdout[-4000:])
        self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", result.stdout)
        return result.stdout

    def read(self, name="one"):
        return json.loads(self.paths[name].read_text())

    def network_reads(self, name):
        path = self.paths[name].with_suffix(".network-reads")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_actual_default_subnet_uses_fresh_networking_on_every_host(self):
        self.inventory(default_subnet=True)
        self.run_play()
        for name in self.paths:
            self.assertIn("base", self.read(name)["events"])
            self.assertEqual(self.read(name)["firewalld"], {"public": ["unrelated-rule"], "internal": []})
            reads = self.network_reads(name)
            self.assertEqual(len(reads), 1)
            self.assertEqual(reads[0]["gather_subset"], ["!all", "!min", "default_ipv4"])
            self.assertEqual(reads[0]["filter"], ["ansible_default_ipv4"])

    def test_default_ignores_inventory_network_facts(self):
        self.inventory({name: {"ansible_facts": {"default_ipv4": {"network": "203.0.113.0"}}}
                        for name in self.paths}, default_subnet=True)
        self.run_play()
        for name in self.paths:
            self.assertEqual(self.read(name)["firewalld"], {"public": ["unrelated-rule"], "internal": []})

    def test_default_ignores_extra_vars_network_facts(self):
        self.inventory(default_subnet=True)
        self.run_play("-e", json.dumps({"ansible_facts": {
            "default_ipv4": {"network": "203.0.113.0"}},
            "ansible_default_ipv4": {"network": "198.51.100.0"}}))
        for name in self.paths:
            self.assertEqual(self.read(name)["firewalld"], {"public": ["unrelated-rule"], "internal": []})

    def test_networking_registration_override_stops_before_reads_on_every_host(self):
        forged = {"ansible_facts": {"ansible_default_ipv4": {"network": "192.0.2.0"}},
                  "msg": "SYNTHETIC_SECRET_SENTINEL"}
        for source in ("inventory", "extra"):
            with self.subTest(source=source):
                self.inventory({"two": {"_homelab_lifecycle_network": forged}}
                               if source == "inventory" else None, default_subnet=True)
                args = ("-e", json.dumps({"_homelab_lifecycle_network": forged})) if source == "extra" else ()
                before = {name: path.read_text() for name, path in self.paths.items()}
                self.run_play(*args, success=False)
                self.assertEqual(before, {name: path.read_text() for name, path in self.paths.items()})
                for name in self.paths:
                    self.assertEqual(self.network_reads(name), [])

    def test_invalid_missing_and_failed_networking_stops_every_host(self):
        cases = [{"networking_facts": {}},
                 {"networking_facts": {"ansible_default_ipv4": {}}},
                 {"networking_facts": {"ansible_default_ipv4": {"network": "SYNTHETIC_SECRET_SENTINEL"}}},
                 {"networking_facts": {"ansible_default_ipv4": {"network": ["192.0.2.0"]}}},
                 {"setup_failure": True}]
        for default in (True, False):
            self.inventory(default_subnet=default)
            for fixture in cases:
                with self.subTest(fixture=fixture, default=default):
                    for name, path in self.paths.items():
                        path.write_text(json.dumps({**state(), **(fixture if name == "two" else {})}))
                    before = {name: path.read_text() for name, path in self.paths.items()}
                    self.run_play(success=False)
                    self.assertEqual(before, {name: path.read_text() for name, path in self.paths.items()})

    def test_networking_default_honors_host_and_explicit_subnet_precedence(self):
        for source in ("host", "explicit"):
            with self.subTest(source=source):
                for path in self.paths.values():
                    path.write_text(json.dumps({**state(), "networking_facts": {
                        "ansible_default_ipv4": {"network": "198.51.100.0"}}}))
                values = {"host_lan_subnet": "192.0.2.0/24"} if source == "host" else {
                    "lan_subnet": "192.0.2.0/24", "host_lan_subnet": "203.0.113.0/24"}
                self.inventory({name: values for name in self.paths}, default_subnet=True)
                self.run_play()
                for name in self.paths:
                    self.assertEqual(self.read(name)["firewalld"], {"public": ["unrelated-rule"], "internal": []})

    def test_actual_default_check_diff_reads_networking_without_mutation(self):
        self.inventory(default_subnet=True)
        before = {name: path.read_text() for name, path in self.paths.items()}
        self.run_play("--check", "--diff")
        self.assertEqual(before, {name: path.read_text() for name, path in self.paths.items()})
        for name in self.paths:
            self.assertEqual(len(self.network_reads(name)), 1)

    def test_syntax_and_real_valid_tagged_admission(self):
        self.run_play("--syntax-check")
        self.run_play()
        self.assertIn("base", self.read()["events"])

    def test_inventory_cannot_replace_source_context(self):
        self.inventory({"one": {"homelab_active_system_services": "inventory-invalid",
                                "homelab_lifecycle_source": "inventory-invalid"}})
        self.run_play()
        self.assertIn("base", self.read()["events"])

    def test_multihost_invalid_argument_stops_every_host_before_base(self):
        self.run_play("-e", json.dumps({"homelab_active_system_services": "SYNTHETIC_SECRET_SENTINEL"}), success=False)
        for name in self.paths:
            self.assertEqual(self.read(name)["events"], [])

    def test_one_invalid_host_stops_valid_host(self):
        self.inventory({"two": {"lan_subnet": "invalid-source"}})
        self.run_play(success=False)
        for name in self.paths:
            self.assertEqual(self.read(name)["events"], [])

    def test_extra_vars_retirement_and_protection_drift_rejected(self):
        for variable in ("homelab_decommissioned_services", "homelab_preserved_system_units"):
            self.run_play("-e", json.dumps({variable: []}), success=False)
            self.assertEqual(self.read()["events"], [])

    def test_template_loaded_enabled_and_stale_instance_cleanup(self):
        self.run_play()
        result = self.read()
        self.assertNotIn(TEMPLATE, result["files"])
        self.assertEqual(result["links"], [])
        for name, value in result["units"].items():
            expected = {"running": False, "enabled": False} if name.startswith("avahi-alias@") else {"running": True, "enabled": True}
            self.assertEqual({key: value[key] for key in expected}, expected)
        self.assertNotIn("unit:avahi-alias@.service", result["events"])
        self.assertIn("/etc/systemd/system/unrelated.service", result["files"])
        self.assertEqual(result["firewalld"], {"public": ["unrelated-rule"], "internal": []})
        second = self.run_play()
        self.assertRegex(second, r"changed=0")
        after = self.read()
        for key in result.keys() - {"events"}:
            self.assertEqual(after[key], result[key])

    def test_check_diff_and_clean_host_are_non_mutating(self):
        before = {name: path.read_text() for name, path in self.paths.items()}
        self.run_play("--check", "--diff")
        self.assertEqual(before, {name: path.read_text() for name, path in self.paths.items()})
        for path in self.paths.values():
            path.write_text(json.dumps(state(clean=True)))
        output = self.run_play()
        self.assertRegex(output, r"changed=0")
        self.assertEqual(self.read()["files"], ["/etc/systemd/system/unrelated.service"])

    def test_no_matching_unit_files_is_a_clean_host_in_apply_and_check(self):
        for path in self.paths.values():
            path.write_text(json.dumps(state(clean=True)))
        before = {name: self.read(name) for name in self.paths}
        for options in (("--check", "--diff"), (), ()):
            with self.subTest(options=options):
                self.assertRegex(self.run_play(*options), r"changed=0")
                for name in self.paths:
                    after = self.read(name)
                    self.assertEqual({key: value for key, value in after.items() if key != "events"},
                                     {key: value for key, value in before[name].items() if key != "events"})
                    self.assertFalse(any(event == "reload" or event.startswith(("unit:", "native-stop:"))
                                         for event in after["events"]))

    def test_nonempty_or_other_failed_discovery_never_cleans_up(self):
        cases = [
            ("list-unit-files", {"rc": 1, "stdout": "", "stderr": "", "msg": "Error executing command."}),
            ("list-unit-files", {"rc": 1, "stdout": "", "stderr": "SYNTHETIC_SECRET_SENTINEL"}),
            ("list-unit-files", {"rc": 1, "stdout": "avahi-alias@.service enabled enabled", "stderr": ""}),
            ("list-unit-files", {"rc": 42, "stdout": "", "stderr": ""}),
            ("list-units", {"rc": 1, "stdout": "", "stderr": ""}),
        ]
        for command, response in cases:
            with self.subTest(command=command, response=response):
                for path in self.paths.values():
                    fixture = state()
                    fixture["discovery_results"] = {command: response}
                    path.write_text(json.dumps(fixture))
                before = {name: self.read(name) for name in self.paths}
                self.run_play(success=False)
                for name in self.paths:
                    after = self.read(name)
                    self.assertEqual(after["events"], ["base"])
                    for key in before[name].keys() - {"events"}:
                        self.assertEqual(after[key], before[name][key])

    def test_native_command_module_empty_nonzero_result(self):
        # Exercise the real command module's fail_json/exception metadata,
        # without invoking systemctl or connecting to a production host.
        path = self.work / "roles/decommissioned_services/tasks/converge.yml"
        tasks = yaml.safe_load(path.read_text())
        tasks[0].pop("fixture_backend")
        tasks[0]["ansible.builtin.command"] = {
            "argv": [os.sys.executable, "-c", "raise SystemExit(1)"]}
        path.write_text(yaml.safe_dump(tasks, sort_keys=False))
        for state_path in self.paths.values():
            state_path.write_text(json.dumps(state(clean=True)))
        self.assertRegex(self.run_play(), r"changed=0")

    def test_ufw_exact_removal_and_unavailable_backend(self):
        for backend in ("ufw", "none"):
            for path in self.paths.values():
                path.write_text(json.dumps(state(backend=backend)))
            self.run_play()
            result = self.read()
            expected = state(backend)["ufw"][:1] if backend == "ufw" else state(backend)["ufw"]
            self.assertEqual(result["ufw"], expected)

    def test_discovery_failure_is_not_a_clean_host(self):
        for command in ("list-unit-files", "list-units", "--get-zones"):
            for path in self.paths.values():
                fixture = state()
                fixture["discovery_failure"] = command
                path.write_text(json.dumps(fixture))
            self.run_play(success=False)
            self.assertEqual(self.read()["events"], ["base"])

    def test_backend_failure_propagates_without_retry(self):
        for path in self.paths.values():
            fixture = state()
            fixture["backend_failure"] = True
            path.write_text(json.dumps(fixture))
        self.run_play(success=False)
        self.assertIn(RULE, self.read()["firewalld"]["public"])

    def test_missing_source_and_whole_context_override_fail_closed(self):
        self.run_play("-e", json.dumps({"homelab_lifecycle_source": {"active_system_services": [],
                      "retired_system_services": [], "preserved_system_units": []}}), success=False)
        self.assertEqual(self.read()["events"], [])
        (self.work / "playbooks/vars/system_lifecycle.yml").unlink()
        self.run_play(success=False)
        for name in self.paths:
            self.assertEqual(self.read(name)["events"], [])

    def test_valid_and_invalid_actual_filter_values(self):
        invalid = [{"name": "unsafe", "unit_globs": ["*.service"], "unit_files": [],
                    "firewalld_rules": [], "ufw_rules": []}]
        self.run_play("-e", json.dumps({"homelab_decommissioned_services": invalid}), success=False)
        self.assertEqual(self.read()["events"], [])
        duplicate = [{"name": "first", "unit_globs": ["different.service"], "unit_files": []},
                     {"name": "second", "unit_globs": ["different.service"], "unit_files": []}]
        self.run_play("-e", json.dumps({"homelab_active_system_services": duplicate}), success=False)
        self.assertEqual(self.read()["events"], [])

    def test_pinned_backend_module_option_interfaces(self):
        result = subprocess.run(["ansible-doc", "--json", *sorted(BACKENDS)], cwd=self.work,
                                env=self.env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0)
        interfaces = json.loads(result.stdout)
        for folder in ("tasks", "handlers"):
            for path in (ROOT / "roles/decommissioned_services" / folder).glob("*.yml"):
                for task in yaml.safe_load(path.read_text()):
                    for module in BACKENDS & task.keys():
                        args = task[module] or {}
                        self.assertIsInstance(args, dict)
                        options = interfaces[module]["doc"].get("options", {})
                        accepted = set(options)
                        for option in options.values():
                            accepted.update(option.get("aliases", []))
                        self.assertLessEqual(set(args), accepted, module)

    def test_actual_user_destinations_and_generated_runner_unit(self):
        destinations = []
        for role in ("base", "quadlets", "forgejo_runner"):
            tasks = yaml.safe_load((ROOT / "roles" / role / "tasks/main.yml").read_text())
            for task in tasks:
                for module in ("ansible.builtin.template", "ansible.builtin.copy"):
                    args = task.get(module, {})
                    src = args.get("src", "")
                    if args and (src.endswith((".container.j2", ".build.j2", ".override.conf.j2", ".network")) or task.get("loop") == ["homelab.network"]):
                        destinations.append(args["dest"])
        self.assertEqual(len(destinations), 6)
        values = {"quadlet_dir": str(self.work / ".config/containers/systemd"),
                  "homelab_user_home": str(self.work),
                  "forgejo_runner_quadlet_dir": str(self.work / "runner/.config/containers/systemd"),
                  "forgejo_runner_image": "example.invalid/runner@sha256:" + "a" * 64,
                  "forgejo_runner_uid": 1000, "forgejo_runner_data_dir": str(self.work / "runner/data"),
                  "forgejo_runner_workdir": str(self.work / "runner/work"), "item": "fixture"}
        tasks = [{"ansible.builtin.assert": {"that": "'/.config/' in candidate and '/etc/systemd/system' not in candidate"},
                  "loop": destinations, "loop_control": {"loop_var": "candidate"}},
                 {"ansible.builtin.template": {"src": str(ROOT / "roles/forgejo_runner/templates/forgejo-runner.container.j2"),
                                               "dest": str(self.work / "runner.container")}}]
        play = [{"hosts": "one", "gather_facts": False, "vars": values, "tasks": tasks}]
        file = self.work / "playbooks/render.yml"
        file.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(["ansible-playbook", "playbooks/render.yml"], cwd=self.work,
                                env=self.env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:])
        rendered = (self.work / "runner.container").read_text()
        self.assertIn("WantedBy=default.target", rendered)
        self.assertIn("/run/user/1000/podman/podman.sock", rendered)
        self.assertNotIn("multi-user.target", rendered)

    def test_derived_target_override_is_ineffective_and_reserved_data_rejected(self):
        self.run_play("-e", json.dumps({"homelab_retired_instances": ["avahi-daemon.service"]}))
        self.assertEqual(self.read()["units"]["avahi-daemon.service"], {"running": True, "enabled": True})
        for path in self.paths.values():
            path.write_text(json.dumps(state()))
        for variable in ("_homelab_lifecycle_files", "_homelab_lifecycle_loaded",
                         "_homelab_lifecycle_links", "_homelab_lifecycle_zones"):
            self.run_play("-e", json.dumps({variable: {}}), success=False)
            for name in self.paths:
                self.assertEqual(self.read(name)["events"], [])

    def test_actual_backend_result_wins_over_global_fact_shadowing(self):
        shadow = {"services": {"firewalld.service": {"state": "stopped"},
                               "ufw.service": {"state": "stopped"}}}
        for backend in ("firewalld", "ufw"):
            for origin in ("inventory", "extra-vars"):
                for path in self.paths.values():
                    path.write_text(json.dumps(state(backend=backend)))
                self.inventory({name: {"ansible_facts": shadow} for name in self.paths}
                               if origin == "inventory" else {})
                self.run_play(*(["-e", json.dumps({"ansible_facts": shadow})]
                                if origin == "extra-vars" else []))
                result = self.read()
                self.assertIn("firewall", result["events"])
                if backend == "firewalld":
                    self.assertNotIn(RULE, result["firewalld"]["public"])
                    self.assertNotIn(RULE, result["firewalld"]["internal"])
                else:
                    self.assertEqual(result["ufw"], state(backend)["ufw"][:1])

    def test_backend_registration_override_fails_before_base(self):
        for name in self.paths:
            self.inventory({name: {"_homelab_lifecycle_backends": {}}})
            self.run_play(success=False)
            for host in self.paths:
                self.assertEqual(self.read(host)["events"], [])
        self.inventory()
        self.run_play("-e", json.dumps({"_homelab_lifecycle_backends": {}}), success=False)
        for host in self.paths:
            self.assertEqual(self.read(host)["events"], [])

    def test_missing_definition_residents_and_stale_links_converge(self):
        for active in ("inactive", "failed", "active"):
            for linked in (True, False):
                for path in self.paths.values():
                    fixture = state()
                    fixture["unit_files"] = []
                    fixture["files"].remove(TEMPLATE)
                    fixture["links"] = fixture["links"] if linked else []
                    fixture["units"] = {UNIT: {"load_state": "not-found", "active_state": active,
                                              "running": active == "active", "enabled": linked},
                                        "avahi-daemon.service": {"running": True, "enabled": True}}
                    path.write_text(json.dumps(fixture))
                before = {name: path.read_text() for name, path in self.paths.items()}
                self.run_play("--check", "--diff")
                self.assertEqual(before, {name: path.read_text() for name, path in self.paths.items()})
                self.run_play()
                result = self.read()
                self.assertFalse(result["units"][UNIT]["running"])
                self.assertFalse(result["units"][UNIT]["enabled"])
                self.assertEqual(result["links"], [])
                self.assertNotIn(TEMPLATE, result["files"])
                self.assertIn("/etc/systemd/system/unrelated.service", result["files"])
                self.assertEqual(result["firewalld"], {"public": ["unrelated-rule"], "internal": []})
                self.assertEqual(result["units"]["avahi-daemon.service"], {"running": True, "enabled": True})
                self.assertNotIn("unit:" + UNIT, result["events"])
                self.assertEqual(result["events"].count("native-stop:" + UNIT), int(active == "active"))
                self.assertRegex(self.run_play(), r"changed=0")
                after = self.read()
                for key in result.keys() - {"events"}:
                    self.assertEqual(after[key], result[key])

    def test_stale_link_without_resident_or_definition(self):
        unrelated = "/etc/systemd/system/multi-user.target.wants/unrelated.service"
        for path in self.paths.values():
            fixture = state(clean=True)
            fixture["links"] = ["/etc/systemd/system/multi-user.target.wants/" + UNIT, unrelated]
            path.write_text(json.dumps(fixture))
        self.run_play()
        self.assertEqual(self.read()["links"], [unrelated])
        self.assertNotIn("unit:" + UNIT, self.read()["events"])
        self.assertRegex(self.run_play(), r"changed=0")

    def test_missing_definition_native_stop_failure_stops_cleanup(self):
        for path in self.paths.values():
            fixture = state()
            fixture["units"][UNIT].update(load_state="not-found", active_state="active")
            fixture["native_stop_failure"] = True
            path.write_text(json.dumps(fixture))
        self.run_play(success=False)
        self.assertIn(TEMPLATE, self.read()["files"])
        self.assertIn(RULE, self.read()["firewalld"]["public"])
        self.assertTrue(self.read()["links"])


if __name__ == "__main__":
    unittest.main()
