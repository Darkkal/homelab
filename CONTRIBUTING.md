# Contributing Guidelines

Welcome to the **homelab** repository! Whether you are a human developer or an AI agent, please follow these conventions and patterns to maintain high code quality, consistency, and clean git history.

---

## 1. Commit Strategy & Formatting

This repository uses **`release-please`** to automate versioning and changelogs. All commits **must** strictly adhere to the [Conventional Commits specification](https://www.conventionalcommits.org/).

### Commit Message Format

```text
<type>(<scope>): <description>
```

#### Allowed Types
- **`feat`**: New user-facing service, role, or feature.
- **`fix`**: Bug fix in playbooks, roles, or configurations.
- **`docs`**: Documentation updates (README, docs/, CONTRIBUTING).
- **`chore`**: Maintenance, dependency updates, build/tooling changes.
- **`refactor`**: Code restructuring without changing behavior.

#### Examples
- `feat(quadlets): add quadlet template for open-webui`
- `fix(caddy): resolve upstream port forwarding for sillytavern`
- `docs(readme): expand quick start setup steps`
- `chore(deps): update podman quadlet base image versions`

### Incremental Commits
- Avoid single monolithic commits for large or multi-step changes.
- Break work down into small, logical, self-contained units.
- Commit after completing and verifying each component or step.

---

## 2. Container Runtime & Infrastructure Conventions

### Podman & Quadlets
- This machine and all target nodes use **Podman** instead of Docker.
- Services are declared using **Podman Quadlets** (`.container`, `.network`, `.volume` systemd unit templates).
- All containers run as **rootless systemd user units** under `~/.config/containers/systemd/`.
- Ensure systemd user lingering is enabled for persistent container background execution.
- Use `quadlet_no_block: true` in group/host variables when containers require background build units or non-blocking systemd starts to prevent Ansible playbook delays.

### Volume Mounting & Data Persistence Audit Strategy
When persisting data for containerized services, follow this strategy to distinguish user state from application code:
1. **Audit Application Structure**: Inspect the container image filesystem (`podman run --entrypoint /bin/ls ...`) and search codebase imports/references to determine directory roles.
2. **Never Mask App Code / Python Packages**: Directories containing Python modules (`__init__.py`, source code) or application binaries must **not** be mounted as volumes over the host. Mounting over code packages causes `ModuleNotFoundError` or missing executable crashes (exit code 127/1).
3. **Isolate User State**: Mount only true user data directories (checkpoints, models, outputs, presets, user plugins, settings) to subfolders under `~/homelab/<service>/`.
4. **Rootless SELinux Labels**: Always append `:Z` relabeling flags to volume mounts (e.g. `Volume={{ wan2gp_data_dir }}/ckpts:/workspace/ckpts:Z`) for rootless SELinux permissions.


### Network & Routing
- Services publish LAN mDNS hostnames (`*.local`) via Avahi.
- Web services are reverse-proxied through **Caddy** bound to unprivileged host port `80`.
- **New Service `.local` Routing Requirement**: Every new web-accessible service must be configured for `.local` routing:
  1. Add the `.local` hostname (e.g. `swarmui.local`) to `avahi_aliases` in `inventory/group_vars/service_hosts.yml`.
  2. Define default upstream target (e.g. `swarmui_upstream: "swarmui:7821"`) in `roles/caddy/defaults/main.yml`.
  3. Add the `reverse_proxy` block to `roles/caddy/templates/Caddyfile.j2`.
- Multi-host overrides should be configured cleanly in `inventory/group_vars/service_hosts.yml`.


---

## 3. Ansible Conventions & Role Patterns

- **Idempotency**: All playbooks and role tasks must be strictly idempotent. Re-running `site.yml` multiple times should produce zero unexpected state mutations (`changed=0`).
- **Role Structure**: Keep roles modular (`base`, `nvidia`, `quadlets`, `avahi`, `caddy`).
- **Secrets**: Never commit unencrypted sensitive credentials. Use `ansible-vault` for `inventory/group_vars/all/vault.yml`.

---

## 4. Verification Workflow

Before committing any playbook, role, or template changes, verify your changes:

1. **Syntax Check**:
   ```bash
   ansible-playbook playbooks/site.yml --syntax-check --vault-password-file .vault-pass
   ```

2. **Dry Run (Check & Diff)**:
   ```bash
   ansible-playbook playbooks/site.yml --check --diff --vault-password-file .vault-pass
   ```

3. **Deployment Verification**:
   Ensure services build and systemd user services report healthy status:
   ```bash
   systemctl --user status caddy sillytavern open-webui hermes-agent llama-swap forgejo
   ```

> **Note:** Build verification is not strictly required when solely modifying markdown documentation files.

---

## 5. GitHub Repository Details

- **Canonical Owner**: `Darkkal`
- **Repository**: `Darkkal/homelab`
