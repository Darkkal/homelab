# Configuration Reference

This document provides a detailed reference for all configuration variables across Ansible group variable files, role defaults, and Ansible Vault secrets.

---

## LAN hostname suffix

`lan_domain: home` is defined once in `inventory/group_vars/all/vars.yml`.
Use a bare lowercase DNS suffix, without a leading/trailing dot, URL scheme,
port or wildcard. Multi-label values such as `lab.test` are supported. DNS
labels must contain 1–63 letters/digits/hyphens, start and end with a letter or
digit, and the suffix must contain a letter and be at most 253 characters.
The base role rejects malformed values before configuration writes.

Normal Ansible inventory precedence applies; a group/host override or `-e`
can override the default. This is one deployment-wide namespace: configure the
same value for service and inference hosts. Independent per-host namespaces
are not supported by the shared routing/DNS design. No play variable masks
inventory overrides.

Generated Caddy names, application defaults, Homepage links/search/rewrite map,
AdGuard wildcard and telemetry LAN names follow the suffix. Explicit settings
such as `forgejo_root_url` and `homepage_allowed_hosts_extra` retain operator
values. Protected application dictionaries, OAuth/webhook configuration, stored
user data and runner host-binding/allow-list policy are separate operator-owned
settings and are not rewritten. Container DNS, public domains and account email
addresses such as `admin@homelab.local` are independent of the LAN suffix.

The `.home` URLs in this documentation are examples of the default deployment;
historical issue links and Avahi retirement fixtures intentionally retain their
original names. New generated LAN endpoints must use `lan_domain`.

This refactor performs no live rename. Before deploying a different suffix,
inventory protected overrides and client dependencies, check the actual provider
version and separately approve cutover and reachable rollback. AdGuard retains
its first-exact-wildcard reconciliation: a new suffix manages a new wildcard
without deleting the old suffix or cleaning duplicates. A changed answer is
still deleted before it is added; this is not an atomic DNS cutover. Source
reversion alone cannot restore externally stored DNS/application state.

A thin controller-only render fixture uses the actual templates and non-secret
variable files, with explicit dummy paths/secrets. It loads no Vault and runs no
service roles, handlers or API calls. Use an empty temporary inventory and config
so production inventory, automatic group variables and callbacks are not loaded:

```bash
validation_work=$(mktemp -d /tmp/lan-domain.XXXXXX)
printf '[defaults]\nretry_files_enabled=False\n' > "$validation_work/ansible.cfg"
export ANSIBLE_CONFIG="$validation_work/ansible.cfg"
export ANSIBLE_LOCAL_TEMP="$validation_work/local"
export ANSIBLE_REMOTE_TEMP="$validation_work/remote"
ansible-playbook -i localhost, tests/validation/lan_domain.yml -e "validation_output_dir=$validation_work/home"
ansible-playbook -i localhost, tests/validation/lan_domain.yml -e "validation_output_dir=$validation_work/lab.test" -e lan_domain=lab.test
ansible-playbook -i localhost, tests/validation/lan_domain.yml -e "validation_output_dir=$validation_work/override" -e lan_domain=lab.test -e forgejo_root_url=https://git.example.org/custom/
ansible-playbook -i localhost, tests/validation/lan_domain.yml -e "validation_output_dir=$validation_work/home" --check --diff
```

The fixture checks suffix propagation, Forgejo URL overrides, and OTel Host/SNI
and Uptrace URL/DSN forms. Check/diff only predicts changes to these local rendered
files. This is a limited render context, not the full deployment or proof of
service/DNS idempotence. It does not discover/extract provisioning tasks, simulate
AdGuard guards, or retain whole-artifact fingerprints or a duplicate service map.

For a change to the suffix behavior, also record a one-time comparison of default
renders with the pre-change source, representative valid/invalid admission checks,
and a bounded Homepage LAN/direct-host URL check (including suffix boundaries and
path/query/fragment preservation). Validate generated YAML and JavaScript syntax;
where Caddy is available, validate both Caddyfiles natively with temporary
`XDG_DATA_HOME`/`XDG_CONFIG_HOME`. Record unavailable checks as not run.

Review AdGuard's source for the same derived wildcard in selection/delete/add and
unchanged guards. Production check mode skips its provisioning; rendering is not
proof of API reconciliation or live DNS idempotence. Repository-wide test tooling
and policy are separate follow-up work; this fixture does not choose a framework.

## Inventory & Group Variables

Customizing deployment options is done by editing files under `inventory/group_vars/` and host-specific overrides under `inventory/host_vars/<host>/`.

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

Application container data normally lives under subdirectories of `homelab_data_dir` (`~/homelab/<service>`). Web Gallery retains its existing data and media locations through explicit host-path variables; see [Web Gallery](#web-gallery).

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
| `forgejo_port` | `3003` | Host web port for direct Forgejo access. |
| `forgejo_image` | `codeberg.org/forgejo/forgejo:16` | Forgejo container image. Tracks the latest major (auto-updated via the `registry` label). Bumped off the old `:10` pin for the LFS upload quota nil-pointer fix (v10/v12 crash on LFS batch uploads when `ctx.Doer` is nil). Forgejo publishes no `:latest` tag, so `:16` is the newest major. |
| `forgejo_root_url` | `https://forgejo.home/` | Forgejo `ROOT_URL` (`[server] ROOT_URL`). Must match the primary site URL so generated links (web UI, mail, webhooks, OAuth2) are correct and the admin-page mismatch warning is not shown. |
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
| `homepage_allowed_hosts_extra` | `[]` | Extra `host:port` entries appended to `HOMEPAGE_ALLOWED_HOSTS` (in addition to `homepage.home`, the host's default LAN IPv4 address, and loopback), e.g. `['desktop.home:3002']`. |
| `glances_data_dir` | `~/homelab/glances` | Directory for the Glances password file and runtime data. |
| `glances_port` | `61208` | Host web port for direct Glances access (container internal port `61208`). |
| `glances_username` | `glances` | Glances web server basic auth username (from `vault_glances_username`). |
| `glances_password` | `""` | Glances web server basic auth password (from `vault_glances_password`). When empty, Glances runs without authentication. |
| `searxng_data_dir` | `~/homelab/searxng` | Directory for SearXNG settings and configuration. |
| `searxng_port` | `8082` | Host web port for direct SearXNG search interface access (container internal port `8080`). |
| `playwright_port` | `3004` | Host web port for direct Playwright browser scraping service access (container internal port `3000`). |
| `piclaw_data_dir` | `~/homelab/piclaw` | Directory for PiClaw persistent configuration and workspace files. |
| `piclaw_port` | `8083` | Host web port for direct PiClaw AI workspace access (container internal port `8080`). |
| `webgallery_port` | `8084` | Host port for direct Web Gallery HTTP access (container internal port `3000`). |
| `uptrace_data_dir` | `~/homelab/uptrace` | Directory for Uptrace config, ClickHouse (`uptrace/ch`), PostgreSQL (`uptrace/pg`), and the ClickHouse Prometheus drop-in (`uptrace/ch-config`). |
| `uptrace_port` | `14318` | Host web port for direct Uptrace UI access (container internal port `80`). |
| `uptrace_image` | `docker.io/uptrace/uptrace:2.0.3` | Uptrace container image. Pinned to a stable release; Uptrace only supports next-minor upgrades, so `uptrace_autoupdate` defaults to `disabled`. |
| `uptrace_clickhouse_image` | `docker.io/clickhouse/clickhouse-server:26.3` | ClickHouse telemetry store image. |
| `uptrace_clickhouse_http_port` | `8123` | Host **loopback-only** (`127.0.0.1`) HTTP port exposing ClickHouse to local tooling for **read-only** querying of Uptrace telemetry. Consumed by the local MCP ClickHouse server (`mcp-clickhouse`) that the agent runs on the host. Bound to loopback only and read-only by design (see the rationale in [`docs/architecture.md`](architecture.md)). |
| `uptrace_postgres_image` | `docker.io/library/postgres:17-alpine` | Uptrace PostgreSQL metadata store image. |
| `uptrace_redis_image` | `docker.io/library/redis:6.2.2-alpine` | Uptrace Redis cache image. |
| `uptrace_otelcol_image` | `docker.io/otel/opentelemetry-collector-contrib:0.123.0` | OpenTelemetry Collector image handling host metrics, synthetic checks, and Prometheus scraping. |
| `enable_uptrace_dashboards` | `true` | Provision Uptrace dashboards and metric monitors (from `roles/quadlets/files/dashboards/*.yml`) via the Uptrace internal HTTP API on each playbook run. |
| `uptrace_project_id` | `1` | Uptrace project ID (the first seeded project, `Homelab`) used by the dashboard/monitor provisioning API. |
| `uptrace_admin_email` | `admin@homelab.local` | Initial Uptrace admin login email (from `vault_uptrace_admin_email`). |
| `uptrace_admin_password` | `""` | Initial Uptrace admin login password (from `vault_uptrace_admin_password`). |
| `uptrace_project_token` | auto-generated (`~/homelab/.uptrace_project_token`) | Write-only OTLP project token used in DSNs and collector ingestion. |
| `uptrace_secret` | auto-generated (`~/homelab/.uptrace_secret`) | Uptrace `service.secret` for cryptographic operations. |
| `uptrace_pg_password` | auto-generated (`~/homelab/.uptrace_pg_password`) | Uptrace PostgreSQL password. |
| `uptrace_ch_password` | auto-generated (`~/homelab/.uptrace_ch_password`) | Uptrace ClickHouse password. |
| `uptrace_retention_traces` | `7 DAY` | ClickHouse TTL for trace data. |
| `uptrace_retention_metrics` | `30 DAY` | ClickHouse TTL for metric data. |
| `uptrace_retention_logs` | `7 DAY` | ClickHouse TTL for log data. |
| `adguardhome_data_dir` | `~/homelab/adguardhome` | Directory for AdGuard Home config (`conf`) and runtime state (`work`). |
| `adguardhome_port` | `8090` | Host web port for the AdGuard Home admin UI (container internal port `3000`). |
| `adguardhome_upstream_dns` | `["1.1.1.1", "8.8.8.8"]` | Upstream DNS servers AdGuard Home forwards public queries to. |
| `adguardhome_username` | `admin` | AdGuard Home admin UI username (from `vault_adguard_username`). |
| `adguardhome_password` | auto-generated (`~/homelab/.adguardhome_password`) | AdGuard Home admin UI password (from `vault_adguard_password`). The playbook seeds it on first install via AdGuard's `install/configure` API. |

#### Web Gallery

Web Gallery runs as `webgallery.service` on `service_hosts`, available at
`https://webgallery.home` through Caddy or `http://<host-ip>:8084` directly.
The service is included in the normal site deployment list. Its GHCR `latest`
tag follows published releases, rather than every source commit. The shared
Podman auto-update timer checks for a new image on the configured schedule
(default Tuesday at 04:00 host local time), pulls it and restarts the service
when its digest changes. Applying a changed image reference also recreates the
service through the normal Quadlet deployment tasks.

Define the required host-specific values in
`inventory/host_vars/<host>/webgallery.yml` (`desktop` for the default inventory).
This file is gitignored; keep it mode `0600` and back it up separately. A fresh
clone does not include the local paths or desired configuration.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `webgallery_image` | `ghcr.io/darkkal/web-gallery:latest` | GitHub mirror release image. Override to select another release tag or registry. |
| `webgallery_autoupdate` | `registry` | Podman checks the selected registry tag through the shared auto-update timer. Set to `disabled` to stop automatic updates for this service. |
| `webgallery_data_dir` | Required | Absolute path to the existing database/configuration directory, previously supplied through Compose's `WEBGALLERY_DATA_DIR`. Mounted at `/data`. |
| `webgallery_media_dir` | Required | Absolute path to the existing media directory, previously supplied through `WEBGALLERY_MEDIA_DIR`. Mounted at `/media`. |
| `webgallery_browser_dir` | Required | Existing Firefox-profile directory, mounted read-only at `/home/node/.mozilla/firefox` without SELinux relabeling. |
| `webgallery_settings` | Required | Complete desired mapping for `/data/settings.json`, including the `app` and `scraper` groups. |
| `webgallery_gallery_dl_config` | Required | Complete desired mapping for `/data/scrapers/gallery-dl/gallery-dl.conf`, including the `extractor` mapping. |
| `webgallery_extractor_credentials` | Pixiv refresh token from Vault | Mapping of extractor names to credential options, applied to the declared gallery-dl configuration before rendering the complete file. |
| `webgallery_uid` / `webgallery_gid` | `1000` / `1000` | Container user/group IDs, used with `UserNS=keep-id`. |
| `webgallery_timezone` | `UTC` | Container `TZ` setting; host `/etc/localtime` is also mounted read-only. |

Use the existing directory roots rather than a database filename or the nested
downloads folder:

| Host path | Container path | Contents |
| :--- | :--- | :--- |
| `{{ webgallery_data_dir }}/sqlite.db` | `/data/sqlite.db` | Existing SQLite database |
| `{{ webgallery_data_dir }}/settings.json` | `/data/settings.json` | Ansible-managed application and scraper settings |
| `{{ webgallery_data_dir }}/scrapers/gallery-dl/gallery-dl.conf` | `/data/scrapers/gallery-dl/gallery-dl.conf` | Ansible-managed gallery-dl configuration |
| `{{ webgallery_data_dir }}/scrapers/gallery-dl/` | `/data/scrapers/gallery-dl/` | Scraper archives and logs alongside configuration |
| `{{ webgallery_media_dir }}/downloads/` | `/media/downloads/` | Downloaded media |
| `{{ webgallery_media_dir }}/avatars/` | `/media/avatars/` | Cached avatars |

Ansible replaces both complete JSON configuration files on apply, using mode
`0600` and the deploying user's ownership. Settings edited through the application
UI must also be reflected in the desired inventory mappings to survive the next
apply. Database, downloaded media, browser cookies and scraper archives remain
application-owned state.

Add `vault_webgallery_pixiv_refresh_token` to the encrypted Vault before deploying;
it is required and has no empty fallback. The default credential mapping is:

```yaml
webgallery_extractor_credentials:
  pixiv:
    refresh-token: "{{ vault_webgallery_pixiv_refresh_token }}"
```

Add future extractor credentials as entries in that mapping referencing their
own Vault keys. Browser cookies stay in the existing read-only profile mount.
For a missing-token error, use `ansible-vault edit` as described under
[Vault utility commands](#ansible-vault-utility-commands) and define the required
key before rerunning the playbook.

#### Adding New Services to the Homepage Dashboard

To register a new containerized service on the Homepage dashboard:

1. **Add Discovery Labels in Quadlet Template (`<service>.container.j2`)**:
   Add standard `homepage.*` labels to the `[Container]` block of your Jinja2 template:
   ```ini
   Label=homepage.group="Web Services"
   Label=homepage.name="SearXNG"
   Label=homepage.icon=searxng.png
   Label=homepage.href=https://searxng.{{ lan_domain }}
   Label=homepage.description="Self-hosted search aggregator"
   ```

2. **Select or Create a Dashboard Group**:
   - Assign `homepage.group` to an existing layout group: `Inference`, `Web Services`, or `Infrastructure`.
   - If creating a new group, add a matching entry under `layout:` in `roles/quadlets/templates/homepage.settings.yaml.j2`.

3. **Configure DNS Hostnames & Reverse Proxy**:
   - Add the `.home` hostname to the Caddy route (served by AdGuard Home DNS's wildcard `*.home` rewrite and routed by Caddy).
   - Add default upstream in `roles/caddy/defaults/main.yml` and routing block in `roles/caddy/templates/Caddyfile.j2`.

4. **Adhere to Quadlet Quoting Rules**:
   - Double-quote multi-word label strings: `Label=homepage.group="Web Services"`
   - Single-quote JSON arrays: `Label=homepage.widget.fields='["upstreams","requests"]'`

#### AdGuard Home (LAN DNS & Ad Blocker)

AdGuard Home runs as a rootless Quadlet service on `service_hosts` on the **host network** (`Network=host`), binding DNS directly to the host's LAN IP on port `53` (TCP+UDP) and serving its admin UI directly on host port `adguardhome_port` (default `8090`). Running on the host network (rather than a port-published container) avoids a port-53 conflict with aardvark-dns on the podman bridge gateway; the admin UI is therefore accessed directly at `http://<host-ip>:8090`, not through Caddy.

- **Provisioning**: The playbook performs the first-run setup via the AdGuard Home HTTP API (`roles/quadlets/tasks/adguardhome-provision.yml`), mirroring the Uptrace dashboard pattern and running only outside `--check` mode:
  1. `POST /control/install/configure` — creates the admin user (username/password from `adguardhome_username` / `adguardhome_password`) and binds web (`0.0.0.0:3000`) and DNS (`0.0.0.0:53`). Returns `403` once configured, so re-runs are a no-op.
  2. `POST /control/dns_config` — sets `adguardhome_upstream_dns` and enables protection/filtering.
  3. `POST /control/rewrite/*` — reconciles a wildcard `*.home → ansible_default_ipv4.address` rewrite against the live list (added if missing, re-pointed if the host IP changed).
- **`.home` resolution**: AdGuard Home answers every `*.home` hostname with the host's LAN IP to any device pointed at `<host-ip>` (port `53`) — Linux, macOS, Windows, and Android alike. We use `.home` because `.local` (RFC 6762) is reserved for mDNS and Android will not query a DNS server for `.local` names.
- **Port 53 binding**: AdGuard's DNS is published only on the host's LAN IP (`ansible_default_ipv4.address:53`), not `0.0.0.0`. Binding all host interfaces would collide with the podman network's aardvark-dns on the bridge gateway (`10.89.9.1:53`), which resolves container names for the rest of the homelab network.
- **Credentials**: `vault_adguard_username` / `vault_adguard_password` are optional; when omitted the password is auto-generated into `~/homelab/.adguardhome_password` (read it to log into the admin UI). If the admin password is changed in the AdGuard UI, subsequent provisioning runs will fail authentication on the rewrite/upstream calls — keep it in sync with the vault value.
- **Data**: config lives in `adguardhome_data_dir/conf` (`AdGuardHome.yaml`) and runtime state in `adguardhome_data_dir/work`. AdGuard Home owns `AdGuardHome.yaml` after first boot (it migrates the schema and persists UI edits), so the repo does not template it after initial provisioning.
- **Verification**: `dig @<host-ip> homepage.home` returns the host IP; `dig @<host-ip> example.com` returns a public answer via Quad9.

#### Glances Runtime Configuration

Glances runs as a rootless Podman Quadlet on `service_hosts` and exposes its REST API to the Homepage Glances info widget over the shared `homelab.network`.

- **Web server mode**: `GLANCES_OPT=-w` enables the FastAPI web server/REST API on container port `61208` (published to `glances_port` on the host and proxied by Caddy at `glances.home`).
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

## Forgejo Actions Runner Configuration

The runner is deployed by the `forgejo_runner_hosts` inventory group. In the
single-machine inventory this group contains `desktop`, but the runner uses a
separate `forgejo-runner` Unix account and rootless Podman socket so it cannot
manage the existing service user's containers.

The runner daemon uses the pinned `data.forgejo.org/forgejo/runner` image. Jobs
are launched as ephemeral containers through that account's rootless Podman
socket. The default `ubuntu-latest` label uses the pinned Node/bookworm image,
which provides the common Actions toolchain needed by the Godot and Next.js
repositories. Add a separate label and job image when a workflow needs a
specialized SDK; do not add SDKs to the daemon image.

Before the first deployment, create a runner in Forgejo's Actions runner UI
and add its UUID and token to the encrypted vault:

```yaml
vault_forgejo_runner_uuid: "<runner-uuid>"
vault_forgejo_runner_token: "<runner-token>"
```

The role uses the UUID and token directly in the runner configuration's
`server.connections` section, so re-running the playbook does not create
duplicate runners.

---

## Role Defaults & Upstreams

### Caddy Reverse Proxy Defaults (`roles/caddy/defaults/main.yml`)

Caddy upstream variables define where requests to `*.home` hostnames are routed. In single-machine setups, these default to container names on the `homelab.network` bridge network. For multi-host setups, these can be overridden in `inventory/group_vars/service_hosts.yml` with physical IP addresses or hostnames.

All `.home` sites are served over **automatic HTTPS** using Caddy's internal Certificate Authority. The `roles/caddy/templates/Caddyfile.j2` template declares sites with **bare hostnames** (no scheme), which activates automatic HTTPS: Caddy serves TLS on port `443` with internal-CA-signed certificates for `*.home` names and redirects HTTP on port `80` to HTTPS. The generated CA root certificate is persisted under `~/homelab/caddy/data/caddy/pki/authorities/local/root.crt` and must be trusted on every LAN client (see the [README](README.md#trusting-caddys-local-ca)).

| Variable | Default Upstream Target | Proxied Hostname |
| :--- | :--- | :--- |
| `sillytavern_upstream` | `sillytavern:8000` | `sillytavern.home` |
| `forgejo_upstream` | `forgejo:3003` | `forgejo.home` |
| `llama_swap_upstream` | `llama-swap:8080` | `llamaswap.home` |
| `openwebui_upstream` | `open-webui:8081` | `openwebui.home` |
| `swarmui_upstream` | `swarmui:7801` | `swarmui.home` |
| `homepage_upstream` | `homepage:3000` | `homepage.home` |
| `glances_upstream` | `glances:61208` | `glances.home` |
| `piclaw_upstream` | `piclaw:8080` | `piclaw.home` |
| `webgallery_upstream` | `webgallery:3000` | `webgallery.home` |
| `uptrace_upstream` | `uptrace:80` | `uptrace.home` |

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
| `vault_sillytavern_api_key` | SillyTavern API access key | `""` |
| `vault_forgejo_api_token_planner` | Forgejo API token for the PiClaw planner account (`piclaw`); injected as `FORGEJO_TOKEN` / `FORGEJO_PLANNER_TOKEN` | `""` |
| `vault_forgejo_api_token_piclaw_worker` | Forgejo API token for the `piclaw-worker` dispatcher account (`FORGEJO_WORKER_TOKEN`) | `""` |
| `vault_forgejo_api_token_piclaw_reviewer` | Forgejo API token for the `piclaw-reviewer` dispatcher account (`FORGEJO_REVIEWER_TOKEN`) | `""` |
| `vault_forgejo_runner_uuid` | Forgejo Actions runner UUID created in the runner UI | required for runner deployment |
| `vault_forgejo_runner_token` | Forgejo Actions runner connection token created in the runner UI | required for runner deployment |
| `vault_github_api_token_piclaw` | GitHub Personal Access Token for PiClaw container (`GH_TOKEN` / `GITHUB_TOKEN`) | `""` |
| `vault_piclaw_api_token` | Bearer token API key for PiClaw state APIs (`/api/state`, `/api/state/events`) | Auto-generated unique 64-char hex secret (`~/homelab/.piclaw_api_token`) |
| `vault_webgallery_pixiv_refresh_token` | Pixiv extractor refresh token for Web Gallery | Required; deployment fails if undefined or empty |
| `vault_glances_username` | Basic auth username for the Glances web server | `glances` |
| `vault_glances_password` | Basic auth password for the Glances web server | `""` (no auth) |
| `vault_uptrace_admin_email` | Initial Uptrace admin login email (seeded via `seed_data`) | `admin@homelab.local` |
| `vault_uptrace_admin_password` | Initial Uptrace admin login password (seeded via `seed_data`) | `""` |
| `vault_uptrace_project_token` | Uptrace project token used in OTLP DSNs and collector ingestion | Auto-generated (`~/homelab/.uptrace_project_token`) |
| `vault_adguard_username` | AdGuard Home admin UI username | `admin` |
| `vault_adguard_password` | AdGuard Home admin UI password (seeded via the install API on first run) | Auto-generated (`~/homelab/.adguardhome_password`) |

### `vault.yml` File Template

Unencrypted template structure before executing `ansible-vault encrypt`:

```yaml
---
# Forgejo Initial Credentials & Dashboard Tokens
vault_forgejo_admin_user: "admin"
vault_forgejo_admin_password: "SuperSecretForgejoPassword"
vault_forgejo_admin_email: "admin@homelab.local"
vault_forgejo_api_token_homepage: "SuperSecretForgejoApiTokenForHomepage"
vault_forgejo_api_token_planner: "SuperSecretForgejoApiTokenForPiclaw"
vault_forgejo_api_token_piclaw_worker: "SuperSecretForgejoApiTokenForPiclawWorker"
vault_forgejo_api_token_piclaw_reviewer: "SuperSecretForgejoApiTokenForPiclawReviewer"
vault_forgejo_runner_uuid: "ForgejoRunnerUUID"
vault_forgejo_runner_token: "ForgejoRunnerConnectionToken"
vault_github_api_token_piclaw: "SuperSecretGitHubTokenForPiclaw"

# PiClaw API State Token
vault_piclaw_api_token: "SuperSecretPiclawApiToken"

# SillyTavern API Key
vault_sillytavern_api_key: ""

# Web Gallery Pixiv extractor (required)
vault_webgallery_pixiv_refresh_token: "<existing-pixiv-refresh-token>"

# Glances Authentication
vault_glances_username: "glances"
vault_glances_password: "SuperSecretGlancesPassword"

# Uptrace Observability
vault_uptrace_admin_email: "admin@homelab.local"
vault_uptrace_admin_password: "SuperSecretUptraceAdminPassword"
# vault_uptrace_project_token: "SuperSecretUptraceProjectToken" (optional; auto-generated if omitted)

# AdGuard Home (optional; password auto-generated if omitted)
vault_adguard_username: "admin"
vault_adguard_password: "SuperSecretAdguardPassword"
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
