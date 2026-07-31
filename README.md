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
| **KoboldCPP** | `ghcr.io/lostruins/koboldcpp` | `http://kobold.local` (internal: 5001) | LLM inference server with NVIDIA GPU acceleration | `inference_hosts` |
| **SillyTavern** | `ghcr.io/sillytavern/sillytavern` | `http://sillytavern.local` | AI chat & roleplay interface | `service_hosts` |
| **PiClaw** | `ghcr.io/rcarmo/piclaw` | `http://piclaw.local` | Isolated coding agent workspace | `service_hosts` |
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

---

## Model Tuning Notes

Detailed configuration guidelines and sampling recommendations for AI models are available in the [docs/models/](docs/models/) directory:
- [Gemma 4 Setting Notes](docs/models/gemma%20setting%20notes.md)
- [Qwen Setting Notes](docs/models/qwen%20setting%20notes.md)

---

## Future Roadmap

- **Remote SSH Deployment**: Tracked in [#5](https://github.com/Darkkal/homelab/issues/5) — SSH key authentication and remote target provisioning.
- **Ansible Vault Secrets**: Implemented in [#6](https://github.com/Darkkal/homelab/issues/6) — Vault encrypted variables and Quadlet integration.
