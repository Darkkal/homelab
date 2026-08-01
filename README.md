# Homelab Infrastructure

An automated, declarative homelab infrastructure managed with **Ansible** and **Podman Quadlets** integrated into `systemd`.

---

## Overview

This repository automates the deployment and configuration of self-hosted homelab services. Services run as rootless Podman containers defined via Podman Quadlet systemd unit files, orchestrated centrally through Ansible playbooks.

Services are accessible on your local network via mDNS aliases (`*.local`) routed through a Caddy reverse proxy.

---

## Services

| Service | Image | Ports / Routing | Description | Group |
| :--- | :--- | :--- | :--- | :--- |
| **llama-swap** | `ghcr.io/llama-swap/llama-swap` | `http://llama-swap.local` (internal: 8080) | Model swap proxy & inference controller | `inference_hosts` |
| **SillyTavern** | `ghcr.io/sillytavern/sillytavern` | `http://sillytavern.local` | AI chat & roleplay interface | `service_hosts` |
| **Open WebUI** | `ghcr.io/open-webui/open-webui` | `http://openwebui.local` (internal: 8081) | Open WebUI chat & LLM interface | `service_hosts` |
| **Hermes Agent** | `hermes` | `http://hermes.local` (internal: 8383) | Hermes agent service | `service_hosts` |
| **SwarmUI** | `swarmui` | `http://swarmui.local` (internal: 7821) | Generative image creation UI | `inference_hosts` |
| **Wan2GP** | `wan2gp` | `http://wan2gp.local` (internal: 7860) | Video generation server | `inference_hosts` |
| **Caddy** | `docker.io/library/caddy` | `80:80` | Reverse proxy for `.local` domain resolution | `service_hosts` |
| **Forgejo** | `codeberg.org/forgejo/forgejo:10` | `3000:3000`, `222:22` | Self-hosted Git hosting & CI/CD platform | `service_hosts` |
| **Avahi Aliases** | Host native (`avahi-tools`) | mDNS (`*.local`) | Publishes LAN mDNS aliases for local service resolution | `service_hosts` |

---

## Architecture & Host Groups

The inventory divides target machines into two main functional groups:

- **`inference_hosts`**: Machines equipped with dedicated GPUs for AI model inference (runs `koboldcpp` and configures the NVIDIA Container Toolkit).
- **`service_hosts`**: Machines running application containers, proxies, and mDNS services (`caddy`, `sillytavern`, `piclaw`, `forgejo`, `avahi`).

Currently, single-machine setups run both groups on `desktop` (via local Ansible connection). In the future, non-inference services can be migrated to a remote target machine simply by adding a new host under `service_hosts` in `inventory/hosts.yml`.

---

## Repository Structure

```
homelab/
├── ansible.cfg                  # Ansible configuration
├── inventory/
│   ├── hosts.yml                # Host definitions and group mappings
│   └── group_vars/
│       ├── all.yml              # Shared paths and system configuration
│       ├── all/
│       │   └── vault.yml        # Ansible Vault encrypted secrets
│       ├── inference_hosts.yml  # KoboldCPP & GPU inference settings
│       └── service_hosts.yml    # Service ports and mDNS alias list
├── playbooks/
│   └── site.yml                 # Main deployment playbook
├── roles/
│   ├── base/                    # Core setup: directories, sysctl port 80, lingering, Quadlet network/volume
│   ├── nvidia/                  # NVIDIA container toolkit repo & CDI spec generation
│   ├── quadlets/                # Jinja2 container templates & systemd user service management
│   ├── avahi/                   # Avahi package, systemd template unit, & mDNS alias publishing
│   └── caddy/                   # Caddyfile deployment
├── docs/
│   └── models/                  # Model inference configuration notes (Gemma, Qwen)
└── README.md
```

---

## Prerequisites

On the **Ansible Control Node** (your desktop/workstation):
- Python 3.10+
- Ansible (`pip install ansible`)

On the **Target Machine**:
- Linux distribution (Fedora / RHEL recommended)
- Podman with Quadlet support (`systemd >= 252`)
- NVIDIA GPU drivers installed (for `inference_hosts`)

---

## Quick Start

### 1. Secret Vault Preparation

Create a local `.vault-pass` file containing your vault password (ignored by `.gitignore`):

```bash
echo "your-secure-vault-password" > .vault-pass
```

### 2. Dry Run (Preview Changes)

To check playbook syntax and preview changes without modifying the system:

```bash
# Syntax check
ansible-playbook playbooks/site.yml --syntax-check --vault-password-file .vault-pass

# Dry run / diff mode
ansible-playbook playbooks/site.yml --check --diff --vault-password-file .vault-pass
```

### 3. Deploy Infrastructure

Run the site playbook to configure all roles:

```bash
ansible-playbook playbooks/site.yml --ask-become-pass --vault-password-file .vault-pass
```

> **Note:** `--ask-become-pass` (or `-K`) is required for root-level tasks (setting unprivileged port 80 in sysctl, enabling user lingering, installing system packages, and creating systemd system units). If no local `.vault-pass` file exists, use `--ask-vault-pass` instead.

### 4. Verify Deployed Services

Check status of user-level Podman Quadlet services:

```bash
systemctl --user status caddy sillytavern piclaw koboldcpp forgejo
```

Check mDNS address resolution:

```bash
avahi-resolve -n sillytavern.local
```

---

## Accessing Deployed Services

Once the Ansible deployment completes successfully, services are accessible on your local network (LAN) using **mDNS Hostnames** (`*.local`) or **Direct Host IP / Ports**.

### Service Directory & Access Matrix

| Service | Primary Access URL | Direct Host / Port | Access Protocol | Description & Authentication Notes |
| :--- | :--- | :--- | :--- | :--- |
| **llama-swap** | `http://llama-swap.local` | `http://<host-ip>:80` | Web UI & Model API | Model swap proxy & inference controller. Proxied via Caddy. |
| **SillyTavern** | `http://sillytavern.local` | `http://<host-ip>:80` | Web UI (HTTP) | Web chat & roleplay UI. Proxied via Caddy. HTTP basic authentication enabled (`basicAuthUser`). |
| **Open WebUI** | `http://openwebui.local` | `http://<host-ip>:80` | Web UI (HTTP) | Open WebUI chat & LLM interface. Proxied via Caddy. |
| **Hermes Agent** | `http://hermes.local` | `http://<host-ip>:80` | Web UI / API | Hermes agent backend/UI service. Proxied via Caddy. |
| **SwarmUI** | `http://swarmui.local` | `http://<host-ip>:80` | Web UI (HTTP) | Generative image creation UI. Proxied via Caddy. |
| **Wan2GP** | `http://wan2gp.local` | `http://<host-ip>:80` | Web UI (HTTP) | Video generation server. Proxied via Caddy. |
| **Forgejo (Web)** | `http://forgejo.local` | `http://<host-ip>:3000` | Web UI & HTTP Git | Self-hosted Git repository hosting & CI/CD platform. Data stored in `~/homelab/forgejo`. Initial admin credentials set in `vault.yml`. |
| **Forgejo (SSH)** | `ssh://git@<host-ip>:222` | `ssh://git@localhost:222` | Git over SSH | Git clone and push operations over SSH using port `222` (e.g. `git clone ssh://git@<host-ip>:222/<user>/<repo>.git`). |
| **Caddy** | `http://<host-ip>:80` | `http://localhost:80` | HTTP Reverse Proxy | Reverse proxy listening on port 80, routing `.local` mDNS domain requests to container backends based on `Host` headers. |

---

### How Network Access Works

1. **mDNS Hostname Resolution (`*.local`)**:
   - The `avahi` role publishes `.local` mDNS aliases (`sillytavern.local`, `forgejo.local`, `llama-swap.local`, `openwebui.local`, `hermes.local`, `swarmui.local`, `wan2gp.local`) across your local network.
   - Any client device connected to the same LAN (Linux, macOS, Windows 10/11, iOS, Android) can resolve these hostnames directly to the host's LAN IP address without requiring a local DNS server.

2. **Reverse Proxy Routing (Caddy)**:
   - **Caddy** listens on host port `80` (configured via sysctl `net.ipv4.ip_unprivileged_port_start = 80`).
   - HTTP requests to `.local` domains are routed to configured upstream addresses (`*_upstream`). In single-host deployments, these default to container names on the shared Podman network (`homelab.network`), while in multi-host setups they can be overridden with host IPs.

3. **Direct Port Exposure**:
   - **Forgejo** binds directly to host ports `3000` (Web) and `222` (SSH), as well as being proxied at `http://forgejo.local`.

---

### Client Setup & Requirements

- **Linux Clients**: Ensure `avahi-daemon` or `systemd-resolved` with mDNS enabled is active.
- **macOS / iOS Clients**: mDNS (`Bonjour`) is enabled by default. Open any browser to `http://sillytavern.local`.
- **Windows Clients**: Windows 10 (1803+) and Windows 11 support mDNS out of the box. Ensure network profile is set to "Private".

---

### Fallback Access & Troubleshooting

If a client device cannot resolve `.local` mDNS hostnames:

1. **Static Host Overrides (`/etc/hosts` or `C:\Windows\System32\drivers\etc\hosts`)**:
   Add target host IP address and service hostnames:
   ```text
   192.168.1.100  sillytavern.local piclaw.local kobold.local forgejo.local
   ```

2. **Testing via HTTP Host Header**:
   Verify proxy routing from any terminal using `curl`:
   ```bash
   curl -H "Host: sillytavern.local" http://<host-ip>
   curl -H "Host: forgejo.local" http://<host-ip>
   ```

3. **Verifying mDNS Resolution**:
   ```bash
   avahi-resolve -n sillytavern.local
   # or
   ping sillytavern.local
   ```

---

## Secrets Management (Ansible Vault)

Sensitive values (admin credentials, API keys, authentication tokens) are encrypted at rest using `ansible-vault` in `inventory/group_vars/all/vault.yml`.

### Variable Naming Convention

All secret variables defined in `vault.yml` use the `vault_` prefix:
- `vault_forgejo_admin_user`
- `vault_forgejo_admin_password`
- `vault_forgejo_admin_email`
- `vault_kobold_api_key`
- `vault_sillytavern_api_key`
- `vault_piclaw_api_key`

Unencrypted variable abstractions in `inventory/group_vars/all.yml` reference these vault variables with safe default fallbacks:
```yaml
forgejo_admin_password: "{{ vault_forgejo_admin_password | default('') }}"
```

### Working with Vault Files

- **View encrypted contents:**
  ```bash
  ansible-vault view inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **Edit encrypted secrets:**
  ```bash
  ansible-vault edit inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
  ```
- **Change vault password:**
  ```bash
  ansible-vault rekey inventory/group_vars/all/vault.yml
  ```

---

## Configuration Reference

Key variables can be customized in `inventory/group_vars/`:

### `inventory/group_vars/all.yml`
- `homelab_data_dir`: Base path for persistent service data (`~/homelab`)
- `quadlet_dir`: Path for user systemd Quadlets (`~/.config/containers/systemd`)
- `network_name`: Shared container bridge network (`homelab.network`)

### `inventory/group_vars/inference_hosts.yml`
- `kobold_roleplay_model`: Primary model file for SillyTavern roleplay (`gemma-4-12b-it-Q4_K_M.gguf`)
- `kobold_roleplay_model_mmproj`: Multimodal vision adapter file (`gemma-4-12b-it-Q4_K_M-mmproj-BF16.gguf`)
- `kobold_use_mtp`: Enable Multi-Token Prediction (`true`)
- `gpu_layers`: Number of layers to offload to GPU (`99`)
- `context_size`: Context window size (`32768`)
- `auto_unload_seconds`: Inactivity timeout before model unloads (`600`)

### `inventory/group_vars/service_hosts.yml`
- `avahi_aliases`: List of `.local` hostnames to publish on the LAN

### `roles/caddy/defaults/main.yml`
- `*_upstream`: Upstream service addresses for Caddy reverse proxy routing (`sillytavern_upstream`, `forgejo_upstream`, `llama_swap_upstream`, `openwebui_upstream`, `hermes_upstream`, `swarmui_upstream`, `wan2gp_upstream`, `koboldcpp_upstream`). Defaults to container names on single-host, overrideable for multi-host cross-routing.

---

## Model Tuning Notes

Detailed configuration guidelines and sampling recommendations for AI models are available in the [docs/models/](docs/models/) directory:
- [Gemma 4 Setting Notes](docs/models/gemma%20setting%20notes.md)
- [Qwen Setting Notes](docs/models/qwen%20setting%20notes.md)

---

## Future Roadmap

- **Remote SSH Deployment**: Tracked in [#5](https://github.com/Darkkal/homelab/issues/5) — SSH key authentication and remote target provisioning.
- **Ansible Vault Secrets**: Implemented in [#6](https://github.com/Darkkal/homelab/issues/6) — Vault encrypted variables and Quadlet integration.
