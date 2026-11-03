# Native Forgejo workflows (#104)

The source is opt-in. A selected Hatchet native webhook receives Forgejo events;
its event-key expression routes eligible families to their matching workflows.
The workflow checks a persisted native receipt and current Forgejo state before
submitting a role job. The role executor checks those facts again after queueing.
No live webhook is created or retargeted by this source.

## Protected policy

Set `routing_policy` for each selected executor as a JSON string from protected
inventory, and supply its own `forgejo_token` and `forgejo_ca`. Absence of the
policy preserves the existing manual worker. Selected malformed policy fails
startup. Ansible stores the files in the existing private instance configuration
and uses its stopped-update guard; a policy change is not a hot reload. Every
selected role must use the same mapping and routing policy. The designated `controlInstance` registers family workflows and the permission
helper; other selected instances register routed tasks for their own role. The
control instance cannot launch an agent, including through manual or login mode,
while this policy is selected. It is not eligible to run a routed role task, so a separate selected
replica is required for any role that also owns the control worker. The non-effectful
family task releases its Hatchet slot while waiting for the helper; execution
workers retain their slot during the final permission check and agent run. All examples below are placeholders:

```yaml
routing_policy: '{{ vault_native_routing_policy | to_json }}'
forgejo_ca: '{{ vault_forgejo_ca }}'
```

The protected JSON object has `webhookName`, `controlInstance`, `forgejoOrigin` (an HTTPS origin),
`dedupeSeconds` (60–604800), `mapping` and `routing`. Mapping has nonempty
`families`, `repositories` (`owner/repo`) and `actors` arrays. Routing has `roles`
with exactly `planner`, `worker` and `reviewer` account names, plus `owners` and
trusted `reviewers` arrays and a nonempty `requiredChecks` list of exact CI contexts. These identities are operator policy, not task input.
Only supported routing families may be selected. Well-formed non-work families
and unlisted identities map to the reserved `forgejo-ignored-v1` key.

The `eventKeyExpression` and `staticPayload` exports in
`forgejo-mapping.mjs` produce the native webhook configuration from the same
protected mapping object. Store the generated configuration privately and use it
only under E's separate provider authority. Static payload keys override colliding
body keys in the pinned Hatchet receiver. Do not print the generated static payload
or policy. For an approved E configuration step, the mapping can be written to a
new private file without printing its contents (run from this repository; both
paths are operator-selected protected paths):

```sh
node --input-type=module - "$ROUTING_POLICY_FILE" "$MAPPING_OUTPUT_FILE" <<'JS'
import { readFile, writeFile } from 'node:fs/promises';
import { eventKeyExpression, staticPayload } from './roles/quadlets/files/codex-executor/forgejo-mapping.mjs';
const policy = JSON.parse(await readFile(process.argv[2], 'utf8'));
await writeFile(process.argv[3], JSON.stringify({ eventKeyExpression: eventKeyExpression(policy.mapping),
  staticPayload: staticPayload(policy.mapping) }), { flag: 'wx', mode: 0o600 });
JS
```

The generated file is an input for native webhook administration, not an
instruction to create or update a webhook. Configure native HMAC SHA256/hex with
the Forgejo signature header and an independently protected signing secret. Set
`returnEventAsResponsePayload` to false. Use the matching family patterns from
`triggerPattern`; do not register application consumers that match the ignored
namespace or unrelated wildcard triggers. E must verify these actual subscriptions.

Set `hatchet_webhook_body_limit_enabled: true` for the opt-in Caddy limit on native
webhook paths. It limits reads to 1 MiB and affects all such paths on that Caddy
site. E must verify the actual request path cannot bypass the selected limiter and
that the installed Caddy supports it. The native receiver otherwise reads the body
without that streaming bound. No playbook, webhook, or live service action is part
of this source work.

## Receipts and boundaries

Hatchet may retain an incoming body and enqueue internal processing before a
workflow is selected. A successful native HTTP response is an ingress receipt,
not role completion. Invalid authentication and malformed input use native error
responses; exhausted or failed ingestion is not success. Ignored keys must match
no application workflow. E must bind retention, event limits, hook scope and retry
behavior as well as the intended tenant and endpoint before a live canary.

The native permission helper runs only on the configured existing control instance.
It reads current repository and actor IDs plus actual permissions using that
instance’s own credential; other roles never receive that credential. The same
capability is checked again on the execution path immediately before agent launch.
Forgejo 16.0.6 requires instance-admin or repository-admin authority to query
another user’s permission, and a repository-specific token does not necessarily
permit the admin override. No eligible credential is established by this source.
Before E, bind the account, effective scopes, token resource mode and approved
repository scope; a missing helper, 403, timeout or mismatched identity stops
work as unknown. An insufficient permission is denial. Do not broaden tokens
or share them between roles merely to satisfy this check.

The event key includes the Forgejo delivery UUID, which is not signed by the body
HMAC. A workflow retrieves the native event by its trigger ID and requires the
selected webhook name and key to match before canonical reads. If persistence is
not yet visible or a read is ambiguous, it returns unknown without replay. Native
role jobs use an operator-selected bounded idempotency window and shared
`GROUP_ROUND_ROBIN` work-item concurrency. Neither is an exactly-once guarantee;
a duplicate after the window or an uncertain external effect requires operator
assessment. Submission uses one SDK attempt and returns a run ID only after the
SDK supplies it. The executor rechecks the receipt, actor permission, open state,
current head and target before invoking the agent. Event content never becomes
model, tool, profile or credential configuration.

This source does not establish live ingress, persisted receipt timing, permissions,
role routing, replica concurrency, quota, provider retry, or model behavior. E's
owner-selected host agent must validate those and the forward/restored old path;
unknown results stop rather than trigger automatic replay. Reverting this source
leaves the current webhook route untouched.
