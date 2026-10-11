"""Admission for system-scope lifecycle data, without discovery or mutation."""
import fnmatch
import ipaddress
import re
from ansible.errors import AnsibleFilterError

NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}")
UNIT = re.compile(r"[a-z][a-z0-9_.:-]{2,}(?:@[a-z0-9_.:-]*)?\.service")
FAMILY = re.compile(r"[a-z][a-z0-9_.:-]{2,}@\*\.service")
RULE = re.compile(r'rule family="(ipv[46])" source address="([^"\s]+)" port port="([0-9]+)" protocol="(tcp|udp)" (accept|drop|reject)')
ROOT = "/etc/systemd/system/"


def require(condition):
    if not condition:
        raise ValueError()


def pattern(value):
    require(isinstance(value, str) and len(value) <= 255)
    require(UNIT.fullmatch(value) is not None or FAMILY.fullmatch(value) is not None)
    return value


def unit_file(value):
    require(isinstance(value, str) and value.startswith(ROOT))
    name = value[len(ROOT):]
    require(len(name) <= 255 and UNIT.fullmatch(name) is not None)
    require(".." not in name)
    return name


def sequence(value):
    require(isinstance(value, list) and len(value) <= 128)
    return value


def port(value):
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,4}", value) is not None)
    require(int(value) <= 65535)


def network(value):
    require(isinstance(value, str))
    return ipaddress.ip_network(value, strict=True)


def record(item, retired):
    keys = {"name", "unit_globs", "unit_files"}
    if retired:
        keys |= {"firewalld_rules", "ufw_rules"}
    require(isinstance(item, dict) and set(item) == keys)
    require(isinstance(item["name"], str) and NAME.fullmatch(item["name"]) is not None)
    patterns = sequence(item["unit_globs"])
    files = sequence(item["unit_files"])
    require(bool(patterns) if retired else bool(patterns or files))
    for value in patterns:
        pattern(value)
    for value in files:
        name = unit_file(value)
        if retired:
            require(any(fnmatch.fnmatchcase(name, glob) for glob in patterns))
    require(len(set(patterns)) == len(patterns) and len(set(files)) == len(files))
    if not retired:
        return
    for rule in sequence(item["firewalld_rules"]):
        require(isinstance(rule, dict) and set(rule) == {"rich_rule"})
        require(isinstance(rule["rich_rule"], str))
        match = RULE.fullmatch(rule["rich_rule"])
        require(match is not None)
        family, source, number, _, _ = match.groups()
        require(network(source).version == (4 if family == "ipv4" else 6))
        port(number)
    for rule in sequence(item["ufw_rules"]):
        require(isinstance(rule, dict) and set(rule) == {"from_ip", "port", "proto"})
        network(rule["from_ip"])
        port(rule["port"])
        require(isinstance(rule["proto"], str) and rule["proto"] in ("tcp", "udp"))


def targets(item):
    return item["unit_globs"] + [unit_file(path) for path in item["unit_files"]]


def overlap(first, second):
    # Grammar admits only exact names and one terminal template-instance wildcard.
    # Exact/template intersections are decided with case-sensitive unit matching;
    # two template families overlap iff their literal family names are equal.
    return (first == second or fnmatch.fnmatchcase(first, second)
            or fnmatch.fnmatchcase(second, first))


def validate_policy(retired, active, preserved):
    try:
        sequence(retired)
        sequence(active)
        sequence(preserved)
        for name in preserved:
            require(isinstance(name, str) and UNIT.fullmatch(name) is not None)
        for entries, is_retired in ((retired, True), (active, False)):
            for entry in entries:
                record(entry, is_retired)
            require(len({entry["name"] for entry in entries}) == len(entries))
            for index, entry in enumerate(entries):
                for other in entries[index + 1:]:
                    require(not any(overlap(left, right)
                                    for left in targets(entry) for right in targets(other)))
        for entry in retired:
            old_targets = targets(entry)
            require(not any(fnmatch.fnmatchcase(name, glob)
                            for name in preserved for glob in old_targets))
            for current in active:
                require(entry["name"] != current["name"])
                require(not any(overlap(old, new)
                                for old in old_targets for new in targets(current)))
        return True
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AnsibleFilterError("Invalid system lifecycle policy") from None


def unit_file_discovery_ok(result):
    """systemd 259 returns 1 after successfully listing zero matching files."""
    # Ansible attaches failure/exception metadata even for this expected rc=1;
    # Require its completed-command message too: an OSError EPERM also has
    # rc=1 and empty streams, but reports "Error executing command." instead.
    return (isinstance(result, dict) and not result.get("skipped", False)
            and not result.get("unreachable", False)
            and (result.get("rc") == 0
                 or (result.get("rc") == 1 and result.get("stdout") == ""
                     and result.get("stdout_lines") == [] and result.get("stderr") == ""
                     and result.get("msg") == "The command exited with a non-zero return code.")))


def retired_instances(file_results, loaded_results, links, retired, mode="all"):
    """Validated instance plans; missing definitions require native resident stop."""
    try:
        require(mode in ("all", "defined", "missing-running", "links"))
        sequence(file_results)
        sequence(loaded_results)
        require(len(file_results) == len(retired) == len(loaded_results))
        found = set()
        file_units, link_paths, loaded_states = set(), set(), {}
        for results, loaded in ((file_results, False), (loaded_results, True)):
            for result, entry in zip(results, retired):
                require(isinstance(result, dict))
                require(result.get("rc") == 0 if loaded else unit_file_discovery_ok(result))
                lines = sequence(result["stdout_lines"])
                for line in lines:
                    require(isinstance(line, str) and len(line) <= 2048)
                    fields = line.split()
                    if loaded:
                        require(len(fields) >= 4 and fields[1] in {
                            "loaded", "not-found", "bad-setting", "error", "merged", "masked", "stub"})
                        require(fields[2] in {"active", "reloading", "inactive", "failed", "activating",
                                              "deactivating", "maintenance", "refreshing"})
                        require(re.fullmatch(r"[a-z-]+", fields[3]) is not None)
                    else:
                        require(len(fields) in (2, 3) and fields[1] in {
                            "enabled", "enabled-runtime", "linked", "linked-runtime", "alias", "masked",
                            "masked-runtime", "static", "disabled", "indirect", "generated", "transient", "bad"})
                        require(len(fields) == 2 or fields[2] in {"enabled", "disabled", "-"})
                    name = fields[0]
                    require(UNIT.fullmatch(name) is not None)
                    require(any(fnmatch.fnmatchcase(name, glob) for glob in entry["unit_globs"]))
                    if loaded:
                        state = (fields[1], fields[2])
                        require(name not in loaded_states or loaded_states[name] == state)
                        loaded_states[name] = state
                    else:
                        file_units.add(name)
                    # The file template belongs to retirement, not instance stop/disable.
                    if "@.service" not in name:
                        found.add(name)
        require(isinstance(links, dict) and not links.get("failed", False))
        require(not links.get("skipped_paths", {}))
        for link in sequence(links["files"]):
            require(isinstance(link, dict) and isinstance(link.get("path"), str))
            path = link["path"]
            match = re.fullmatch(r"/(etc|run)/systemd/system/([A-Za-z0-9_.@:-]+\.(?:wants|requires))/([^/]+)", path)
            require(match is not None)
            name = match.group(3)
            require(UNIT.fullmatch(name) is not None and "@.service" not in name)
            require(any(fnmatch.fnmatchcase(name, glob)
                        for entry in retired for glob in entry["unit_globs"]))
            found.add(name)
            link_paths.add(path)
        require(len(found) <= 128)
        if mode == "all":
            return sorted(found)
        if mode == "links":
            return sorted(link_paths)
        defined, running_missing = set(), set()
        for name in found:
            loaded = loaded_states.get(name)
            template = name.split("@")[0] + "@.service" if "@" in name else ""
            if loaded is not None and loaded[0] == "not-found":
                if loaded[1] not in ("inactive", "failed"):
                    running_missing.add(name)
            elif loaded is not None or name in file_units or template in file_units:
                defined.add(name)
        return sorted(defined if mode == "defined" else running_missing)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AnsibleFilterError("Invalid system instance discovery") from None


def firewall_zones(value):
    try:
        require(isinstance(value, str) and len(value) <= 4096)
        names = value.split()
        require(0 < len(names) <= 128 and len(set(names)) == len(names))
        require(all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name) for name in names))
        return True
    except (ValueError, TypeError):
        raise AnsibleFilterError("Invalid firewall zone discovery") from None


def network_fallback(result):
    """Validate only the fresh registered setup result, retaining the /24 default."""
    try:
        require(isinstance(result, dict) and not result.get("failed", False))
        require(not result.get("skipped", False))
        require(not any(key in result for key in ("msg", "exception", "rc")))
        facts = result["ansible_facts"]
        require(isinstance(facts, dict))
        ipv4 = facts["ansible_default_ipv4"]
        require(isinstance(ipv4, dict))
        address = ipv4["network"]
        require(isinstance(address, str) and ipaddress.ip_address(address).version == 4)
        require(network(address + "/24").version == 4)
        return True
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AnsibleFilterError("Invalid system lifecycle networking result") from None


class FilterModule:
    def filters(self):
        return {"homelab_validate_system_lifecycle": validate_policy,
                "homelab_unit_file_discovery_ok": unit_file_discovery_ok,
                "homelab_retired_instances": retired_instances,
                "homelab_firewall_zones": firewall_zones,
                "homelab_validate_network_fallback": network_fallback}
