"""Finite source audit, not an Ansible interpreter or host inventory.

Run: python -m unittest discover -s tests -p test_decommission_source_audit.py
Only site.yml, explicitly classified role source and the wrapped lifecycle
source data are read. Source-side group_vars/host_vars are classified as absent;
any addition is rejected by path without reading its contents. Never load inventory/vault, render arbitrary Jinja, or run a backend.

The pins are deliberately conservative tripwires for reviewed task graphs and
opaque commands: changes require tracing and updating the finite classification,
not regenerating hashes blindly. User destination variables are source contracts
(quadlet_dir / forgejo_runner_quadlet_dir), NOT proof of effective inventory
values. Separate launcher/rendering tests exercise synthetic user destinations. An
operator must verify effective deployed values and reject configuration drift.

No assertion here concerns package-installed services or running host state.
"""
import copy
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = "playbooks/vars/system_lifecycle.yml"
USER_ROLES = {"base", "caddy", "quadlets", "forgejo_runner"}
ROLES = USER_ROLES | {"nvidia", "decommissioned_services"}
# Canonical YAML hashes cover module arguments, loops, block context, destinations,
# notifications, includes and opaque non-unit actions (CDI, HTTP APIs, firewall).
# #64: base adds a controller-only suffix assertion; AdGuard only derives its
# exact wildcard. Unit templates only derive LAN names/labels (no scope,
# destination, command, volume or service-manager changes).
# #70: native stat/slurp/merge/copy tasks update the same user config path.
# The added include preserves the service handler and system lifecycle boundary;
# private tempfile/copy backups are confined to that service's config directory.
# #71: Uptrace API/state work is live-only; cookie parsing uses the uri cookie jar.
# Runner previews read real identity and avoid user buses, including handlers;
# absent accounts defer dependent work. Live destinations and user scope persist.
# #109: normal service selection adds two user Quadlets. Private Hatchet
# directories/config and the launcher remain under hatchet_data_dir; paired
# restart handlers retain scope=user. The one-shot native initialization container
# and atomic private record publisher stay within that user-owned data directory;
# neither starts the engine/database nor introduces system provisioning. Caddy
# adds the LAN UI upstream; the user Quadlet adds discovery and collector settings.
TASK_PINS = {
    "roles/quadlets/tasks/hatchet-config.yml": "7d8dbdd0620fab806448675478346c0003b2a9842a4591dbf41e76b99143226a",
    "roles/quadlets/tasks/hatchet-initialize.yml": "3f83a5216ceadb2cee3a7c97d8c479a02c8c96a84c472719bcd10a7bb362b465",
    "roles/quadlets/tasks/hatchet.yml": "1fbda49a09c61a1f8c5762b75124e965116668d966fde0db819a1b2571e7aa68",
    "roles/quadlets/tasks/sillytavern.yml": "a4ca5bd483dc20958a6dcc2229dd91286aafcaa297329ac731f6a2aaad2507b7",
    "roles/quadlets/tasks/webgallery.yml": "c743cc6eebe43b238d8796bc9a2ffbf753baf11f89b3079eee2a07f7c024bfdf",
    "roles/decommissioned_services/tasks/network.yml": "4a4777dcf41e50a71208ebcb57724f454592a8602fb3845825e6dffdc24b5cfd",
    "roles/decommissioned_services/tasks/converge.yml": "d08a3d1f6ad5951630a27ad5ac32338860b27310e9963ec828b5b0a918fbad0c",
    "roles/decommissioned_services/tasks/validate.yml": "f6bad3bc257c5d6371bda6e1967627fdf6c376b2b808523a341dad8a380d29f1",
    "roles/base/handlers/main.yml": "faa1d0329f442797c8fb25f93c8736604e9f75f8a69b7a3707254a82beea4db2",
    "roles/base/tasks/main.yml": "2d955dc3192b96f1244aa4d396739b73995c6889a15769d8b406a0f03f3459d0",
    "roles/caddy/handlers/main.yml": "837289bc4d0a75dd1626b6e4cdd76f27c8ecf12465e54663ec2f249080148f54",
    "roles/caddy/tasks/main.yml": "5c937923825f517ef7c33cf10d85f222daf84a52d4e775f6575f1d28cbf618ce",
    "roles/decommissioned_services/handlers/main.yml": "0314a5e7443e9185914f96a521594f441174e7ed4c8c11803013b3f3ac2b5ffc",
    "roles/decommissioned_services/tasks/main.yml": "e4ef37eee4aa4d96ef8d825c6679ab14730f1d1129c6df22361d7f0e2ffd9630",
    "roles/forgejo_runner/handlers/main.yml": "6a96ffbec2b6030e96aa3dbd5522f884da60fb8345adba1ca5d49d237ed368e1",
    "roles/forgejo_runner/tasks/job_policy.yml": "84ebab5f7ca0c4b907d33ccf34f7fa7720dc878d83d138ccf09836fce57fe366",
    "roles/forgejo_runner/tasks/main.yml": "23c3f761c5a7a232773ee09c2f869a30369f6c3e065416367ef8a61a470ab69e",
    "roles/nvidia/tasks/main.yml": "a0ed3021381db3336eadeb85c84ec6cf27314e2871eee35ad26a1ccac6095934",
    "roles/quadlets/handlers/main.yml": "2324cffb005a3581e705eb07d2f72f2dea3e5f21c094da38acd24758cb49c7c5",
    "roles/quadlets/tasks/adguardhome-provision.yml": "d3aa363abcc18fe1028d9ace8da51ef29d7744d01b18e376a021a10596175f1a",
    "roles/quadlets/tasks/main.yml": "a415867554bcbde18c32fc9e25efadbec43f2aaf9a57315c41ed58fb1edeacd9",
    "roles/quadlets/tasks/uptrace-dashboards.yml": "676f2e0e6df0c2bb1fdb3642a32e3d516b73e992b5334f98b2c74072322f323b",
}

# Generated units plus executed source scripts: commands and references
# are pinned too; task pins alone cannot detect a changed ExecStartPre payload.
ARTIFACT_PINS = {
    "roles/quadlets/files/hatchet-generate.sh": "00f4e30f2ab35649170050c8488c6c00262bf0c919229b9b06afd6c5e83093a7",
    "roles/quadlets/files/hatchet-start.sh": "a4a2ad0f03378b53478f271ab58985772be87e47f7b8ab56af4a07acf2897f74",
    "roles/quadlets/templates/hatchet-postgres.container.j2": "41467abc33e7e839486a3b61847f86a16bfa7cd678e0aba3c48bbdb8665edbd3",
    "roles/quadlets/templates/hatchet.container.j2": "5f23473311a87622e6d61643c7cb8f303b3b55f0710c7b0df11ac9c8278d8dd6",
    "roles/quadlets/templates/hatchet.database-url.j2": "bf3cd7c29a9a8863756b8255581d520eaf7c0d1bca255ce408e02d53ccf5e629",
    "roles/quadlets/templates/hatchet.database.yaml.j2": "f522f7ca5d43dcef0bf3dc057e9d6d7925c7b27e459859daa018518050039b7d",
    "roles/quadlets/templates/hatchet.grpc-ca.crt.j2": "22872510a97c048415a140700b010cb912aff8f0cff8befb77458638d3f004e6",
    "roles/quadlets/templates/hatchet.grpc.crt.j2": "39de25b2209a697bbbca7965b2e254e372156182f9ce979489a24664fddde523",
    "roles/quadlets/templates/hatchet.grpc.key.j2": "baffcc0b2a4cb2e5d7bb3e01257518117e0eca081ad3ec07eebc970280c84bf7",
    "roles/quadlets/templates/hatchet.master.key.j2": "38f8fb113a71ce7930b5f09af37775e12383251d6295043103041adc2d87bf49",
    "roles/quadlets/templates/hatchet.postgres-password.j2": "7109d12634ab39b2442268b44d188d8d58343ed7368597ed8a06d4ee90c800e4",
    "roles/quadlets/templates/hatchet.private-jwt.key.j2": "1a4a3088768801b878f70fabeeaf34ea56a22b80ebae74517c823f92cfc4588b",
    "roles/quadlets/templates/hatchet.public-jwt.key.j2": "d035020fe6956cd7f8a162e91fea5f2001b06fe0d9b25ad3006568c407c25f90",
    "roles/quadlets/templates/hatchet.server.yaml.j2": "d60f61ca7496a9f8b0d64da06644ea00fab2a01e9bef8894bc2712bb14983925",

    "roles/quadlets/templates/webgallery.container.j2": "ec117ebfb37c8498f0c1ca7864e4c9936a2b8269a24077bd69b2bde150e808bc",
    "roles/base/files/homelab.network": "3dd7bab39fe946ce1e1abf7ef4d92c6d769895504698dbecc04bae7e6637a243",
    "roles/base/templates/homelab-auto-rebuild-check.sh.j2": "c63835f4616af90634f51d9a8108f94a7c68129397959f8ae71db55761c3c617",
    "roles/base/templates/podman-auto-update.service.override.conf.j2": "1c607259b53854a6784edcb8cdf6d7c364fb20a52323d234a1a60e05687f90d6",
    "roles/base/templates/podman-auto-update.timer.override.conf.j2": "c688d7b0e06784d29bcf4c4382ecf722a4d2dc2a01c4c4bc1fbd3023ba39c436",
    "roles/forgejo_runner/templates/forgejo-runner.container.j2": "d5db3ee9cbc3222edf055e51f10a9632dc2d9daddb561eed5eed95694f9de721",
    "roles/quadlets/templates/adguardhome.container.j2": "4b553804187d615f49f15e6382736a4466e0b57f564cebb43ef8c155f37f5efa",
    "roles/quadlets/templates/caddy.container.j2": "eedffbee7476e3cfd497ae6ac18d837e80f870f1106bac6d6a8882c2eccc83b4",
    "roles/quadlets/templates/forgejo.container.j2": "a04f4ac87b2fd9b229a8d2838696cbba87a5e55c79f94ef8764a6afcabaeeda8",
    "roles/quadlets/templates/glances.container.j2": "6890fa35e88b427ef26fa214a6cd965ea7c1e78185ec048dd26f0b14c0d1e611",
    "roles/quadlets/templates/homepage.container.j2": "eba90afdfc383f7708ce57430c2bcd9b0b131e57b180c24a2dd0b13696d4149a",
    "roles/quadlets/templates/llama-swap.container.j2": "3daa13d9b25dd7b1762ddbab3c32fce580e56d7717530062be789816d69732dd",
    "roles/quadlets/templates/open-webui.container.j2": "bd14b8fb86b089b7466c61710d84338551d60497025aed6347528e6f44fc7d70",
    "roles/quadlets/templates/piclaw.container.j2": "503582e02414bd636a286dba68e1b3580c0888d6e1f288c06ca9504c8f8f0a02",
    "roles/quadlets/templates/playwright.container.j2": "953fcd273fc2ddbe49e3c4096fe0331d0cc47271960bb14919dc25ecc146948e",
    "roles/quadlets/templates/searxng.container.j2": "b6c1b66033814774e52218d3333278e36b315f6fd8459bce497aeed35a37a566",
    "roles/quadlets/templates/sillytavern.container.j2": "b135fe99d4a3a2d1a8a2e676bf6d433965d79410bfdcc68a7dc57151b7615930",
    "roles/quadlets/templates/swarmui.build.j2": "3468504aee5df5e3dd1fbb571e6af56cfc3e54f95bc90249e311c1a163d4567b",
    "roles/quadlets/templates/swarmui.container.j2": "0be22cf34fb2ee0371d6719bc7169382cc0bccdcca2e55368e343dc6ed934f3a",
    "roles/quadlets/templates/sync_openwebui_db.py.j2": "e59458d5258e52a3b327ce2e7110d8a9f0c763eeebae05f77bcbb8a6d59e1abc",
    "roles/quadlets/templates/uptrace-clickhouse.container.j2": "da2dc11192ce90b811b81d33a25da7ac210925cf2f7b030c6ed37ecbcec9605d",
    "roles/quadlets/templates/uptrace-otelcol.container.j2": "05c6533352146bae6c68fdefa6b2f936d16b42addea1ee22e8282eab0f55103e",
    "roles/quadlets/templates/uptrace-postgres.container.j2": "c0654b99cfcf760b4e282b2891a360ebaba427319a31b0b0164f5990a8a3e2d9",
    "roles/quadlets/templates/uptrace-redis.container.j2": "76ae9a959222a052bb256918eb72954ab38524cad375f9ff2f292f62b97679df",
    "roles/quadlets/templates/uptrace.container.j2": "853928e54a7085d87443157bc9ff7970932a8614e01c9e83b658243589383909",
}


# Finite source context, not effective inventory values. Whole-play pins include
# role parameters, inline vars and execution context. Display names are immaterial;
# retirement call/task pins cover the integrated source-bound admission.
PLAY_CONTEXT_PINS = (
    "d7795e2695fe07ea7cfd83862a51fb96dd75c88e9393dac7a8f6bc6e2920467b",
    "5d70c1aef94195dda9bd2c7b372e3e7b2095baa99a6552b151f126c5f002b83e",
    "14b60b6622801dba90e46164758b8807ada1b74c96b5109d277feff4f6979090",
    "ff5d3bc1ad87c57c8c4af624a3b5447b6740266495fcf4c741b865a4db3e1a98",
    "32fb18ae4c3b78d8021b2b69c9ee121ceab6c374ed182a55a8873e26db0d85d4",
    "9eb370969a4c52a057ca944f60ff2a7b12409c29f7d484d26813fc27b2976af0",
    "84e7c18c26a7f16a77870aa6e6ae62cb503f8e0ff0beeef8a02fd99495ae0ec8",
)
SOURCE_CONTEXT_PINS = {
    "roles/quadlets/defaults/main.yml": "2eafedd02cd658b9bd868d478534a25961960045fdfc053ca154ce83ef50ed34",
    "roles/caddy/defaults/main.yml":
        "8c49384a14861e1ab59e8889397e78709bec42b5a6e76fe2c4129b58fe255970",
    "roles/decommissioned_services/defaults/main.yml":
        "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
}
LIFECYCLE_VAR = "homelab_lifecycle_source"
PREFLIGHT_CONTEXT = {'hosts': 'all',
 'gather_facts': False,
 'strategy': 'linear',
 'any_errors_fatal': True,
 'vars_files': ['./vars/system_lifecycle.yml'],
 'pre_tasks': [{'ansible.builtin.import_role': {'name': 'decommissioned_services',
                                                'tasks_from': 'network'}},
               {'ansible.builtin.import_role': {'name': 'decommissioned_services',
                                                'tasks_from': 'validate'},
                'vars': {'homelab_active_system_services': '{{ '
                                                           'homelab_lifecycle_source.active_system_services '
                                                           '}}',
                         'homelab_decommissioned_services': '{{ '
                                                            'homelab_lifecycle_source.retired_system_services '
                                                            '}}',
                         'homelab_preserved_system_units': '{{ '
                                                           'homelab_lifecycle_source.preserved_system_units '
                                                           '}}'}}]}


def canonical_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def source_context(source, plays):
    """Finite source boundary; never resolve inventory or arbitrary vars_files.

    Inventory-adjacent group/host vars and launcher config are deliberately outside
    this source audit. Parent runtime tests must establish their effective values.
    Playbook-adjacent (and root source) implicit vars must remain absent, including
    extensionless files and main/ directories. Unknown paths fail before reading.
    """
    prefixes = ["group_vars", "host_vars", "playbooks/group_vars", "playbooks/host_vars"]
    prefixes += [f"roles/{role}/{kind}" for role in ROLES
                 for kind in ("vars", "defaults", "meta")]
    paths = set()
    for prefix in prefixes:
        root = ROOT / prefix
        require(not root.is_symlink(), "unclassified implicit source symlink")
        if root.exists():
            paths.add(prefix)
            if root.is_dir():
                paths.update(str(p.relative_to(ROOT)) for p in root.rglob("*"))
        paths.update(p for p in source.overrides if p == prefix or p.startswith(prefix + "/"))
    # Only the explicitly reviewed defaults files and their directories exist.
    allowed = set(SOURCE_CONTEXT_PINS) | {str(Path(p).parent) for p in SOURCE_CONTEXT_PINS}
    require(paths <= allowed, "unclassified implicit variable source or role metadata")
    for path, digest in SOURCE_CONTEXT_PINS.items():
        require(not (ROOT / path).is_symlink(), "unclassified source context symlink")
        require(canonical_digest(source.data(path)) == digest,
                "unclassified role vars/defaults context: " + path)

    require(isinstance(plays, list), "site play sequence required")
    contexts = copy.deepcopy(plays)
    for play in contexts:
        require(isinstance(play, dict), "site play mapping required")
        play.pop("name", None)
    require(contexts and "pre_tasks" in contexts[0], "missing lifecycle preflight context")
    preflight = contexts.pop(0)
    for task in preflight.get("pre_tasks", []):
        require(isinstance(task, dict), "preflight task mapping required")
        task.pop("name", None)
    require(preflight == PREFLIGHT_CONTEXT, "unclassified preflight vars_files/vars/role context")
    # Exactly the same explicit source file in retirement, no search lists,
    # templated filenames, inline override or additional file is admitted.
    require(len(contexts) > 1 and contexts[1].get("vars_files") ==
            PREFLIGHT_CONTEXT["vars_files"], "unclassified retirement vars_files")
    contexts[1].pop("vars_files")
    require(tuple(canonical_digest(p) for p in contexts) == PLAY_CONTEXT_PINS,
            "unclassified play vars/vars_files/role/execution context")


def lifecycle_policy(source):
    wrapper = source.data(POLICY)
    require(isinstance(wrapper, dict) and set(wrapper) == {LIFECYCLE_VAR},
            "unclassified lifecycle vars_file wrapper")
    policy = wrapper[LIFECYCLE_VAR]
    require(isinstance(policy, dict) and set(policy) == {
        "active_system_services", "retired_system_services", "preserved_system_units"},
        "unclassified lifecycle source fields")
    return policy


class AuditError(AssertionError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


class Source:
    """In-memory overlays make mutations isolated; no repository fixture writes."""
    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def text(self, path):
        if path in self.overrides:
            return self.overrides[path]
        relative = Path(path)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "unclassified source path")
        require(not any((ROOT / part).is_symlink()
                        for part in (relative, *relative.parents)),
                "unclassified source symlink")
        require((ROOT / path).is_file(), "missing source: " + path)
        return (ROOT / path).read_text()

    def data(self, path):
        return yaml.safe_load(self.text(path))


def flattened(tasks):
    require(isinstance(tasks, list), "task sequence required")
    for task in tasks:
        require(isinstance(task, dict), "task mapping required")
        yield task
        for section in ("block", "rescue", "always"):
            if section in task:
                yield from flattened(task[section])


def compare_declarations(actual, policy):
    """Independent, bounded source comparison; production admission is separate.

    Only literal unit names and a single template-instance '*' are understood.
    That grammar makes family intersection decidable without a glob interpreter.
    """
    require(isinstance(policy, dict), "lifecycle mapping required")
    keys = {"active_system_services", "retired_system_services", "preserved_system_units"}
    require(keys <= policy.keys(), "missing lifecycle declarations")
    active, retired, preserved = (policy[k] for k in (
        "active_system_services", "retired_system_services", "preserved_system_units"))
    require(all(isinstance(x, list) for x in (actual, active, retired, preserved)),
            "lifecycle declarations must be lists")
    unit = r"[a-zA-Z0-9_:-]+(?:@[a-zA-Z0-9_:-]*)?\.(?:service|socket|timer|target|path|mount|automount)"
    family = r"[a-zA-Z0-9_:-]+@\*\.service"

    def records(items, retirement=False):
        names = set()
        for item in items:
            require(isinstance(item, dict), "service mapping required")
            fields = {"name", "unit_globs", "unit_files"}
            allowed = fields | ({"firewalld_rules", "ufw_rules"} if retirement else set())
            require(fields <= item.keys() <= allowed, "unknown service fields")
            name = item["name"]
            require(isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_-]*", name),
                    "invalid service name")
            require(name not in names, "duplicate service name")
            names.add(name)
            for key in ("unit_globs", "unit_files"):
                require(isinstance(item[key], list), "unit list required")
                require(all(isinstance(v, str) for v in item[key]), "unit string required")
                require(len(set(item[key])) == len(item[key]), "duplicate unit declaration")
            require(item["unit_globs"] or item["unit_files"], "empty service declaration")
            require(all(re.fullmatch(unit, v) or re.fullmatch(family, v)
                        for v in item["unit_globs"]), "unbounded unit pattern")
            require(all(v.startswith("/etc/systemd/system/") and
                        re.fullmatch(unit, v.removeprefix("/etc/systemd/system/"))
                        for v in item["unit_files"]), "unknown unit destination")
        return items

    records(actual)
    records(active)
    records(retired, retirement=True)
    require(all(isinstance(v, str) and re.fullmatch(unit, v) for v in preserved),
            "invalid preserved unit")

    def patterns(record):
        return record["unit_globs"] + [Path(p).name for p in record["unit_files"]]

    def intersects(left, right):
        return fnmatch.fnmatchcase(left, right) or fnmatch.fnmatchcase(right, left)

    def conflicts(left, right):
        return left["name"] == right["name"] or any(
            intersects(a, b) for a in patterns(left) for b in patterns(right))

    for group in (active, retired):
        for index, record in enumerate(group):
            require(not any(conflicts(record, other) for other in group[index + 1:]),
                    "conflicting declarations")
    for record in retired:
        require(not any(conflicts(record, other) for other in active),
                "active/retired conflict")
        require(not any(intersects(pattern, kept) for pattern in patterns(record)
                        for kept in preserved), "preserved unit conflict")
    canonical = lambda records: sorted(json.dumps(r, sort_keys=True) for r in records)
    require(canonical(actual) == canonical(active), "source/declaration mismatch")


def audit(source):
    plays = source.data("playbooks/site.yml")
    source_context(source, plays)
    policy = lifecycle_policy(source)
    visited = set()
    roles = set()
    services = set()
    artifacts = set()

    def walk(path, role):
        require(path in TASK_PINS, "unclassified task/include: " + path)
        if path in visited:
            return
        visited.add(path)
        tasks = source.data(path)
        for task in flattened(tasks):
            for module, args in task.items():
                if module in ("ansible.builtin.include_tasks", "ansible.builtin.import_tasks"):
                    target = args if isinstance(args, str) else args.get("file")
                    require(isinstance(target, str) and re.fullmatch(r"[a-z_-]+\.yml", target),
                            "opaque include: " + path)
                    walk(str(Path(path).parent / target), role)
                if module in ("ansible.builtin.systemd", "ansible.builtin.systemd_service",
                              "ansible.builtin.service", "systemd", "service"):
                    require(isinstance(args, dict), "opaque service consumer")
                    if role in USER_ROLES:
                        require(args.get("scope") == "user", "unknown/non-user scope: " + path)
                    else:
                        require(role == "decommissioned_services", "unexpected system consumer")
                        require(args.get("scope", "system") == "system", "retirement scope")
                        reload_only = args == {"daemon_reload": True}
                        stop_only = (args.get("state") == "stopped" and args.get("enabled") is False
                                     and set(args) <= {"name", "state", "enabled", "scope"})
                        require(reload_only or stop_only, "retirement provisioning forbidden")
        # This pins *all* actions, not just modules caught by the semantic checks:
        # action/local_action, new commands, changed loops, destinations, scope
        # overrides, and nested role calls cannot bypass the finite classification.
        digest = hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
        require(digest == TASK_PINS[path], "unclassified task graph/destination/command: " + path)

    def enable(call):
        name = call if isinstance(call, str) else call.get("role")
        require(isinstance(name, str) and name in ROLES, "unclassified enabled role")
        roles.add(name)
        if name == "quadlets":
            values = call.get("vars", {}).get("quadlet_services")
            require(isinstance(values, list) and values and
                    all(isinstance(v, str) and re.fullmatch(r"[a-z][a-z0-9-]*", v) for v in values),
                    "opaque quadlet_services call")
            for service in values:
                path = "roles/quadlets/templates/" + service + ".container.j2"
                require(path in ARTIFACT_PINS, "unclassified generated unit")
                artifacts.add(path)
                services.add(service)
        walk("roles/" + name + "/tasks/main.yml", name)
        handlers = "roles/" + name + "/handlers/main.yml"
        if handlers in TASK_PINS or (ROOT / handlers).exists() or handlers in source.overrides:
            walk(handlers, name)
        # Role dependencies are another enabled source, not an implicit exemption.
        meta = "roles/" + name + "/meta/main.yml"
        require(not (ROOT / meta).exists() and meta not in source.overrides,
                "unclassified role metadata/dependency")

    require(isinstance(plays, list), "site play sequence required")
    for play in plays:
        require(isinstance(play, dict) and "import_playbook" not in play,
                "unclassified imported playbook")
        for call in play.get("roles", []):
            enable(call)
        for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            for task in flattened(play.get(section, [])):
                # The parent preflight may import the retirement validation file.
                # All other top-level actions need an explicit finite fixture.
                if "block" in task:
                    require(set(task) <= {"name", "block", "when", "tags"},
                            "unclassified site block")
                    continue
                imports = [k for k in ("ansible.builtin.import_role", "ansible.builtin.include_role")
                           if k in task]
                require(len(imports) == 1, "unclassified site consumer")
                args = task[imports[0]]
                require(isinstance(args, dict) and args.get("name") == "decommissioned_services"
                        and set(args) <= {"name", "tasks_from"}, "unclassified site role call")
                target = args.get("tasks_from", "main")
                require(isinstance(target, str) and re.fullmatch(r"[a-z_]+(?:\.yml)?", target),
                        "opaque tasks_from")
                target = target if target.endswith(".yml") else target + ".yml"
                walk("roles/decommissioned_services/tasks/" + target, "decommissioned_services")
    require(roles == ROLES, "enabled role coverage changed")
    # Fixed helper outputs and commands are reachable through pinned tasks.
    artifacts |= {p for p in ARTIFACT_PINS if "/quadlets/templates/" not in p}
    artifacts.add("roles/quadlets/templates/sync_openwebui_db.py.j2")
    if "hatchet" in services:
        artifacts |= {p for p in ARTIFACT_PINS if p.startswith("roles/quadlets/templates/hatchet.")}
    if "swarmui" in services:
        artifacts.add("roles/quadlets/templates/swarmui.build.j2")
    for path in artifacts:
        digest = hashlib.sha256(source.text(path).encode()).hexdigest()
        require(digest == ARTIFACT_PINS[path], "unclassified generated output/command: " + path)
    # All enumerated provisioning consumers are user-owned. NVIDIA only installs
    # toolkit/repository and generates CDI. Retirement only discovers/stops/
    # disables/removes declared system aliases and reloads the system manager.
    actual_system = []
    compare_declarations(actual_system, policy)
    return {"roles": roles, "tasks": visited, "artifacts": artifacts,
            "quadlets": services, "active_system_services": actual_system}


SYNTHETIC_POLICY = {
    "active_system_services": [],
    "retired_system_services": [{"name": "alias", "unit_globs": ["fixture-alias@*.service"],
                                "unit_files": ["/etc/systemd/system/fixture-alias@.service"]}],
    "preserved_system_units": ["fixture-daemon.service"],
}


class SourceAuditTests(unittest.TestCase):
    def fixture(self, overrides=None):
        return Source({POLICY: yaml.safe_dump({LIFECYCLE_VAR: SYNTHETIC_POLICY}), **(overrides or {})})

    def mutate_yaml(self, path, change):
        data = Source().data(path)
        change(data)
        return self.fixture({path: yaml.safe_dump(data)})

    def test_reviewed_source_context(self):
        source_context(self.fixture(), Source().data("playbooks/site.yml"))
        self.assertEqual(lifecycle_policy(self.fixture()), SYNTHETIC_POLICY)

    def test_parent_preflight_context_without_repinning_retirement_tasks(self):
        plays = Source().data("playbooks/site.yml")
        source_context(self.fixture(), plays)
        for change in (
            lambda p: p[0].update(vars={"quadlet_dir": "/etc/systemd/system"}),
            lambda p: p[0]["pre_tasks"][0].update(vars={"quadlet_dir": "/etc/systemd/system"}),
            lambda p: p[0].update(strategy="free"),
            lambda p: p[2].update(vars_files=["./vars/other.yml"]),
        ):
            mutated = copy.deepcopy(plays)
            change(mutated)
            with self.assertRaisesRegex(AuditError, "context|vars_files"):
                source_context(self.fixture(), mutated)

    def test_play_and_role_variable_context_mutations(self):
        baseline = Source().data("playbooks/site.yml")
        for index, play in enumerate(baseline):
            mutations = [
                lambda p: p.update(vars={"quadlet_dir": "/etc/systemd/system"}),
                lambda p: p.update(vars={"forgejo_runner_quadlet_dir": "/etc/systemd/system"}),
                lambda p: p.update(vars_files=["./vars/rogue.yml"]),
                lambda p: p.update(vars_files=[["./vars/system_lifecycle.yml", "fallback.yml"]]),
                lambda p: p.update(environment={"XDG_CONFIG_HOME": "/etc"}),
                lambda p: p.update(module_defaults={"ansible.builtin.systemd": {"scope": "system"}}),
            ]
            for mutation in mutations:
                plays = copy.deepcopy(baseline)
                mutation(plays[index])
                with self.subTest(play=index, context=plays[index]), self.assertRaises(AuditError):
                    source_context(self.fixture(), plays)
            for call_index, call in enumerate(play.get("roles", [])):
                for field in ("vars", "quadlet_dir", "vars_files"):
                    plays = copy.deepcopy(baseline)
                    replacement = {"role": call} if isinstance(call, str) else copy.deepcopy(call)
                    replacement[field] = ({"quadlet_dir": "/etc/systemd/system"}
                                          if field == "vars" else "/etc/systemd/system")
                    plays[index]["roles"][call_index] = replacement
                    with self.subTest(play=index, role=call_index, field=field), self.assertRaises(AuditError):
                        source_context(self.fixture(), plays)

    def test_unclassified_var_files_are_not_read(self):
        class GuardedSource(Source):
            def text(self, path):
                if path == "playbooks/vars/rogue.yml":
                    raise AssertionError("unclassified vars_file was read")
                return super().text(path)
        plays = Source().data("playbooks/site.yml")
        plays[0]["vars_files"] = ["./vars/rogue.yml"]
        source = GuardedSource({"playbooks/site.yml": yaml.safe_dump(plays),
                                "playbooks/vars/rogue.yml": "quadlet_dir: /etc/systemd/system"})
        with self.assertRaisesRegex(AuditError, "vars_files"):
            audit(source)

    def test_implicit_variable_sources_and_metadata_fail_closed(self):
        paths = [f"{prefix}/{suffix}" for prefix in (
            "group_vars", "host_vars", "playbooks/group_vars", "playbooks/host_vars")
            for suffix in ("all", "all.yml", "all/extra.yaml")]
        paths += [f"roles/{role}/{kind}/{suffix}" for role in ROLES
                  for kind in ("vars", "defaults", "meta")
                  for suffix in ("main.yml", "main.yaml", "main/extra.yml")]
        for path in paths:
            with self.subTest(path=path), self.assertRaisesRegex(AuditError, "context|implicit"):
                source_context(self.fixture({path: "quadlet_dir: /etc/systemd/system"}),
                               Source().data("playbooks/site.yml"))
        for path in SOURCE_CONTEXT_PINS:
            data = Source().data(path)
            data["forgejo_runner_quadlet_dir"] = "/etc/systemd/system"
            with self.subTest(path=path), self.assertRaisesRegex(AuditError, "defaults context"):
                source_context(self.fixture({path: yaml.safe_dump(data)}),
                               Source().data("playbooks/site.yml"))

    def test_unknown_enabled_role_context(self):
        plays = Source().data("playbooks/site.yml")
        plays[1]["roles"].append({"role": "unknown"})
        with self.assertRaisesRegex(AuditError, "role"):
            source_context(self.fixture(), plays)

    def test_lifecycle_source_file_wrapper_rejects_variable_injection(self):
        for data in (SYNTHETIC_POLICY, None, {LIFECYCLE_VAR: SYNTHETIC_POLICY,
                                            "quadlet_dir": "/etc/systemd/system"},
                     {LIFECYCLE_VAR: {**SYNTHETIC_POLICY, "quadlet_dir": "/etc/systemd/system"}}):
            with self.subTest(data=data), self.assertRaisesRegex(AuditError, "lifecycle"):
                lifecycle_policy(self.fixture({POLICY: yaml.safe_dump(data)}))

    def test_actual_source_matches_caller_declarations(self):
        # Missing parent-owned data is a failure, never a skip or an empty default.
        self.assertEqual(audit(Source())["active_system_services"], [])

    def test_synthetic_context_traces_all_enabled_sources(self):
        result = audit(self.fixture())
        self.assertEqual(result["roles"], ROLES)
        self.assertEqual(result["tasks"], set(TASK_PINS))
        self.assertEqual(result["artifacts"], set(ARTIFACT_PINS))
        self.assertEqual(len(result["quadlets"]), 20)
        self.assertTrue({"hatchet", "hatchet-postgres"} <= result["quadlets"])

    def test_each_task_and_handler_requires_explicit_user_scope(self):
        for path in TASK_PINS:
            if Path(path).parts[1] not in USER_ROLES:
                continue
            tasks = list(flattened(Source().data(path)))
            for index, task in enumerate(tasks):
                if "ansible.builtin.systemd" not in task:
                    continue
                for scope in (None, "system", "{{ unknown_scope }}"):
                    with self.subTest(path=path, index=index, scope=scope):
                        def change(data):
                            args = list(flattened(data))[index]["ansible.builtin.systemd"]
                            if scope is None:
                                args.pop("scope")
                            else:
                                args["scope"] = scope
                        with self.assertRaisesRegex(AuditError, "scope"):
                            audit(self.mutate_yaml(path, change))

    def test_every_file_writer_destination_is_classified(self):
        for path in TASK_PINS:
            for index, task in enumerate(flattened(Source().data(path))):
                for module in ("ansible.builtin.template", "ansible.builtin.copy", "ansible.builtin.file"):
                    if module not in task:
                        continue
                    for dest in ("/etc/systemd/system/rogue.service", "{{ unknown_destination }}"):
                        with self.subTest(path=path, index=index, destination=dest):
                            def change(data):
                                args = list(flattened(data))[index][module]
                                args["path" if module.endswith(".file") else "dest"] = dest
                            with self.assertRaises(AuditError):
                                audit(self.mutate_yaml(path, change))

    def test_unknown_consumers_includes_and_roles_fail(self):
        additions = [
            {"ansible.builtin.service": {"name": "rogue", "state": "started"}},
            {"ansible.builtin.command": "systemctl enable rogue.service"},
            {"ansible.builtin.shell": "printf unit > /etc/systemd/system/rogue.service"},
            {"ansible.builtin.include_tasks": "{{ opaque }}"},
            {"ansible.builtin.include_tasks": "new.yml"},
            {"ansible.builtin.include_role": {"name": "unknown"}},
            {"action": "systemd name=rogue state=started"},
        ]
        for role in ROLES:
            for task in additions:
                with self.subTest(role=role, task=task):
                    with self.assertRaises(AuditError):
                        audit(self.mutate_yaml("roles/" + role + "/tasks/main.yml",
                                               lambda data: data.append(task)))
        with self.assertRaisesRegex(AuditError, "role"):
            audit(self.mutate_yaml("playbooks/site.yml",
                                   lambda data: data[1]["roles"].append("unknown")))

    def test_changed_generated_commands_and_references_fail(self):
        for path in ARTIFACT_PINS:
            with self.subTest(path=path):
                text = Source().text(path) + "\nExecStartPre=/bin/systemctl enable rogue.service\n"
                with self.assertRaisesRegex(AuditError, "generated output"):
                    audit(self.fixture({path: text}))
        path = "roles/base/templates/homelab-auto-rebuild-check.sh.j2"
        with self.assertRaises(AuditError):
            audit(self.fixture({path: Source().text(path).replace("systemctl --user", "systemctl")}))

    def test_new_quadlet_call_is_not_silently_ignored(self):
        def change(data):
            data.append({"hosts": "synthetic", "roles": [
                {"role": "quadlets", "vars": {"quadlet_services": ["unknown"]}}]})
        with self.assertRaisesRegex(AuditError, "context"):
            audit(self.mutate_yaml("playbooks/site.yml", change))

    def test_retirement_is_confined_not_exempt(self):
        path = "roles/decommissioned_services/tasks/converge.yml"
        for field, value in (("state", "started"), ("enabled", True), ("scope", "user"),
                             ("name", "unrelated.service")):
            def change(data):
                task = next(t for t in flattened(data) if "ansible.builtin.systemd" in t)
                task["ansible.builtin.systemd"][field] = value
            with self.subTest(field=field), self.assertRaises(AuditError):
                audit(self.mutate_yaml(path, change))

    def test_nonempty_declarations_require_matching_source(self):
        record = {"name": "other", "unit_globs": ["other.service"],
                  "unit_files": ["/etc/systemd/system/other.service"]}
        policy = copy.deepcopy(SYNTHETIC_POLICY)
        policy["active_system_services"] = [record]
        compare_declarations([record], policy)
        with self.assertRaisesRegex(AuditError, "source/declaration mismatch"):
            audit(self.fixture({POLICY: yaml.safe_dump({LIFECYCLE_VAR: policy})}))
        with self.assertRaisesRegex(AuditError, "source/declaration mismatch"):
            compare_declarations([record], SYNTHETIC_POLICY)

    def test_nonempty_conflicts_independent_of_display_name(self):
        for record in (
            {"name": "alias", "unit_globs": ["other.service"], "unit_files": []},
            {"name": "other", "unit_globs": ["fixture-alias@live.service"], "unit_files": []},
            {"name": "other", "unit_globs": ["fixture-alias@*.service"], "unit_files": []},
            {"name": "other", "unit_globs": [],
             "unit_files": ["/etc/systemd/system/fixture-alias@.service"]},
        ):
            policy = copy.deepcopy(SYNTHETIC_POLICY)
            policy["active_system_services"] = [record]
            with self.subTest(record=record), self.assertRaisesRegex(AuditError, "active/retired conflict"):
                compare_declarations([record], policy)
        policy = copy.deepcopy(SYNTHETIC_POLICY)
        policy["preserved_system_units"] += ["fixture-alias@live.service"]
        with self.assertRaisesRegex(AuditError, "preserved unit conflict"):
            compare_declarations([], policy)

    def test_missing_malformed_and_unbounded_declarations_fail(self):
        for key in SYNTHETIC_POLICY:
            for value in (None, {}, ""):
                policy = copy.deepcopy(SYNTHETIC_POLICY)
                policy[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(AuditError):
                    compare_declarations([], policy)
            policy = copy.deepcopy(SYNTHETIC_POLICY)
            del policy[key]
            with self.assertRaises(AuditError):
                compare_declarations([], policy)
        for pattern in ("*", "*.service", "fixture-*.service", "{{ unresolved }}"):
            policy = copy.deepcopy(SYNTHETIC_POLICY)
            policy["retired_system_services"][0]["unit_globs"] = [pattern]
            with self.assertRaisesRegex(AuditError, "unbounded"):
                compare_declarations([], policy)

    def test_source_caller_binds_only_the_owned_alias_topology(self):
        policy = lifecycle_policy(Source())
        self.assertEqual(policy["active_system_services"], [])
        self.assertEqual(policy["preserved_system_units"], ["avahi-daemon.service"])
        self.assertEqual(len(policy["retired_system_services"]), 1)
        retirement = policy["retired_system_services"][0]
        self.assertEqual(retirement["name"], "avahi")
        self.assertEqual(retirement["unit_globs"], ["avahi-alias@*.service"])
        self.assertEqual(retirement["unit_files"], ["/etc/systemd/system/avahi-alias@.service"])
        self.assertEqual(retirement["ufw_rules"], [{"from_ip": "{{ lan_subnet }}", "port": "5353", "proto": "udp"}])
        self.assertEqual(retirement["firewalld_rules"], [{"rich_rule": 'rule family="ipv4" source address="{{ lan_subnet }}" port port="5353" protocol="udp" accept'}])

    def test_missing_preflight_cannot_match_the_remaining_play_pins(self):
        plays = Source().data("playbooks/site.yml")[1:]
        plays[1].pop("vars_files")
        with self.assertRaisesRegex(AuditError, "preflight"):
            source_context(self.fixture(), plays)


if __name__ == "__main__":
    unittest.main()
