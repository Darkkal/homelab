# System service lifecycle

`playbooks/vars/system_lifecycle.yml` owns the release's system-service declarations. The generic `decommissioned_services` role retires declared units and exact firewall rules. It does not remove packages, shared daemons, application data or user services.

## Declare ownership

The file contains exactly one `homelab_lifecycle_source` mapping with three required lists:

| List | Record fields | Meaning |
| --- | --- | --- |
| `active_system_services` | `name`, `unit_globs`, `unit_files` | System units explicitly provisioned by enabled repository source |
| `retired_system_services` | The active fields plus `firewalld_rules`, `ufw_rules` | Durable removal declarations for formerly owned system units |
| `preserved_system_units` | Exact service names | Protected units that retirement must not match |

Lists have at most 128 entries. Names are lower-case identifiers, beginning with a letter, with at most 64 characters. Unit targets are bounded exact `.service` names or one literal template family such as `example-alias@*.service`; unrestricted wildcards, paths and shell expressions are rejected. Owned files are direct children of `/etc/systemd/system`, must end in `.service`, and must match that retirement's targets. Each active record needs a unit target or file; each retirement needs a unit target. Include every field, even when its value is `[]`.

Firewalld records contain only `rich_rule`, using the admitted grammar:

```text
rule family="ipv4" source address="192.0.2.0/24" port port="5353" protocol="udp" accept
```

IPv6, TCP and the `drop`/`reject` actions are also admitted. UFW records contain exactly `from_ip`, `port` and `proto`; ports are decimal strings from `1` to `65535`, protocols are `tcp` or `udp`, and source networks must be canonical CIDRs. These are exact rules, without broad port deletion. The example subnet is synthetic.

Unknown keys, null or missing lists, duplicate record names/targets and intersecting records fail admission. Comparisons include names, exact units, template families and file basenames within each list and between active/retired lists. Protected units cannot intersect retirement. Ansible's tagged/lazy containers are admitted without relaxing the schema.

The current source declares no explicitly provisioned system units, preserves `avahi-daemon.service`, and retires the old `avahi-alias@*.service` family, its owned template and the exact LAN UDP 5353 allow rules. An empty active list says nothing about package-installed or running host services. Rootless Quadlets, runner units and auto-update overrides remain user-scoped.

## Admission and convergence

The first site play runs on every selected host with automatic fact gathering disabled, a linear strategy and `any_errors_fatal`. It first rejects overridden discovery registrations, then reads only the default IPv4 networking subset with `ansible.builtin.setup`. The fresh registered result supplies the ordinary LAN fallback; cached or inventory/extra-vars global facts cannot replace it. Missing, malformed or failed results stop the whole selected-host run with redacted errors. The existing `/24` fallback and explicit `lan_subnet`/`host_lan_subnet` precedence remain intact. Outside this launcher the source default retains its original ordinary network-fact fallback.

The complete admission barrier remains factless: before `base`, it validates the explicit caller arguments and compares them with a fresh rendering of the checked-in declaration. Networking reads may occur on invalid admission, but no base, service/firewall discovery or cleanup runs on any host until every selected host passes. Missing source, invalid values, or inventory/extra-vars drift stop the playbook before base/backend work. The role repeats admission immediately before convergence. Reserved discovery variables must be absent at admission; cleanup derives targets directly from validated discovery instead of accepting an overrideable target fact. Its defaults supply no empty-active fallback. Do not bypass the first play with tags, start-at-task, or an alternate caller for deployment.

After admission, read-only native `systemctl list-unit-files` and `list-units --all` discovery is combined with matching enablement symlinks under `/etc/systemd/system` and `/run/systemd/system`. Output, process status and link locations are validated before cleanup. Unreadable paths, unexpected names/states, more than 128 instances, or malformed output fail closed. Uninstantiated templates are excluded from stop/disable; only concrete admitted instances are stopped and disabled. Only explicitly owned files are removed, followed by a system daemon reload when a file changes.

Systemd 259 returns status 1 for a successful unit-file listing with no matches. Only unit-file discovery accepts that status, with empty stdout, stdout lines and stderr and the pinned command module's completed-command message; execution errors, diagnostic output, other failure statuses and failed loaded-unit discovery still stop convergence. Error logging is explicitly directed to the console so invoking environment settings cannot suppress discovery diagnostics. The synthetic backend reproduces this native no-match result for clean-host, check/diff and repeat-apply regressions, with a real command-module test for its result metadata.

When firewalld is running, the role discovers and validates all configured zones before cleanup, then removes each declared rule from both permanent and immediate state in every zone. When UFW is running, it deletes only the declared allow rules. Inactive/unavailable backends are skipped and require explicit operator acceptance; their offline persisted rules have not been cleared. A failed task makes the apply fail, with no automatic retry. Native Ansible loops can attempt other admitted items within the same failing task; later tasks must not be treated as completed.

Missing-definition residents use a separate path: inactive/failed residents need no stop; still-running residents receive a bounded native `systemctl --system stop` request, without asking Ansible's systemd module to operate on a missing definition. Validated owned enablement links are removed directly, including stale links without a resident or definition. Native stop failure propagates before subsequent link/file/firewall removal. Defined units retain normal systemd-module stop/disable handling. Source tracing uses systemd v257's `bus_unit_queue_job_one()`/`unit_stop()` and Ansible core 2.21.5; deployed compatibility still needs operator verification.

Backend selection uses the actual registered `service_facts` result. The registration must be absent before base; inventory/extra-vars cannot replace it or redirect selection through global `ansible_facts`.

Read-only discovery also runs in check mode. Check/diff predicts changes without performing cleanup; it cannot establish actual convergence. Cleanup tasks suppress argument/result logging. Use an approved redacted verifier for operational evidence, rather than verbose output or configuration dumps.

## Add, verify and retire

1. When adding a system-unit producer, declare its exact owned targets in the active list in the same change. Trace enabled plays, roles, handlers, includes, variable sources and generated files. Keep user-unit producers outside this system-only engine.
2. Run the source audit and launcher tests. A source-context/task/template pin change requires inspecting the changed producer and its effective destinations; updating a hash alone is insufficient. Unknown variable sources and execution context must fail the audit. Synthetic destination rendering does not establish deployed inventory values.
3. To retire a producer, remove its provisioning and place its owned targets and exact firewall rules in retirement in the same release. Remove the corresponding active record. Preserve unrelated units, packages and data. Keep the tombstone across subsequent releases so an older host returning later still converges.
4. A proposal to remove a tombstone needs separate evidence that no admitted host can return with its old installed state. A proposal to reuse a retired family needs an explicit migration; intersecting active and retired declarations are rejected.

## Verify source locally

Use isolated Python/Ansible tooling and official pinned collections: ansible-core `2.21.5`, ansible.posix `2.1.0`, community.general `12.4.0`, and PyYAML `6.0.3`. Existing repository suites also require their normal dependencies. Point `ANSIBLE_TEST_COLLECTIONS` at the private collection installation and place the isolated Ansible executables on `PATH`.

```sh
python tests/test_decommission_policy.py
python tests/test_decommission_discovery.py
python tests/test_decommission_source_audit.py
python tests/test_decommission_ansible.py
python tests/test_decommission_native.py
python -m unittest discover -s tests
git diff --check
```

The launcher suite uses synthetic inventory, a copied site/role, a base marker and finite backend action doubles. Only the checked-in LAN default scalar is selected for synthetic default-path tests; the suite never loads production inventory or Vault. Actual Ansible admission, templating, conditions, registrations, loops and notifications run; privileged backend operations, host connections and real firewalls do not. The systemd action double executes the actual pinned module with all commands and host lookups intercepted, including missing-definition failure controls. Module option interfaces are checked against the pinned documentation. Separate controller-only rendering checks exercise source destinations and the runner template in a temporary directory. These tests do not prove host systemd/firewall versions, network reachability, DNS, or exercised rollback.

## Deploy only the accepted merge

Source approval, owner merge, deployment authorisation and operational acceptance are separate decisions. Keep issue #65 open until the operator evidence is accepted.

Before any host action, obtain approval naming the exact merge, selected hosts, backend variants, permitted operations, evidence collection and rollback. Confirm protected inventory/Vault/configuration ownership and effective precedence without exposing values. Verify explicit LAN overrides or the fresh networking fallback and its retained `/24` semantics; no new mandatory subnet setting, private keep-list or policy loader is introduced. Verify effective user-unit destinations, package-installed service boundaries and pinned module/backend compatibility on the selected deployment. Reject drift from the accepted source.

Capture owned-state recovery material in protected operator storage before applying: owned file content/metadata and hashes; concrete instance loaded/running/enabled/masked state; enablement links and their targets; exact firewall rule existence in each zone and permanent/runtime plane, or UFW configuration; and pre-change preservation/DNS evidence. Do not capture or publish unrelated secret-bearing configuration objects. Record bounded counts, approved names and correlation identifiers in the PR. Verify that recovery access remains reachable under the restored service/network state.

Run the normal site launcher from the exact merge, using the approved inventory, Vault source and privilege mechanism. First perform syntax and protected check/diff assessment; do not publish raw diffs, arguments, process environments or logs containing protected inventory/secrets. The full site launcher includes other existing provisioning roles, so their permitted effects must be included in deployment approval. Apply once only when the predicted targets match the captured owned state. On unexpected scope, failed discovery/backend, preservation failure, drift or exposure, stop; do not replay automatically.

After apply, verify:

- No admitted concrete alias is running or enabled; the owned template and its enablement links are absent. A stale loaded entry can persist until systemd releases it; a missing-definition entry must be inactive/failed without owned enablement links, rather than a live alias.
- Exact declared firewall rules are absent in every relevant plane/zone; unrelated rules, Avahi daemon/package/data, user units and accepted AdGuard/Caddy/runner/trust state are preserved.
- A second approved apply makes no further retirement changes. Check a clean host separately; unavailable backends require explicit acceptance or a separately approved cleanup.
- DHCP advertises the intended resolver and representative clients, including Android, resolve the approved `.home` names through AdGuard and reach Caddy. Use the owner's approved test names and redacted evidence.

## Restore installed owned state

A source revert restores provisioning code only. It cannot reconstruct deleted installed files, links or firewall state.

With fresh rollback authority, restore the captured owned files with their metadata, reload the system manager, restore only the recorded links and instance enablement/masking/running states, and reinstate only the rules that existed in the captured zones/planes or UFW configuration. Do not create rules or start instances that were previously absent. Keep unrelated state unchanged and verify rollback access, preservation and DNS again. If continued operation needs the former producer, separately approve the source revision and launcher that reproduce it; do not run the retirement merge again over restored aliases.

Exercise the approved rollback and record its result before operational acceptance. A failed or unreachable rollback, unavailable backend, unverified client DNS or changed unrelated state leaves #65 open.
