# Homelab Infrastructure

An automated, declarative homelab infrastructure managed with **Ansible** and **Podman Quadlets** integrated into `systemd`.

---

## Overview

This repository automates the deployment and configuration of self-hosted homelab services. Services run as rootless Podman containers defined via Podman Quadlet systemd unit files, orchestrated centrally through Ansible playbooks.

Services are accessible on your local network (LAN) via mDNS hostnames (`*.local`) routed through a Caddy reverse proxy.

### Documentation Quick Links
- 📐 **[System Architecture & Structure](docs/architecture.md)**: Host groups (`inference_hosts`, `service_hosts`), network topology, and repository tree.
- ⚙️ **[Configuration Reference](docs/configuration.md)**: Ansible variables, Caddy upstreams, and Ansible Vault setup.
- 🤝 **[Contributing Guidelines](CONTRIBUTING.md)**: Conventions, commit standards, Quadlet guidelines, and verification rules.

---

## Quick Start Guide

Follow this step-by-step process to set up the minimum dependencies, configure secrets, and deploy the homelab infrastructure.

### Step 1: Install Prerequisites

Ensure the following software is installed before deploying:

#### On the **Ansible Control Node** (your workstation):
- Python 3.10+
- Ansible:
  ```bash
  pip install ansible
  ```

#### On the **Target Machine(s)**:
- Linux distribution (Fedora, RHEL, or AlmaLinux recommended)
- Podman with Quadlet support (`systemd >= 252`)
- NVIDIA GPU Drivers & Container Toolkit (only required for `inference_hosts`)

---

### Step 2: Clone Repository & Inventory Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Darkkal/homelab.git
   cd homelab
   ```

2. Review `inventory/hosts.yml` to ensure target machine IP addresses or connection parameters match your setup. By default, single-machine setups target `desktop` via Ansible's `local` connection.

---

### Step 3: Secret Vault Preparation

Create a `.vault-pass` password file in the repository root (ignored by `.gitignore`):

```bash
echo "your-secure-vault-password" > .vault-pass
chmod 600 .vault-pass
```

Next, create your encrypted secrets file at `inventory/group_vars/all/vault.yml`:

```bash
ansible-vault create inventory/group_vars/all/vault.yml --vault-password-file .vault-pass
```

*(See the [Configuration Reference](docs/configuration.md#secrets-management-ansible-vault) for recommended vault keys and safe defaults).*

---

### Step 4: Validate Playbook (Syntax & Dry Run)

Verify playbook syntax and dry-run changes without altering system state:

```bash
# Syntax check
ansible-playbook playbooks/site.yml --syntax-check --vault-password-file .vault-pass

# Dry run / diff mode
ansible-playbook playbooks/site.yml --check --diff --vault-password-file .vault-pass
```

---

### Step 5: Deploy Infrastructure

Run the main playbook to deploy container networks, Quadlet unit files, Avahi mDNS aliases, and Caddy reverse proxy:

```bash
ansible-playbook playbooks/site.yml --ask-become-pass --vault-password-file .vault-pass
```

> **Note:** `--ask-become-pass` (`-K`) is required for root tasks (setting unprivileged port 80 sysctl, system package installations, and enabling user lingering).

---

### Step 6: Verify Deployed Services

Check status of user-level Podman Quadlet services:

```bash
systemctl --user status caddy sillytavern open-webui hermes-agent llama-swap forgejo glances searxng playwright
```

Verify mDNS address resolution from your local workstation:

```bash
avahi-resolve -n sillytavern.local
```

---

## Services & Network Access Directory

Once deployed, all services are accessible across your LAN using **mDNS Hostnames** (`*.local`) or direct host ports.

| Service | Primary LAN URL | Direct Host / Port | Access Protocol | Description & Authentication | Ansible Group |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **llama-swap** | `http://llamaswap.local` | `http://<host-ip>:8080` | Web UI & API | Model swap proxy & inference controller. Proxied via Caddy. | `inference_hosts` |
| **SillyTavern** | `http://sillytavern.local` | `http://<host-ip>:8000` | Web UI (HTTP) | LLM chat & roleplay UI. Connects to `llama-swap:8080`. Basic auth enabled (`vault_sillytavern_user`). | `service_hosts` |
| **Open WebUI** | `http://openwebui.local` | `http://<host-ip>:8081` | Web UI (HTTP) | Open WebUI chat & LLM interface. Proxied via Caddy. | `service_hosts` |
| **Hermes Agent** | `http://hermes.local` | `http://<host-ip>:8383`<br>`http://<host-ip>:8642` | Web UI / API | Hermes agent service backend & UI (port 8383) and OpenAI-compatible API server (port 8642). Basic HTTP auth supported. | `service_hosts` |
| **SearXNG** | `http://searxng.local` | `http://<host-ip>:8082` | Web UI / API | Self-hosted search aggregator for Open WebUI and Hermes Agent. Proxied via Caddy. | `service_hosts` |
| **Playwright** | — | `http://<host-ip>:3004` | WebSocket / HTTP | Headless browser scraping service for Open WebUI web loader (`ws://playwright:3000`). | `service_hosts` |
| **SwarmUI** | `http://swarmui.local` | `http://<host-ip>:7801` | Web UI (HTTP) | Generative image creation interface. Proxied via Caddy. | `inference_hosts` |
| **Wan2GP** | `http://wan2gp.local` | `http://<host-ip>:7860` | Web UI (HTTP) | Generative video creation server. Proxied via Caddy. | `inference_hosts` |
| **Forgejo (Web)** | `http://forgejo.local` | `http://<host-ip>:3003` | Web UI / Git | Self-hosted Git repository hosting & CI/CD platform. Data in `~/homelab/forgejo`. | `service_hosts` |
| **Forgejo (SSH)**| — | `ssh://git@<host-ip>:222` | Git over SSH | Git clone and push operations over SSH using port `222`. | `service_hosts` |
| **Caddy Proxy** | `http://<host-ip>:80` | `http://localhost:80` | HTTP Proxy | Reverse proxy routing `.local` requests to Quadlet containers. | `service_hosts` |
| **Homepage** | `http://homepage.local` | `http://<host-ip>:3002` | Web UI (HTTP) | Single-page dashboard for all local services with bookmarks, site monitoring, and widgets. Proxied via Caddy. | `service_hosts` |
| **Glances** | `http://glances.local` | `http://<host-ip>:61208` | Web UI / REST API | Host resource monitoring (CPU, memory, temp, uptime, disk) exposing the REST API consumed by the Homepage Glances info widget. Basic auth enabled. Proxied via Caddy. | `service_hosts` |
| **Avahi Aliases**| Host native (`avahi-tools`) | mDNS (`*.local`) | mDNS Publishing | Publishes LAN mDNS aliases for local service resolution. | `service_hosts` |

---

### How Network Access Works

1. **mDNS Hostname Resolution (`*.local`)**:
   - The `avahi` role publishes `.local` hostnames across your LAN.
   - Any LAN device (Linux, macOS, Windows 10/11, iOS, Android) resolves these hostnames directly without a custom local DNS server.
2. **Reverse Proxy Routing (Caddy)**:
   - Caddy binds to host port `80` (configured via sysctl `net.ipv4.ip_unprivileged_port_start = 80`).
   - Requests to `*.local` domains forward to container backends based on `Host` headers.
3. **Direct Port Exposure**:
   - Every service also publishes a direct host port (see the **Direct Host / Port** column above) so it can be reached at `http://<host-ip>:<port>` without mDNS or the reverse proxy.
   - Forgejo additionally binds SSH port `222` directly to the host.

---

### Fallback Access & Client Troubleshooting

If a device cannot resolve `.local` mDNS hostnames:

1. **Direct Host Port Access**:
   Reach any service directly by its published port, e.g. `http://<host-ip>:8000` for SillyTavern or `http://<host-ip>:8080` for llama-swap (see the **Direct Host / Port** column above).
2. **Static Host Overrides (`/etc/hosts` or `C:\Windows\System32\drivers\etc\hosts`)**:
   Add target host IP address and service hostnames:
   ```text
   192.168.1.100  sillytavern.local hermes.local llamaswap.local forgejo.local openwebui.local glances.local
   ```
3. **Direct HTTP Host Header Verification**:
   ```bash
   curl -H "Host: sillytavern.local" http://<host-ip>
   ```
4. **Verify mDNS Resolution**:
   ```bash
   avahi-resolve -n sillytavern.local
   # or
   ping sillytavern.local
   ```

> [!NOTE]
> Direct host-port access and the Homepage dashboard's IP-aware link rewriting assume a **single-host deployment** (both `inference_hosts` and `service_hosts` on the same machine, as in the default `inventory/hosts.yml`). On a split-host topology, the per-service direct ports and hostnames must be resolved per-host — this is a known limitation to be addressed in a future release.

---

## Secrets Management (Ansible Vault)

Sensitive values (passwords, API tokens) are managed using `ansible-vault` in `inventory/group_vars/all/vault.yml`.

> [!IMPORTANT]
> The encrypted vault file is **gitignored**. For a complete list of supported secret keys and management commands, refer to the [Configuration Reference](docs/configuration.md#secrets-management-ansible-vault).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
