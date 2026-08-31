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

### PR & Issue Titles (Exception)
PR titles and issue titles do **not** use Conventional Commits syntax — use plain, descriptive titles (e.g. "Deploy Homepage dashboard", "Enable Docker service discovery"). Conventional Commits apply only to commit messages, which `release-please` parses for the changelog.

---

## 2. Container Runtime & Infrastructure Conventions

### Podman & Quadlets
- This machine and all target nodes use **Podman** instead of Docker.
- Services are declared using **Podman Quadlets** (`.container`, `.network`, `.volume` systemd unit templates).
- All containers run as **rootless systemd user units** under `~/.config/containers/systemd/`.
- Ensure systemd user lingering is enabled for persistent container background execution.
- Use `quadlet_no_block: true` in group/host variables when containers require background build units or non-blocking systemd starts to prevent Ansible playbook delays.
- **Container Auto-Updates**: Quadlet templates for registry images must include `AutoUpdate={{ <service>_autoupdate | default('registry') }}` under `[Container]` to support automated update cycles via `podman-auto-update.timer` and per-service overrides (`disabled`), unless explicitly necessary to pin to a fixed version number.

### Volume Mounting & Data Persistence Audit Strategy
When persisting data for containerized services, follow this strategy to distinguish user state from application code:
1. **Audit Application Structure**: Inspect the container image filesystem (`podman run --entrypoint /bin/ls ...`) and search codebase imports/references to determine directory roles.
2. **Never Mask App Code / Python Packages**: Directories containing Python modules (`__init__.py`, source code) or application binaries must **not** be mounted as volumes over the host. Mounting over code packages causes `ModuleNotFoundError` or missing executable crashes (exit code 127/1).
3. **Isolate User State**: Mount only true user data directories (checkpoints, models, outputs, presets, user plugins, settings) to subfolders under `~/homelab/<service>/`.
4. **Rootless SELinux Labels**: Always append `:Z` relabeling flags to volume mounts (e.g. `Volume={{ swarmui_data_dir }}/Models:/SwarmUI/Models:Z`) for rootless SELinux permissions.
5. **Register Host Data Directories in `base` Role**: Every new service host persistent data path (e.g. `{{ homelab_data_dir }}/<service>`) **must** be registered in `roles/base/tasks/main.yml` under `Ensure service host data directories exist` (or `Ensure inference host data directories exist`). This guarantees the target host directory exists before any configuration templates (`ansible.builtin.template`) or Quadlet units attempt to write files to it.


### Network & Routing
- Services publish LAN hostnames (`*.home`) resolved via the AdGuard Home DNS server.
- Web services are reverse-proxied through **Caddy** bound to unprivileged host port `80`.
- **New Service `.home` Routing Requirement**: Every new web-accessible service must be configured for `.home` routing:
  1. Configure the `.home` hostname in AdGuard Home DNS and the Caddy route.
  2. Define default upstream target (e.g. `swarmui_upstream: "swarmui:7821"`) in `roles/caddy/defaults/main.yml`.
  3. Add the `reverse_proxy` block to `roles/caddy/templates/Caddyfile.j2`.
- Multi-host overrides should be configured cleanly in `inventory/group_vars/service_hosts.yml`.
- **Homepage Service Discovery & Labeling Requirements**: Homepage populates the dashboard dynamically from container labels read over the Podman socket (see `docs/architecture.md` and `docs/configuration.md` for full details). Every new web-accessible service must be configured for Homepage discovery:
  1. **Add Homepage Labels**: Add `homepage.group`, `homepage.name`, `homepage.icon`, `homepage.href`, and `homepage.description` labels to the container's `.container.j2` Quadlet template.
  2. **Group Alignment & Layout**: Select an existing dashboard group (`Inference`, `Web Services`, `Infrastructure`) or add a matching layout entry to `homepage.settings.yaml.j2` if adding a new group.
  3. **Strict Quadlet Quoting Rules**: Always double-quote multi-word string values (`Label=homepage.group="Web Services"`) and single-quote JSON arrays (`Label=homepage.widget.fields='["a","b"]'`). Unquoted values will be split by the Podman Quadlet generator on whitespace and result in broken container labels.



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
   systemctl --user status caddy sillytavern open-webui llama-swap forgejo
   ```

> **Note:** Build verification is not strictly required when solely modifying markdown documentation files.

---

## 5. GitHub Repository Details

- **Canonical Owner**: `Darkkal`
- **Repository**: `Darkkal/homelab`
