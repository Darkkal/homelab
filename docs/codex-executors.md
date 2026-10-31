# Opt-in Codex executors

This source selects no executor by default. It builds one shared image and renders
one private container per entry in `codex_executor_instances` on the service host.
The owner must review and merge the source before the separately authorised #103
installation. No login, task execution or host validation is performed by this source.

Set protected inventory values for every selected instance. The following is a
shape only; replace all placeholders in protected inventory and keep tokens out of
tracked files and command lines:

```yaml
codex_executor_instances:
  - instance: worker-example
    memory: 4g
    pids: 256
    hatchet_host_port: hatchet:7070
    hatchet_api_url: https://OWNER_SELECTED_PRIVATE_API
    hatchet_token: "{{ vault_executor_hatchet_token }}"
    hatchet_ca: "{{ vault_executor_hatchet_ca }}"
    hatchet_api_ca: "{{ vault_executor_hatchet_api_ca }}"
    # Optional; one instance's own role only.
    forgejo_token: "{{ vault_executor_forgejo_token }}"
    git_credentials: "{{ vault_executor_git_credentials }}"
    skills_ca: "{{ vault_executor_skills_ca }}"
    policy:
      instance: worker-example
      role: worker
      model: OWNER_SELECTED_MODEL
      reasoning: medium
      skillsUrl: https://git.example.org/owner/skills.git
      skillsBranch: main
      instructions: OWNER_APPROVED_INSTRUCTIONS
      timeoutSeconds: 600
```

The accepted gRPC endpoint is `hatchet:7070` on the existing network, using the
retained CA and a tenant token. The SDK also requires an API URL. Use the existing
Caddy HTTPS route and provide its local issuer as `hatchet_api_ca`, separately
from the gRPC CA. The API client verifies the issuer and hostname. The SDK receives
explicit endpoint and TLS settings; the container starts with a cleared environment.
The launcher supplies its own clean child environment. Policy and credentials
are stored in separate per-instance `0700` configuration directories, with
`0600` files. Do not copy authentication from another worker. The agent and
control directories are separate private mounts; the application creates the
UID/GID 10001 home inside its private agent mount. Configure a persistent storage
quota externally for each instance as well as the memory and PID limits above.
When any protected bundle changes, Ansible stops and confirms all selected
instances inactive before replacing files. An unchanged apply does not stop them.
An interrupted replacement leaves a `.updating` guard in each affected
configuration directory; startup and login refuse until a successful apply
reconciles all files and clears it. Preserve authentication and run locks and
investigate before retrying.

The build uses only the listed reviewed package files in a versioned local context.
The normal base is `docker.io/docker/sandbox-templates:codex`; set
`codex_executor_base_image` to the same reference with an `@sha256:` digest to
pin temporarily. The existing Podman update service runs the refresh command,
which pulls the base and rebuilds from that local context. A successful build
updates the local tag and `AutoUpdate=local` can restart the containers. A failed
refresh reports failure and does not itself promote an image. Retain image IDs and
base digest before changes; native update rollback is not proof of compatibility.
Changing reviewed source or the base reference creates a new image tag and forces
an explicit build before the new units start. Retained contexts and images are
not automatically deleted.

For first login, after the source and protected inputs have been installed under
an approved #103 packet, stop the selected worker. Set `INSTANCE`, `DATA_DIR`,
and `IMAGE` to the approved instance identity, executor data directory and exact
built image tag, then use the service account's rootless Podman context:

```sh
podman run --rm -it --network homelab --http-proxy=false --security-opt no-new-privileges \
  -v "$DATA_DIR/instances/$INSTANCE/config:/etc/codex-executor:ro,Z" \
  -v "$DATA_DIR/instances/$INSTANCE/control:/var/lib/codex-executor:Z" \
  -v "$DATA_DIR/instances/$INSTANCE/agent:/var/lib/codex-agent:Z" \
  --entrypoint /usr/bin/env "$IMAGE" -i PATH=/usr/local/bin:/usr/bin:/bin \
  HOME=/nonexistent LANG=C.UTF-8 /opt/executor/node /opt/executor/worker.mjs login
```

This prepares the same
role view and runs `/opt/executor/codex login --device-auth` as UID/GID 10001,
with `CODEX_HOME=/var/lib/codex-agent/<instance>/home/.codex` and the managed
configuration. The account must support device login. Do not place authentication
in inventory or copy it between instances. Preserve the agent directory across
rebuilds and updates. Verify the chosen network name, generated unit and UID mapping
before using the command; do not run login as part of Ansible.

A retained `control/<instance>/lock` quarantines the worker before it registers.
Stop the instance, establish that no run or process remains, and only then recover
its lock/workspace under an approved operator procedure. Never delete these
implicitly or retry an uncertain task. A reboot or image update does not clear the
lock. Review network egress to the approved Hatchet, Git and model provider paths;
there are no published worker ports or mounted host runtime sockets.

Before live acceptance the owner/host agent must verify generated Quadlet and
systemd dependencies, private ownership and SELinux access, persistent auth,
login/run configuration, sandbox and skills discovery, quarantine and restart
behavior, update failure and pin behavior, resource/storage limits, reachability,
idempotence and the exact rollback. Revert the opt-in source for source rollback;
later removal of installed units and state requires an operator packet. Do not
claim source checks establish those native behaviors.
