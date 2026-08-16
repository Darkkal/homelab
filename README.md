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
systemctl --user status caddy sillytavern open-webui llama-swap forgejo glances searxng playwright piclaw uptrace uptrace-clickhouse uptrace-postgres uptrace-redis uptrace-otelcol
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
| **llama-swap** | `https://llamaswap.local` | `http://<host-ip>:8080` | Web UI & API | Model swap proxy & inference controller. Proxied via Caddy. | `inference_hosts` |
| **SillyTavern** | `https://sillytavern.local` | `http://<host-ip>:8000` | Web UI (HTTPS) | LLM chat & roleplay UI. Connects to `llama-swap:8080`. Basic auth enabled (`vault_sillytavern_user`). | `service_hosts` |
| **Open WebUI** | `https://openwebui.local` | `http://<host-ip>:8081` | Web UI (HTTPS) | Open WebUI chat & LLM interface. Proxied via Caddy. | `service_hosts` |
| **SearXNG** | `https://searxng.local` | `http://<host-ip>:8082` | Web UI / API | Self-hosted search aggregator for Open WebUI. Proxied via Caddy. | `service_hosts` |
| **Playwright** | — | `http://<host-ip>:3004` | WebSocket / HTTP | Headless browser scraping service for Open WebUI web loader (`ws://playwright:3000`). | `service_hosts` |
| **PiClaw** | `https://piclaw.local` | `http://<host-ip>:8083` | Web UI (HTTPS) | Stateful AI coding agent & workspace interface. Proxied via Caddy. Data in `~/homelab/piclaw`. | `service_hosts` |
| **SwarmUI** | `https://swarmui.local` | `http://<host-ip>:7801` | Web UI (HTTPS) | Generative image creation interface. Proxied via Caddy. | `inference_hosts` |
| **Forgejo (Web)** | `https://forgejo.local` | `http://<host-ip>:3003` | Web UI / Git | Self-hosted Git repository hosting & CI/CD platform. Data in `~/homelab/forgejo`. | `service_hosts` |
| **Forgejo (SSH)**| — | `ssh://git@<host-ip>:222` | Git over SSH | Git clone and push operations over SSH using port `222`. | `service_hosts` |
| **Caddy Proxy** | `https://<host-ip>` | `http://<host-ip>:80` | HTTP/HTTPS Proxy | Reverse proxy routing `.local` requests to Quadlet containers over HTTPS. | `service_hosts` |
| **Homepage** | `https://homepage.local` | `http://<host-ip>:3002` | Web UI (HTTPS) | Single-page dashboard for all local services with bookmarks, site monitoring, and widgets. Proxied via Caddy. | `service_hosts` |
| **Glances** | `https://glances.local` | `http://<host-ip>:61208` | Web UI / REST API | Host resource monitoring (CPU, memory, temp, uptime, disk) exposing the REST API consumed by the Homepage Glances info widget. Basic auth enabled. Proxied via Caddy. | `service_hosts` |
| **Uptrace** | `https://uptrace.local` | `http://<host-ip>:14318` | Web UI / API (OTLP) | OpenTelemetry-based observability (distributed traces, metrics, logs) with ClickHouse, PostgreSQL, Redis, and an OTel Collector handling host metrics, synthetic health checks, and Prometheus scraping of llama-swap / Forgejo / ClickHouse. Ships six auto-provisioned dashboards (`Homelab: Host / Service Health / GPU / Forgejo / ClickHouse / Uptrace Databases`) with bundled metric monitors. Proxied via Caddy. | `service_hosts` |
| **Avahi Aliases**| Host native (`avahi-tools`) | mDNS (`*.local`) | mDNS Publishing | Publishes LAN mDNS aliases for local service resolution. | `service_hosts` |

---

### How Network Access Works

1. **mDNS Hostname Resolution (`*.local`)**:
   - The `avahi` role publishes `.local` hostnames across your LAN.
   - Any LAN device (Linux, macOS, Windows 10/11, iOS, Android) resolves these hostnames directly without a custom local DNS server.
2. **Reverse Proxy Routing (Caddy)**:
   - Caddy binds to host ports `80` and `443` (configured via sysctl `net.ipv4.ip_unprivileged_port_start = 80`).
   - Requests to `*.local` domains forward to container backends based on `Host` headers.
3. **Automatic Local HTTPS**:
   - All `.local` sites are served over **HTTPS** by default. Caddy uses its built-in internal Certificate Authority (["Local HTTPS"](https://caddyserver.com/docs/automatic-https#local-https)) to sign certificates for `.local` hostnames automatically, and redirects `http://` requests to `https://`.
   - The internal CA root certificate is generated and stored at `~/homelab/caddy/data/caddy/pki/authorities/local/root.crt` on the host. LAN clients must trust this root certificate to avoid browser security warnings — see [Trusting Caddy's Local CA](#trusting-caddys-local-ca) below.
4. **Direct Port Exposure**:
   - Every service also publishes a direct host port (see the **Direct Host / Port** column above) so it can be reached at `http://<host-ip>:<port>` without mDNS or the reverse proxy. Direct ports remain plain HTTP.
   - Forgejo additionally binds SSH port `222` directly to the host.

---

### Trusting Caddy's Local CA

The `.local` certificates are signed by Caddy's self-hosted internal CA ("Caddy Local Authority"). Browsers and apps will flag the connections as untrusted until you install the CA root certificate on each device that accesses the dashboard.

1. On the server, verify the CA has been generated:
   ```bash
   systemctl --user status caddy
   ls ~/homelab/caddy/data/caddy/pki/authorities/local/
   ```
   The file to distribute is `root.crt`.
2. Install the root certificate as a trusted CA on each LAN client:
   - **Linux — Debian/Ubuntu**: copy `root.crt` to `/usr/local/share/ca-certificates/` and run `sudo update-ca-certificates`.
   - **Linux — Fedora/RHEL/Nobara** (uses `p11-kit`): copy `root.crt` to `/etc/pki/ca-trust/source/anchors/` and run `sudo update-ca-trust`.
     ```bash
     sudo cp ~/homelab/caddy/data/caddy/pki/authorities/local/root.crt /etc/pki/ca-trust/source/anchors/
     sudo update-ca-trust
     trust list | grep -A 2 "Caddy Local Authority"   # verify
     ```
   - **macOS**: open `root.crt` in Keychain Access, set *Always Trust*, then verify in *System*.
   - **Windows**: right-click `root.crt` → *Install Certificate* → *Local Machine* → *Trusted Root Certification Authorities*.
   - **Android**: Settings → Security → *Install a certificate* (CA certificate) with `root.crt`.
   - **iOS**: install the profile for `root.crt`, then enable *Full Trust for Root Certificates* in Settings → General → About → Certificate Trust Settings.
   - **Firefox** (uses its own trust store): Settings → Privacy & Security → Certificates → *View Certificates* → *Authorities* → *Import* `root.crt` and tick "Trust this CA to identify websites".

> [!IMPORTANT]
> The CA root certificate is private to your homelab. Keep `~/homelab/caddy/data/` backed up — if it is lost, Caddy generates a new CA and every device must re-trust it. The `/data` volume is persistent across container restarts and image auto-updates.

---

### Fallback Access & Client Troubleshooting

If a device cannot resolve `.local` mDNS hostnames:

1. **Direct Host Port Access**:
   Reach any service directly by its published port, e.g. `http://<host-ip>:8000` for SillyTavern or `http://<host-ip>:8080` for llama-swap (see the **Direct Host / Port** column above).
2. **Static Host Overrides (`/etc/hosts` or `C:\Windows\System32\drivers\etc\hosts`)**:
   Add target host IP address and service hostnames:
   ```text
   192.168.1.100  sillytavern.local llamaswap.local forgejo.local openwebui.local glances.local
   ```
3. **Direct HTTP Host Header Verification**:
   ```bash
   curl -k -H "Host: sillytavern.local" https://<host-ip>
   ```
   (`-k` skips certificate verification; add `--resolve sillytavern.local:443:<host-ip>` if you want to test the `https://` URL directly without touching DNS.)
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
