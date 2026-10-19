# Opt-in Codex executor (#101)

Source/process slice for #77/A. Nothing selects this package in Ansible, starts a
service, consumes jobs by default, or changes Misso/PiClaw. #102 renders protected
deployment configuration; #103 owns native validation, login and the first real
three-role inference; #104 owns Forgejo routing/mutations. Revert by removing this
directory. Preserve operator state independently of source rollback.

## Interface for deployment

Build with `podman build --build-arg BASE_IMAGE=<immutable-reference> -f Containerfile .`.
The base must be the approved `docker.io/docker/sandbox-templates:codex` candidate
resolved to a digest, with Node >=22 and an apt-based filesystem. No image build
was run for this source change. Record that digest, resulting image digest,
architecture, Node, Git, Bubblewrap and util-linux versions during owner validation.
The npm lock selects Hatchet SDK **1.38.0**, Codex SDK/CLI **0.163.0** and YAML
**2.8.1**, including CLI platform packages. `npm ci --ignore-scripts` installs them;
`/opt/executor/codex` always selects this CLI rather than the template's CLI.
OS packages remain dependent on the selected base's apt repositories; the npm lock
does not claim to pin those repositories or prove a byte-identical image rebuild.

Use a separate rootless Podman container and dedicated private state volumes for
each instance. Container UID 0 runs trusted preparation/control; the launcher uses
`setpriv` to drop to outer UID/GID 10001, clears supplementary groups, sets
no-new-privileges, then creates mandatory Bubblewrap user/mount/PID/IPC namespaces.
The child UID is also 10001, with all capabilities dropped. Rootless compatibility
is **pending**, including ordinary path binds and nested Codex sandbox support. A
namespace/permission failure refuses the run; do not enable privileged mode,
disable security profiles, add a host socket, or bypass Codex approval/sandboxing.

B must mount `/etc/codex-executor` as private, container-root-owned mode 0700,
containing `policy.json` mode 0600. Mount `/var/lib/codex-executor` as a dedicated
root-owned mode 0700 persistent volume, using rootless SELinux relabeling `:Z`.
It contains only trusted source/preparation state, locks and the prepared-run record.
Separately mount `/var/lib/codex-agent` as a dedicated root-owned mode **0711**
persistent volume with `:Z`. This parent contains only agent-visible data: each
instance parent is root-owned 0711; home/workspace are owned by UID/GID 10001,
mode 0700; published config and skills are root-owned, readable and not agent-writable.
Never place source/control credentials in this second tree. Explicit publication
modes permit Bubblewrap's dropped UID to resolve/stat the ordinary bind paths,
including under a restrictive launcher umask. The control parent remains 0700.
Never share either volume across instances/replicas or mount other roles' state.
No control credentials may be installed beneath `/usr`, `/bin`, `/lib`, `/lib64`
or `/opt/executor`: those immutable image paths are visible to the child. B must
also bound container memory, process count and persistent storage externally.

`policy.json` is an exact object; unknown/missing fields fail closed:

```json
{
  "instance": "worker-example",
  "role": "worker",
  "model": "OWNER_SELECTED_MODEL",
  "reasoning": "medium",
  "skillsUrl": "https://git.example.org/owner/skills.git",
  "skillsBranch": "main",
  "instructions": "Owner-approved role instructions go here.",
  "timeoutSeconds": 600
}
```

Instance: lowercase identifier, at most 48 characters. Role: `planner`, `worker`,
or `reviewer`. Model: protected identifier, at most 100 characters. Reasoning:
`low|medium|high|xhigh`. Timeout: integer 30–3600 seconds, including preparation.
Instructions: nonempty, at most 16 KiB. Source: HTTPS without URL credentials,
query or fragment; branch: bounded Git branch spelling. These values are read once
at startup; changing policy requires restart. The selected role alone registers
`codex-planner`, `codex-worker`, or `codex-reviewer`, respectively, with **slots: 1**,
zero retries, no events/cron, and role/instance scheduling labels. Planner/reviewer
use `read-only`; worker uses `workspace-write`. All use `untrusted` approvals and
disable tool network access/web search. Labels and task text cannot select a role.

The engine SDK uses its normal protected Hatchet connection settings in the
trusted worker environment. Optional private skill-source authentication uses only
`/etc/codex-executor/git-credentials`, root-owned mode 0600, via Git's noninteractive
store helper. Never put credentials into the policy URL or task. B owns engine TLS
and source CA configuration; the child receives only system CA certificates and
DNS configuration, not private engine keys. There is no credential broker here.

## Entry points (owner invocation only)

The entry point is `/opt/executor/node /opt/executor/worker.mjs MODE`:

- `manual`: read exactly `{"text":"work instruction"}` on stdin (64 KiB text,
  128 KiB envelope, 30-second input deadline). No task-supplied paths, role, model,
  environment, credentials, UID, updater settings or resumption identifiers.
- `worker`: explicitly register the protected role with the native Hatchet engine.
- `login`: prepare the same isolated view, then run that exact CLI's
  `login --device-auth`, as the same UID with the same home/configuration. This
  interactive operator command alone displays the native URL/code. Open it in a
  desktop browser; no container browser or copied browser cookies are needed.
- Any other mode (including the image default `disabled`) exits with bounded
  refusal metadata and does not register a worker or start Codex.

Actual login remains #103's separately authorized operation. ChatGPT subscription
mode omits SDK API-key injection, supplies a fresh explicit child environment with
no API/provider/base/proxy overrides, and forces `chatgpt` login with the built-in
OpenAI provider. Auth/quota failure has no API fallback path. Persistent per-instance
Codex home contains the CLI's refreshable auth/session/cache; never import PiClaw
credentials, bake tokens into the image, share writable auth or overwrite refreshed
tokens from Vault on apply. This configuration does not prove account eligibility.

## Preparation and terminal behavior

A root-owned instance lock covers preparation, execution and cleanup, supplementing
the engine slot. Each run fetches the configured publishing ref with a clean Git
environment, hooks disabled, isolated Git configuration, and no upstream scripts.
Dirty/masked state, unsupported local configuration, non-forward history, special
file modes/submodules/attributes, malformed YAML metadata, duplicate skill names,
over 2000 tracked files or over 8 MiB of material fail before SDK startup. Native
skills are materialized from tracked blobs only; untracked content is never used.
The shared `skill-source-sync` entry is replaced only in this deployment's view.
The prepared SHA and generated run/role/instance identities are saved in protected
`prepared.json` before launch and returned with bounded outcome metadata.

Only that instance's home, scratch workspace, published configuration, skills and
empty skill roots are bound into the agent namespace. No extra descriptors cross
the UID boundary. The agent cannot traverse the private source/control parent.
Managed config/skills and alternative native skill
roots are mounted read-only. Each run starts a fresh SDK thread; resume is unsupported.
The managed view remains unchanged until the slot finishes; the next run refreshes it.
Workspace is scratch, deleted on completion/refusal/cancellation. This package returns
status, not model text or repository artifacts; routing/durable work publication is D.

Outcomes are `completed`, `failed`, `unknown`, `refused`, `cancelled`, `timed_out` or
`busy`. An unknown outcome may already have caused effects: there is no automatic
retry or exactly-once guarantee. No SDK event bodies, prompts, commands, raw errors
or engine diagnostics are forwarded. Local subprocesses have time/output bounds;
timeouts/cancellation kill the outer process group and Bubblewrap's PID namespace
contains descendants. Shutdown has a ten-second bound. Native cleanup proof is pending.
Work admission stays closed until readiness succeeds and closes immediately on
shutdown. Readiness/start failures abort, stop and await the resident worker before
reporting refusal; a hard deadline remains armed through cleanup and process exit.
Manual/login runs are tracked through subprocess close, asynchronous workspace/lock
cleanup and result-output flush; signal shutdown awaits that operation before exit.
A crash can leave a lock; an operator must establish that no run remains before
removing it. Failed initial preparation may leave an unborn source repository;
inspect/reset only that private source directory while stopped, never use stale skills.

## Verification status

Source checks: `npm ci --omit=dev --ignore-scripts --no-audit --no-fund`, `npm run check`,
and imports of the actual pinned SDK/YAML exports. No dedicated tests, fixtures,
container harness, new CI or host/playbook runs were added while #94 is open.
There is no tracked CI configuration in this checkout; this is not evidence of
server-side required checks or an independent review. Those remain separate gates.

Before live acceptance, the owner/host agent must record the selected image/CLI
identities, native skills discovery and denied writes, outer/inner UID and control
credential isolation, per-instance state/restart persistence, one-slot behavior,
next-run refresh/stable SHA, failure-before-Codex, bounded descendant cleanup,
and ChatGPT-only login/refresh/quota/no-fallback behavior. No real developer auth
or model call was accessed here. Keep #101 open until required acceptance is observed.

Interface sources: [Codex SDK](https://developers.openai.com/codex/sdk/),
[authentication](https://developers.openai.com/codex/auth/),
[configuration](https://developers.openai.com/codex/config-reference/),
[skills roots](https://developers.openai.com/codex/skills/),
[Hatchet SDK](https://docs.hatchet.run/reference/typescript), and
[Bubblewrap](https://github.com/containers/bubblewrap).
