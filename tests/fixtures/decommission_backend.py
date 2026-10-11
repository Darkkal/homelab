"""Controller-only backend double. No service, firewall, privilege or host I/O.

Only the invocation-owned JSON state file is read/written. Production modules
are replaced in a copied fixture role, never through a production test hook.
"""
import fnmatch
import json
import os
import shlex
from unittest.mock import patch
from pathlib import Path
from ansible.plugins.action import ActionBase


def native_systemd(args, units, links, check_mode=False):
    """Run the pinned native module with every command/host lookup intercepted."""
    from ansible.modules import systemd_service as native

    class Finished(Exception):
        def __init__(self, result):
            self.result = result

    class Module:
        def __init__(self):
            self.params = dict(name=None, state=None, enabled=None, force=None,
                               masked=None, daemon_reload=False, daemon_reexec=False,
                               scope="system", no_block=False)
            self.params.update(args)
            self.check_mode = check_mode

        def get_bin_path(self, *args, **kwargs):
            return "/fixture/systemctl"

        def run_command(self, command, **kwargs):
            tokens = shlex.split(command)
            assert tokens[0] == "/fixture/systemctl"
            name = self.params["name"]
            assert tokens[2] == name and tokens[1] in {"show", "is-enabled", "disable", "stop"}
            value = units.get(name, {"load_state": "not-found", "running": False, "enabled": False})
            if tokens[1] == "show":
                active = value.get("active_state", "active" if value["running"] else "inactive")
                return 0, "LoadState=" + value.get("load_state", "loaded") + "\nActiveState=" + active + "\n", ""
            if tokens[1] == "is-enabled":
                return (0, "enabled\n", "") if value["enabled"] else (1, "disabled\n", "")
            assert not check_mode
            if tokens[1] == "disable":
                value["enabled"] = False
                links[:] = [p for p in links if Path(p).name != name]
            else:
                value["running"] = False
                value.pop("active_state", None)
            return 0, "", ""

        def warn(self, *args, **kwargs):
            pass

        def fail_json(self, **kwargs):
            raise Finished({"failed": True, **kwargs})

        def exit_json(self, **kwargs):
            raise Finished(kwargs)

    module = Module()
    with patch.object(native, "AnsibleModule", return_value=module), \
            patch.object(native, "sysv_exists", return_value=False), \
            patch.object(native, "is_chroot", return_value=False), \
            patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/fixture/runtime"}, clear=True):
        try:
            native.main()
        except Finished as result:
            return result.result
    raise AssertionError("native module did not exit")


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        path = Path(task_vars["fixture_state_file"])
        if not path.parent.name.startswith("decommission-test-") or path.name not in ("one.json", "two.json"):
            return {"failed": True, "msg": "fixture boundary rejected"}
        state = json.loads(path.read_text())
        module = self._task.args["original_module"]
        args = self._task.args["original_args"]
        changed = False
        result = {}
        event = None
        if module == "ansible.builtin.setup":
            # This audit trail records reads separately from backend mutations,
            # including in check mode, without touching the fixture state.
            with path.with_suffix(".network-reads").open("a") as reads:
                reads.write(json.dumps(args) + "\n")
            if state.get("setup_failure"):
                return {"failed": True, "msg": "SYNTHETIC_SECRET_SENTINEL"}
            return {"changed": False, "ansible_facts": state.get("networking_facts", {
                "ansible_default_ipv4": {"network": "192.0.2.0"}})}
        elif module == "base":
            event = "base"
        elif module == "ansible.builtin.command":
            argv = args["argv"]
            if state.get("discovery_failure") == argv[1]:
                return {"failed": True, "rc": 42, "msg": "synthetic discovery failure"}
            if argv[1] in state.get("discovery_results", {}):
                response = state["discovery_results"][argv[1]]
                return {"changed": False, "failed": response["rc"] != 0,
                        "stdout_lines": response["stdout"].splitlines(), **response}
            if argv[:2] == ["systemctl", "list-unit-files"]:
                patterns = argv[5:]
                lines = [name + " enabled enabled" for name in state["unit_files"]
                         if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)]
            elif argv[:2] == ["systemctl", "list-units"]:
                patterns = argv[7:]
                lines = [name + " " + value.get("load_state", "loaded") + " "
                         + value.get("active_state", "active" if value["running"] else "inactive")
                         + (" failed" if value.get("active_state") == "failed" else " running" if value["running"] else " dead") + " Synthetic fixture"
                         for name, value in state["units"].items()
                         if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)]
            elif argv == ["firewall-cmd", "--get-zones"]:
                lines = [" ".join(state["firewalld"])]
            elif len(argv) == 4 and argv[:3] == ["systemctl", "--system", "stop"]:
                if state.get("native_stop_failure"):
                    return {"failed": True, "rc": 42, "msg": "synthetic native stop failure"}
                name = argv[3]
                value = state["units"][name]
                assert value.get("load_state") == "not-found" and value["running"]
                changed = True
                if not self._task.check_mode:
                    value["running"] = False
                    value["active_state"] = "inactive"
                event = "native-stop:" + name
                lines = []
            else:
                return {"failed": True, "msg": "unclassified fixture command"}
            # Native systemctl list-unit-files reports no matches with rc=1
            # and empty output; list-units still succeeds with no matches.
            rc = int(argv[:2] == ["systemctl", "list-unit-files"] and not lines)
            result = {"failed": rc != 0, "rc": rc, "stdout": "\n".join(lines),
                      "stdout_lines": lines, "stderr": ""}
            if rc:
                result["msg"] = "The command exited with a non-zero return code."
        elif module == "ansible.builtin.find":
            result = {"files": [{"path": path} for path in state["links"]
                                if any(fnmatch.fnmatchcase(Path(path).name, pattern) for pattern in args["patterns"])], "skipped_paths": {}}
        elif module == "ansible.builtin.service_facts":
            result = {"ansible_facts": {"services": {
                "firewalld.service": {"state": "running" if state["backend"] == "firewalld" else "stopped"},
                "ufw.service": {"state": "running" if state["backend"] == "ufw" else "stopped"}}}}
        elif module == "ansible.builtin.systemd":
            if args.get("daemon_reload"):
                event = "reload"
                if not self._task.check_mode:
                    for name, value in state["units"].items():
                        if "@" in name and name.split("@")[0] + "@.service" not in state["unit_files"]:
                            value["load_state"] = "not-found"
            else:
                name = args["name"]
                if "@.service" in name or args.get("scope") != "system":
                    return {"failed": True, "msg": "invalid concrete fixture target"}
                result = native_systemd(args, state["units"], state["links"], self._task.check_mode)
                if result.get("failed"):
                    return result
                changed = result["changed"]
                event = "unit:" + name
        elif module == "ansible.builtin.file":
            path_name = args["path"]
            if args["state"] != "absent":
                return {"failed": True, "msg": "invalid fixture file operation"}
            changed = path_name in state["files"] or path_name in state["links"]
            if not self._task.check_mode:
                state["files"] = [p for p in state["files"] if p != path_name]
                if path_name in state["links"]:
                    state["links"].remove(path_name)
                    name = Path(path_name).name
                    if name in state["units"]:
                        state["units"][name]["enabled"] = any(Path(p).name == name for p in state["links"])
                state["unit_files"] = [p for p in state["unit_files"] if p != Path(path_name).name]
            event = "file:" + path_name
        elif module in ("ansible.posix.firewalld", "community.general.ufw"):
            if state.get("backend_failure"):
                return {"failed": True, "msg": "synthetic backend failure"}
            if module == "ansible.posix.firewalld":
                rules = state["firewalld"][args["zone"]]
                target = args["rich_rule"]
            else:
                rules = state["ufw"]
                target = {"from_ip": args["from_ip"], "port": args["port"], "proto": args["proto"]}
            changed = target in rules
            if changed and not self._task.check_mode:
                rules.remove(target)
            event = "firewall"
        else:
            return {"failed": True, "msg": "unclassified fixture backend"}
        if not self._task.check_mode:
            if event:
                state["events"].append(event)
            path.write_text(json.dumps(state))
        return {"changed": changed, **result}
