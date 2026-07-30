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
│       │   └── vault.yml        # Ansible Vault placeholder for secrets
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

### 1. Dry Run (Preview Changes)

To check playbook syntax and preview changes without modifying the system:

```bash
# Syntax check
ansible-playbook playbooks/site.yml --syntax-check

# Dry run / diff mode
ansible-playbook playbooks/site.yml --check --diff
```

### 2. Deploy Infrastructure

Run the site playbook to configure all roles:

```bash
ansible-playbook playbooks/site.yml --ask-become-pass
```

> **Note:** `--ask-become-pass` (or `-K`) is required for root-level tasks (setting unprivileged port 80 in sysctl, enabling user lingering, installing system packages, and creating systemd system units).

### 3. Verify Deployed Services

Check status of user-level Podman Quadlet services:

```bash
systemctl --user status caddy sillytavern piclaw koboldcpp forgejo
```

Check mDNS address resolution:

```bash
avahi-resolve -n sillytavern.local
```

---

## Configuration Reference

Key variables can be customized in `inventory/group_vars/`:

### `inventory/group_vars/all.yml`
- `homelab_data_dir`: Base path for persistent service data (`~/homelab`)
- `quadlet_dir`: Path for user systemd Quadlets (`~/.config/containers/systemd`)
- `network_name`: Shared container bridge network (`homelab.network`)

### `inventory/group_vars/inference_hosts.yml`
- `default_model`: Default model file inside `~/homelab/models`
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
- **Ansible Vault Secrets**: Tracked in [#6](https://github.com/Darkkal/homelab/issues/6) — Encrypted secret variables for API keys and service passwords.
