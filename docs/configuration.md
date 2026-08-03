# Configuration Reference

This document provides a detailed reference for all configuration variables across Ansible group variable files, role defaults, and Ansible Vault secrets.

---

## Inventory & Group Variables

Customizing deployment options is done by editing files under `inventory/group_vars/`.

### Shared Configuration (`inventory/group_vars/all.yml`)

These settings apply to all target hosts across all host groups:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `homelab_data_dir` | `~/homelab` | Base directory path on target machines for persistent application data storage. |
| `quadlet_dir` | `~/.config/containers/systemd` | Directory path where user systemd Podman Quadlet container files are deployed. |
| `network_name` | `homelab.network` | Shared Podman bridge network name connecting container instances. |

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





---

### Service Host Configuration (`inventory/group_vars/service_hosts.yml`)

These settings apply to target hosts in the `service_hosts` group:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `avahi_aliases` | List of `.local` hostnames | Hostnames published via LAN mDNS (`sillytavern.local`, `forgejo.local`, `llamaswap.local`, `openwebui.local`, `hermes.local`, `swarmui.local`, `wan2gp.local`). |
| `forgejo_port` | `3003` | Host web port for direct Forgejo access. |
| `hermes_data_dir` | `~/homelab/hermes` | Directory for Hermes Agent persistent data. |
| `hermes_port` | `8383` | Host web port for direct Hermes Agent access. |
| `hermes_openai_api_base_url` | `http://llama-swap:8080/v1` | OpenAI-compatible API endpoint for Hermes Agent backend calls. |
| `openwebui_data_dir` | `~/homelab/open-webui` | Directory for Open WebUI persistent data. |
| `openwebui_port` | `8081` | Host web port for direct Open WebUI access. |
| `openwebui_openai_api_base_url` | `http://llama-swap:8080/v1` | OpenAI-compatible API endpoint for Open WebUI backend calls. |
| `st_data_dir` | `~/homelab/sillytavern` | Directory for SillyTavern persistent data. |
| `sillytavern_openai_api_base_url` | `http://llama-swap:8080/v1` | OpenAI-compatible API endpoint for SillyTavern LLM backend calls. |

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
| `forgejo_upstream` | `forgejo:3000` | `forgejo.local` |
| `llama_swap_upstream` | `llama-swap:8080` | `llamaswap.local` |
| `openwebui_upstream` | `open-webui:8080` | `openwebui.local` |
| `hermes_upstream` | `hermes-agent:8080` | `hermes.local` |
| `swarmui_upstream` | `swarmui:7801` | `swarmui.local` |

| `wan2gp_upstream` | `wan2gp:7860` | `wan2gp.local` |

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
| `vault_sillytavern_user` | HTTP basic auth username for SillyTavern | `admin` |
| `vault_sillytavern_password` | HTTP basic auth password for SillyTavern | `""` (no basic auth password) |
| `vault_sillytavern_api_key` | SillyTavern API access key | `""` |
| `vault_hermes_admin_user` | Basic auth username for Hermes Agent | `admin` |
| `vault_hermes_admin_password` | Basic auth password for Hermes Agent | `admin` |

### `vault.yml` File Template

Unencrypted template structure before executing `ansible-vault encrypt`:

```yaml
---
# Forgejo Initial Credentials
vault_forgejo_admin_user: "admin"
vault_forgejo_admin_password: "SuperSecretForgejoPassword"
vault_forgejo_admin_email: "admin@homelab.local"

# SillyTavern Authentication
vault_sillytavern_user: "admin"
vault_sillytavern_password: "SuperSecretSillyTavernPassword"
vault_sillytavern_api_key: ""

# Hermes Agent Authentication
vault_hermes_admin_user: "admin"
vault_hermes_admin_password: "SuperSecretHermesPassword"
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
