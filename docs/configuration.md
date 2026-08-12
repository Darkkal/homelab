# Configuration Reference

This document provides a detailed reference for all configuration variables across Ansible group variable files, role defaults, and Ansible Vault secrets.

---

## Inventory & Group Variables

Customizing deployment options is done by editing files under `inventory/group_vars/`.

### Shared Configuration (`inventory/group_vars/all/vars.yml`)

These settings apply to all target hosts across all host groups:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `homelab_data_dir` | `~/homelab` | Base directory path on target machines for persistent application data storage. |
| `quadlet_dir` | `~/.config/containers/systemd` | Directory path where user systemd Podman Quadlet container files are deployed. |
| `network_name` | `homelab.network` | Shared Podman bridge network name connecting container instances. |
| `enable_podman_auto_update` | `true` | Enables and starts the `podman-auto-update.timer` user systemd unit for automated container updates. |
| `podman_auto_update_schedule` | `Tue *-*-* 04:00:00` | Schedule format for `podman-auto-update.timer` (every Tuesday at 4am; systemd `OnCalendar` expression). |
| `<service>_autoupdate` | `registry` | Per-service auto-update policy set in Quadlet `AutoUpdate` directive (`registry`, `disabled`, or `local`). |

#### Managing Persistent Service Directories

All application container data is stored under subdirectories of `homelab_data_dir` (`~/homelab/<service>`).

When implementing a new service or expanding configuration storage:

1. **Define Data Directory Variables**:
   Define `<service>_data_dir: "{{ homelab_data_dir }}/<service>"` in `inventory/group_vars/service_hosts.yml` or `inventory/group_vars/inference_hosts.yml`.
2. **Register Directory Creation in Base Role (`roles/base/tasks/main.yml`)**:
   Add `{{ homelab_data_dir }}/<service>` (and any required subdirectories) to the directory loops in `roles/base/tasks/main.yml`:
   - Under `Ensure service host data directories exist` for app services (`service_hosts`).
   - Under `Ensure inference host data directories exist` for AI/GPU model services (`inference_hosts`).
   *Note: This step is mandatory so Ansible creates the target directory before any template deployment tasks or systemd container services run.*
3. **Mount Subfolders & Apply SELinux Relabeling**:
   Mount persistent directories in container Quadlet templates (`.container.j2`) with SELinux `:Z` flags:
   ```ini
   Volume={{ searxng_data_dir }}:/etc/searxng:Z
   ```

---

### Inference Host Configuration (`inventory/group_vars/inference_hosts.yml`)

These settings apply to target hosts in the `inference_hosts` group:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `model_dir` | `~/homelab/models` | Target host directory containing downloaded GGUF model files. |
| `llama_swap_config_dir` | `~/homelab/llama-swap` | Path for `llama-swap` configuration files and model swap profiles. |
| `llama_swap_port` | `8080` | Host port for direct `llama-swap` API access. |
| `gpu_layers` | `99` | Default number of model layers to offload to GPU VRAM. |
| `context_size` | `32768` | Default context window size (tokens) for inference model execution. |
| `auto_unload_seconds` | `600` | Inactivity timeout (seconds) before idle models are automatically unloaded from VRAM. |
| `swarmui_data_dir` | `~/homelab/swarmui` | Directory for SwarmUI persistent data and outputs. |
| `swarmui_port` | `7801` | Host web port for direct SwarmUI WebUI access. |
| `swarmui_image` | `localhost/swarmui:latest` | Container image repository and tag for SwarmUI built natively from Git by systemd Quadlet. |
| `quadlet_no_block` | `true` | When `true`, Ansible issues non-blocking systemd service start and restart commands (`no_block: true`). |

#### Non-Blocking Systemd Service Starts (`quadlet_no_block`)

When `quadlet_no_block: true` is set in inventory variables (enabled by default in `inference_hosts.yml`), Ansible executes systemd container start and restart tasks with `no_block: true` (equivalent to `systemctl start --no-block`).

This prevents Ansible playbook execution from blocking on long-running container startup tasks or on-demand container image builds (such as `swarmui-build.service`), allowing the playbook run to complete immediately while systemd manages the job asynchronously in the background.

#### SwarmUI Volume Structure

SwarmUI persistent data, models, and generated outputs are stored in isolated subdirectories within `swarmui_data_dir` (`~/homelab/swarmui`):

| Host Path | Container Target | Purpose |
| :--- | :--- | :--- |
| `~/homelab/swarmui/Data` | `/SwarmUI/Data` | Core application settings and state |
| `~/homelab/swarmui/Models` | `/SwarmUI/Models` | SwarmUI image models (SDXL, Flux, LoRAs, VAEs) |
| `~/homelab/swarmui/Output` | `/SwarmUI/Output` | Generated images and media output |
| `~/homelab/swarmui/dlbackend` | `/SwarmUI/dlbackend` | Deep learning backends, venvs, and self-starting ComfyUI dependencies |
| `~/homelab/swarmui/DLNodes` | `/SwarmUI/src/BuiltinExtensions/ComfyUIBackend/DLNodes` | Downloaded custom nodes and backend extension nodes |

---

## Service Host Configuration (`inventory/group_vars/service_hosts.yml`)

These settings apply to target hosts in the `service_hosts` group:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `avahi_aliases` | List of `.local` hostnames | Hostnames published via LAN mDNS (`sillytavern.local`, `forgejo.local`, `llamaswap.local`, `openwebui.local`, `swarmui.local`). |
| `forgejo_port` | `3003` | Host web port for direct Forgejo access. |
| `forgejo_image` | `codeberg.org/forgejo/forgejo:16` | Forgejo container image. Tracks the latest major (auto-updated via the `registry` label). Bumped off the old `:10` pin for the LFS upload quota nil-pointer fix (v10/v12 crash on LFS batch uploads when `ctx.Doer` is nil). Forgejo publishes no `:latest` tag, so `:16` is the newest major. |
| `forgejo_root_url` | `http://forgejo.local/` | Forgejo `ROOT_URL` (`[server] ROOT_URL`). Must match the primary site URL so generated links (web UI, mail, webhooks, OAuth2) are correct and the admin-page mismatch warning is not shown. |
| `forgejo_populate_squash_comment_with_commit_messages` | `true` | Include all PR commit messages in default squash-merge messages (`[repository] POPULATE_SQUASH_COMMENT_WITH_COMMIT_MESSAGES`). |
| `forgejo_lfs_start_server` | `true` | Enable Git LFS support (`[server] LFS_START_SERVER`). |
| `forgejo_lfs_path` | `/data/git/lfs` | Container path for Git LFS content (`[lfs] PATH`). Must be under a directory writable by the container's git user; maps to host `~/homelab/forgejo/git/lfs` via the `/data` volume mount. |
| `openwebui_data_dir` | `~/homelab/open-webui` | Directory for Open WebUI persistent data. |
| `openwebui_port` | `8081` | Host web port for direct Open WebUI access. |
| `openwebui_openai_api_base_url` | `http://llama-swap:8080/v1` | Primary OpenAI-compatible API endpoint for Open WebUI backend calls. |
| `openwebui_openai_api_base_urls` | `http://llama-swap:8080/v1` | Semicolon-separated list of OpenAI-compatible API endpoints for Open WebUI. |
| `openwebui_openai_api_keys` | `sk-dummy` | Semicolon-separated list of OpenAI API keys corresponding to `openwebui_openai_api_base_urls`. |
| `st_data_dir` | `~/homelab/sillytavern` | Directory for SillyTavern persistent data. |
| `sillytavern_port` | `8000` | Host web port for direct SillyTavern access (container internal port `8000`). |
| `sillytavern_openai_api_base_url` | `http://llama-swap:8080/v1` | OpenAI-compatible API endpoint for SillyTavern LLM backend calls. |
| `homepage_data_dir` | `~/homelab/homepage` | Directory for Homepage dashboard persistent config. |
| `homepage_port` | `3002` | Host web port for direct Homepage dashboard access (container internal port `3000`). |
| `homepage_allowed_hosts_extra` | `[]` | Extra `host:port` entries appended to `HOMEPAGE_ALLOWED_HOSTS` (in addition to `homepage.local`, the host's default LAN IPv4 address, and loopback), e.g. `['desktop.local:3002']`. |
| `glances_data_dir` | `~/homelab/glances` | Directory for the Glances password file and runtime data. |
| `glances_port` | `61208` | Host web port for direct Glances access (container internal port `61208`). |
| `glances_username` | `glances` | Glances web server basic auth username (from `vault_glances_username`). |
| `glances_password` | `""` | Glances web server basic auth password (from `vault_glances_password`). When empty, Glances runs without authentication. |
| `searxng_data_dir` | `~/homelab/searxng` | Directory for SearXNG settings and configuration. |
| `searxng_port` | `8082` | Host web port for direct SearXNG search interface access (container internal port `8080`). |
| `playwright_port` | `3004` | Host web port for direct Playwright browser scraping service access (container internal port `3000`). |
| `piclaw_data_dir` | `~/homelab/piclaw` | Directory for PiClaw persistent configuration and workspace files. |
| `piclaw_port` | `8083` | Host web port for direct PiClaw AI workspace access (container internal port `8080`). |
| `uptrace_data_dir` | `~/homelab/uptrace` | Directory for Uptrace config, ClickHouse (`uptrace/ch`), PostgreSQL (`uptrace/pg`), and the ClickHouse Prometheus drop-in (`uptrace/ch-config`). |
| `uptrace_port` | `14318` | Host web port for direct Uptrace UI access (container internal port `80`). |
| `uptrace_image` | `docker.io/uptrace/uptrace:2.0.3` | Uptrace container image. Pinned to a stable release; Uptrace only supports next-minor upgrades, so `uptrace_autoupdate` defaults to `disabled`. |
| `uptrace_clickhouse_image` | `docker.io/clickhouse/clickhouse-server:26.3` | ClickHouse telemetry store image. |
| `uptrace_postgres_image` | `docker.io/library/postgres:17-alpine` | Uptrace PostgreSQL metadata store image. |
| `uptrace_redis_image` | `docker.io/library/redis:6.2.2-alpine` | Uptrace Redis cache image. |
| `uptrace_otelcol_image` | `docker.io/otel/opentelemetry-collector-contrib:0.123.0` | OpenTelemetry Collector image handling host metrics, synthetic checks, and Prometheus scraping. |
| `uptrace_admin_email` | `admin@homelab.local` | Initial Uptrace admin login email (from `vault_uptrace_admin_email`). |
| `uptrace_admin_password` | `""` | Initial Uptrace admin login password (from `vault_uptrace_admin_password`). |
| `uptrace_project_token` | auto-generated (`~/homelab/.uptrace_project_token`) | Write-only OTLP project token used in DSNs and collector ingestion. |
| `uptrace_secret` | auto-generated (`~/homelab/.uptrace_secret`) | Uptrace `service.secret` for cryptographic operations. |
| `uptrace_pg_password` | auto-generated (`~/homelab/.uptrace_pg_password`) | Uptrace PostgreSQL password. |
| `uptrace_ch_password` | auto-generated (`~/homelab/.uptrace_ch_password`) | Uptrace ClickHouse password. |
| `uptrace_retention_traces` | `7 DAY` | ClickHouse TTL for trace data. |
| `uptrace_retention_metrics` | `30 DAY` | ClickHouse TTL for metric data. |
| `uptrace_retention_logs` | `7 DAY` | ClickHouse TTL for log data. |

#### Adding New Services to the Homepage Dashboard

To register a new containerized service on the Homepage dashboard:

1. **Add Discovery Labels in Quadlet Template (`<service>.container.j2`)**:
   Add standard `homepage.*` labels to the `[Container]` block of your Jinja2 template:
   ```ini
   Label=homepage.group="Web Services"
   Label=homepage.name="SearXNG"
   Label=homepage.icon=searxng.png
   Label=homepage.href=http://searxng.local
   Label=homepage.description="Self-hosted search aggregator"
   ```

2. **Select or Create a Dashboard Group**:
   - Assign `homepage.group` to an existing layout group: `Inference`, `Web Services`, or `Infrastructure`.
   - If creating a new group, add a matching entry under `layout:` in `roles/quadlets/templates/homepage.settings.yaml.j2`.

3. **Configure mDNS & Reverse Proxy**:
   - Add `.local` hostname to `avahi_aliases` in `inventory/group_vars/service_hosts.yml`.
   - Add default upstream in `roles/caddy/defaults/main.yml` and routing block in `roles/caddy/templates/Caddyfile.j2`.

4. **Adhere to Quadlet Quoting Rules**:
   - Double-quote multi-word label strings: `Label=homepage.group="Web Services"`
   - Single-quote JSON arrays: `Label=homepage.widget.fields='["upstreams","requests"]'`

#### Glances Runtime Configuration

Glances runs as a rootless Podman Quadlet on `service_hosts` and exposes its REST API to the Homepage Glances info widget over the shared `homelab.network`.

- **Web server mode**: `GLANCES_OPT=-w` enables the FastAPI web server/REST API on container port `61208` (published to `glances_port` on the host and proxied by Caddy at `glances.local`).
- **Host visibility**: `PodmanArgs=--pid=host` shares the host PID namespace so CPU/memory/process stats reflect the host. The host OS info and temperature sensors are visible via read-only `Volume=/etc/os-release:/etc/os-release:ro` and `Volume=/sys:/sys:ro` mounts.
- **Host disk usage**: The host root filesystem is mounted read-only at `Volume=/:/host:ro`; the Homepage widget monitors it with `disk: /host`.
- **Authentication**: When `vault_glances_password` is set, Glances runs with `--password -u <username>` and reads the hashed password from `glances_data_dir/<username>.pwd` (generated by the `glances_pwd` filter, matching Glances' pbkdf2-sha256 format). The Homepage widget is wired with the same credentials. Ansible only deploys the password file and enables auth when the vault password is non-empty.
- **Homepage widget**: `homepage.widgets.yaml.j2` declares a `glances` info widget (`version: 4`) showing CPU, memory, CPU temp, uptime, and `/host` disk usage. `homepage.custom.css.j2` (rendered to `custom.css`) makes it span the full header row above search/datetime.

#### SillyTavern Volume Structure & Data Migration

SillyTavern's persistent data is mapped to `st_data_dir` (`~/homelab/sillytavern`) via four standard volume mounts:

| Host Path | Container Target | Purpose |
| :--- | :--- | :--- |
| `~/homelab/sillytavern/config` | `/home/node/app/config` | Server configuration (`config.yaml`) |
| `~/homelab/sillytavern/data` | `/home/node/app/data` | Characters, chats, worlds, group chats, presets, and user settings (`user/settings.json`) |
| `~/homelab/sillytavern/plugins` | `/home/node/app/plugins` | Server-side plugins |
| `~/homelab/sillytavern/extensions` | `/home/node/app/public/scripts/extensions/third-party` | Third-party client extensions |

##### Migrating Data from Existing SillyTavern Instances

To migrate characters, chats, and settings from a standalone Docker Compose instance:

1. Stop the active user systemd service:
   ```bash
   systemctl --user stop sillytavern
   ```
2. Copy your existing `./data`, `./plugins`, and `./extensions` content into `~/homelab/sillytavern/`:
   ```bash
   cp -r /path/to/old/sillytavern/data/* ~/homelab/sillytavern/data/
   cp -r /path/to/old/sillytavern/plugins/* ~/homelab/sillytavern/plugins/
   cp -r /path/to/old/sillytavern/extensions/* ~/homelab/sillytavern/extensions/
   ```
3. Re-run the site playbook to apply rootless SELinux permissions (`:Z`) and restart the container:
   ```bash
   ansible-playbook playbooks/site.yml --ask-become-pass --vault-password-file .vault-pass
   ```

---

## Role Defaults & Upstreams

### Caddy Reverse Proxy Defaults (`roles/caddy/defaults/main.yml`)

Caddy upstream variables define where requests to `*.local` hostnames are routed. In single-machine setups, these default to container names on the `homelab.network` bridge network. For multi-host setups, these can be overridden in `inventory/group_vars/service_hosts.yml` with physical IP addresses or hostnames.

| Variable | Default Upstream Target | Proxied Hostname |
| :--- | :--- | :--- |
| `sillytavern_upstream` | `sillytavern:8000` | `sillytavern.local` |
| `forgejo_upstream` | `forgejo:3003` | `forgejo.local` |
| `llama_swap_upstream` | `llama-swap:8080` | `llamaswap.local` |
| `openwebui_upstream` | `open-webui:8081` | `openwebui.local` |
| `swarmui_upstream` | `swarmui:7801` | `swarmui.local` |
| `homepage_upstream` | `homepage:3000` | `homepage.local` |
| `glances_upstream` | `glances:61208` | `glances.local` |
| `piclaw_upstream` | `piclaw:8080` | `piclaw.local` |
| `uptrace_upstream` | `uptrace:80` | `uptrace.local` |

---

## Secrets Management (Ansible Vault)

Sensitive configuration values (passwords, API tokens) are encrypted in `inventory/group_vars/all/vault.yml`.

> [!IMPORTANT]
> The encrypted file `inventory/group_vars/all/vault.yml` is listed in `.gitignore` and is **not committed to version control**.

### Supported Vault Keys

| Secret Variable | Description | Safe Default (if omitted) |
| :--- | :--- | :--- |
| `vault_forgejo_admin_user` | Initial admin username for Forgejo | `admin` |
| `vault_forgejo_admin_password` | Initial admin password for Forgejo | `""` (no default password) |
| `vault_forgejo_admin_email` | Initial admin email for Forgejo | `admin@homelab.local` |
| `vault_forgejo_api_token_homepage` | API access token for Forgejo (used by the Homepage dashboard widget; fallback: `vault_forgejo_api_token`) | `""` (no widget) |
| `vault_sillytavern_user` | HTTP basic auth username for SillyTavern | `admin` |
| `vault_sillytavern_password` | HTTP basic auth password for SillyTavern | `""` (no basic auth password) |
| `vault_sillytavern_api_key` | SillyTavern API access key | `""` |
| `vault_forgejo_api_token_piclaw` | Forgejo API access token for PiClaw container | `""` |
| `vault_github_api_token_piclaw` | GitHub Personal Access Token for PiClaw container (`GH_TOKEN` / `GITHUB_TOKEN`) | `""` |
| `vault_piclaw_api_token` | Bearer token API key for PiClaw state APIs (`/api/state`, `/api/state/events`) | Auto-generated unique 64-char hex secret (`~/homelab/.piclaw_api_token`) |
| `vault_glances_username` | Basic auth username for the Glances web server | `glances` |
| `vault_glances_password` | Basic auth password for the Glances web server | `""` (no auth) |
| `vault_uptrace_admin_email` | Initial Uptrace admin login email (seeded via `seed_data`) | `admin@homelab.local` |
| `vault_uptrace_admin_password` | Initial Uptrace admin login password (seeded via `seed_data`) | `""` |
| `vault_uptrace_project_token` | Uptrace project token used in OTLP DSNs and collector ingestion | Auto-generated (`~/homelab/.uptrace_project_token`) |

### `vault.yml` File Template

Unencrypted template structure before executing `ansible-vault encrypt`:

```yaml
---
# Forgejo Initial Credentials & Dashboard Tokens
vault_forgejo_admin_user: "admin"
vault_forgejo_admin_password: "SuperSecretForgejoPassword"
vault_forgejo_admin_email: "admin@homelab.local"
vault_forgejo_api_token_homepage: "SuperSecretForgejoApiTokenForHomepage"
vault_forgejo_api_token_piclaw: "SuperSecretForgejoApiTokenForPiclaw"
vault_github_api_token_piclaw: "SuperSecretGitHubTokenForPiclaw"

# PiClaw API State Token
vault_piclaw_api_token: "SuperSecretPiclawApiToken"

# SillyTavern Authentication
vault_sillytavern_user: "admin"
vault_sillytavern_password: "SuperSecretSillyTavernPassword"
vault_sillytavern_api_key: ""

# Glances Authentication
vault_glances_username: "glances"
vault_glances_password: "SuperSecretGlancesPassword"

# Uptrace Observability
vault_uptrace_admin_email: "admin@homelab.local"
vault_uptrace_admin_password: "SuperSecretUptraceAdminPassword"
# vault_uptrace_project_token: "SuperSecretUptraceProjectToken" (optional; auto-generated if omitted)
```

### Ansible Vault Utility Commands

- **Create a new encrypted vault file:**
  ```bash
  ansible-vault create inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **Edit an existing encrypted vault file:**
  ```bash
  ansible-vault edit inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **View encrypted contents without editing:**
  ```bash
  ansible-vault view inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **Encrypt an existing unencrypted file:**
  ```bash
  ansible-vault encrypt inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **Rekey (change password):**
  ```bash
  ansible-vault rekey inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
