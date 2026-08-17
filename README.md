# Homelab Infrastructure

An automated, declarative homelab infrastructure managed with **Ansible** and **Podman Quadlets** integrated into `systemd`.

---

## Overview

This repository automates the deployment and configuration of self-hosted homelab services. Services run as rootless Podman containers defined via Podman Quadlet systemd unit files, orchestrated centrally through Ansible playbooks.

Services are accessible on your local network (LAN) via `*.home` hostnames resolved by the AdGuard Home DNS server and routed through a Caddy reverse proxy. This works on every device, including Android, which cannot use mDNS/`.local` names in browsers.

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

Run the main playbook to deploy container networks, Quadlet unit files, the AdGuard Home DNS server, and the Caddy reverse proxy:

```bash
ansible-playbook playbooks/site.yml --ask-become-pass --vault-password-file .vault-pass
```

> **Note:** `--ask-become-pass` (`-K`) is required for root tasks (setting unprivileged port 80 sysctl, system package installations, and enabling user lingering).

---

### Step 6: Verify Deployed Services

Check status of user-level Podman Quadlet services:

```bash
systemctl --user status caddy sillytavern open-webui llama-swap forgejo glances searxng playwright piclaw uptrace uptrace-clickhouse uptrace-postgres uptrace-redis uptrace-otelcol adguardhome
```

Verify DNS address resolution from your local workstation:

```bash
dig @<host-ip> sillytavern.home
```

---

## Services & Network Access Directory

Once deployed, all services are accessible across your LAN using **DNS hostnames** (`*.home`) served by AdGuard Home, or direct host ports.

| Service | Primary LAN URL | Direct Host / Port | Access Protocol | Description & Authentication | Ansible Group |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **llama-swap** | `https://llamaswap.home` | `http://<host-ip>:8080` | Web UI & API | Model swap proxy & inference controller. Proxied via Caddy. | `inference_hosts` |
| **SillyTavern** | `https://sillytavern.home` | `http://<host-ip>:8000` | Web UI (HTTPS) | LLM chat & roleplay UI. Connects to `llama-swap:8080`. LAN-only, no auth. | `service_hosts` |
| **Open WebUI** | `https://openwebui.home` | `http://<host-ip>:8081` | Web UI (HTTPS) | Open WebUI chat & LLM interface. Proxied via Caddy. | `service_hosts` |
| **SearXNG** | `https://searxng.home` | `http://<host-ip>:8082` | Web UI / API | Self-hosted search aggregator for Open WebUI. Proxied via Caddy. | `service_hosts` |
| **Playwright** | — | `http://<host-ip>:3004` | WebSocket / HTTP | Headless browser scraping service for Open WebUI web loader (`ws://playwright:3000`). | `service_hosts` |
| **PiClaw** | `https://piclaw.home` | `http://<host-ip>:8083` | Web UI (HTTPS) | Stateful AI coding agent & workspace interface. Proxied via Caddy. Data in `~/homelab/piclaw`. | `service_hosts` |
| **SwarmUI** | `https://swarmui.home` | `http://<host-ip>:7801` | Web UI (HTTPS) | Generative image creation interface. Proxied via Caddy. | `inference_hosts` |
| **Forgejo (Web)** | `https://forgejo.home` | `http://<host-ip>:3003` | Web UI / Git | Self-hosted Git repository hosting & CI/CD platform. Data in `~/homelab/forgejo`. | `service_hosts` |
| **Forgejo (SSH)**| — | `ssh://git@<host-ip>:222` | Git over SSH | Git clone and push operations over SSH using port `222`. | `service_hosts` |
| **Caddy Proxy** | `https://<host-ip>` | `http://<host-ip>:80` | HTTP/HTTPS Proxy | Reverse proxy routing `.home` requests to Quadlet containers over HTTPS. | `service_hosts` |
| **Homepage** | `https://homepage.home` | `http://<host-ip>:3002` | Web UI (HTTPS) | Single-page dashboard for all local services with bookmarks, site monitoring, and widgets. Proxied via Caddy. | `service_hosts` |
| **Glances** | `https://glances.home` | `http://<host-ip>:61208` | Web UI / REST API | Host resource monitoring (CPU, memory, temp, uptime, disk) exposing the REST API consumed by the Homepage Glances info widget. Basic auth enabled. Proxied via Caddy. | `service_hosts` |
| **Uptrace** | `https://uptrace.home` | `http://<host-ip>:14318` | Web UI / API (OTLP) | OpenTelemetry-based observability (distributed traces, metrics, logs) with ClickHouse, PostgreSQL, Redis, and an OTel Collector handling host metrics, synthetic health checks, and Prometheus scraping of llama-swap / Forgejo / ClickHouse. Ships six auto-provisioned dashboards (`Homelab: Host / Service Health / GPU / Forgejo / ClickHouse / Uptrace Databases`) with bundled metric monitors. Proxied via Caddy. | `service_hosts` |
| **AdGuard Home** | `http://<host-ip>:8090` | `http://<host-ip>:8090` | Web UI / DNS (53) | LAN DNS server & ad blocker. Serves a wildcard `*.home` rewrite so any device pointed at `<host-ip>` (port 53) resolves every `*.home` hostname, with public queries forwarded to Quad9. Runs on the host network; admin UI accessed directly at `http://<host-ip>:8090`. | `service_hosts` |
| **Avahi Aliases**| Host native (`avahi-tools`) | mDNS | mDNS Publishing | Legacy Avahi mDNS publishing, retained for compatibility; hostname resolution now happens via AdGuard Home DNS (`*.home`). See [issue #65](https://github.com/Darkkal/homelab/issues/65). | `service_hosts` |

---

### How Network Access Works

1. **DNS Hostname Resolution (`*.home`)**:
   - The AdGuard Home DNS server (host port `53`) answers every `*.home` name with the host's LAN IP and forwards all other queries upstream to Quad9.
   - Point a device's DNS at the homelab host (`<host-ip>`, port `53`), or have your router hand it out via DHCP, and it resolves any `*.home` service hostname — on Linux, macOS, Windows, iOS, and Android alike. See [Using AdGuard Home as your LAN DNS](#using-adguard-home-as-your-lan-dns).
   - The legacy Avahi mDNS aliases are retained for compatibility but are no longer the resolution path (see [issue #65](https://github.com/Darkkal/homelab/issues/65)).
2. **Reverse Proxy Routing (Caddy)**:
   - Caddy binds to host ports `80` and `443` (configured via sysctl `net.ipv4.ip_unprivileged_port_start = 53`).
   - Requests to `*.home` domains forward to container backends based on `Host` headers.
3. **Automatic Local HTTPS**:
   - All `.home` sites are served over **HTTPS** by default. Caddy uses its built-in internal Certificate Authority (["Local HTTPS"](https://caddyserver.com/docs/automatic-https#local-https)) to sign certificates for `.home` hostnames automatically, and redirects `http://` requests to `https://`.
   - The internal CA root certificate is generated and stored at `~/homelab/caddy/data/caddy/pki/authorities/local/root.crt` on the host. LAN clients must trust this root certificate to avoid browser security warnings — see [Trusting Caddy's Local CA](#trusting-caddys-local-ca) below.
4. **Direct Port Exposure**:
   - Every service also publishes a direct host port (see the **Direct Host / Port** column above) so it can be reached at `http://<host-ip>:<port>` without DNS or the reverse proxy. Direct ports remain plain HTTP.
   - Forgejo additionally binds SSH port `222` directly to the host.

---

### Trusting Caddy's Local CA

The `.home` certificates are signed by Caddy's self-hosted internal CA ("Caddy Local Authority"). Browsers and apps will flag the connections as untrusted until you install the CA root certificate on each device that accesses the dashboard.

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
   - **Firefox (desktop)** (uses its own trust store): Settings → Privacy & Security → Certificates → *View Certificates* → *Authorities* → *Import* `root.crt` and tick "Trust this CA to identify websites".
   - **Android — Chrome**: install `root.crt` via Settings → Security → *Install a certificate* (CA certificate). Chrome (and other Chromium-based browsers) honors user-installed CA certificates.
   - **Android — Firefox**: Firefox for Android ships its own certificate store and **cannot import a custom CA certificate** in release builds, so `https://*.home` will always fail in Android Firefox even after installing `root.crt`. Use Chrome for trusted HTTPS on Android, or plain `http://<host-ip>:<port>` direct-port access.

> [!IMPORTANT]
> The CA root certificate is private to your homelab. Keep `~/homelab/caddy/data/` backed up — if it is lost, Caddy generates a new CA and every device must re-trust it. The `/data` volume is persistent across container restarts and image auto-updates.

---

### Using AdGuard Home as your LAN DNS

AdGuard Home runs as a rootless Quadlet service on `service_hosts`, listening on host port `53` (TCP+UDP), and doubles as the LAN's ad-blocking DNS resolver.

- **Provisioning**: The playbook automates the first-run setup via AdGuard Home's HTTP API — the admin user is created from `vault_adguard_username` / `vault_adguard_password` (or an auto-generated password stored in `~/homelab/.adguardhome_password`), upstream DNS is set to Quad9 (`adguardhome_upstream_dns`), and a wildcard rewrite `*.home → <host-ip>` is added. Re-runs are idempotent.
- **Pointing a device at it**: set the device's DNS server to `<host-ip>`. Any `*.home` hostname then resolves to the homelab host — including on Android, which cannot use mDNS and instead resolves `.home` through this DNS server.
- **Admin UI**: `http://<host-ip>:8090` directly (AdGuard runs on the host network, so its web UI is not routed through Caddy).
- **Verification**: `dig @<host-ip> homepage.home` should return the host's LAN IP, and `dig @<host-ip> example.com` should return a public answer via Quad9.

> [!NOTE]
> [!NOTE]
> We use the private-use `.home` TLD specifically because `.local` (RFC 6762) is reserved for mDNS, and Android's system resolver will not query a DNS server for `.local` names — so mDNS-based names can never work in Android browsers. AdGuard Home serves `*.home` via DNS, which Android forwards normally.

---

### Fallback Access & Client Troubleshooting

If a device cannot resolve `.home` hostnames:

1. **Point the device's DNS at AdGuard Home**:
   - The preferred fix: configure the device's DNS server to `<host-ip>` (port `53`), and it will resolve every `*.home` service hostname via the AdGuard Home wildcard rewrite. On Android: Wi-Fi settings → modify network → IP settings → *Static* → DNS 1 = `<host-ip>`.
   - This is the only option that gives trusted `https://*.home` access on Android Chrome (install `root.crt` as described above, then use the normal `.home` URLs).
2. **Direct Host Port Access**:
   Reach any service directly by its published port, e.g. `http://<host-ip>:8000` for SillyTavern or `http://<host-ip>:8080` for llama-swap (see the **Direct Host / Port** column above). Direct ports are plain HTTP — do not prepend `https://`.
3. **Static Host Overrides (`/etc/hosts` or `C:\Windows\System32\drivers\etc\hosts`)**:
   Add target host IP address and service hostnames:
   ```text
   192.168.1.100  sillytavern.home llamaswap.home forgejo.home openwebui.home glances.home
   ```
4. **Direct HTTP Host Header Verification**:
   ```bash
   curl -k -H "Host: sillytavern.home" https://<host-ip>
   ```
   (`-k` skips certificate verification; add `--resolve sillytavern.home:443:<host-ip>` if you want to test the `https://` URL directly without touching DNS.)
5. **Verify DNS Resolution**:
   ```bash
   dig @<host-ip> sillytavern.home
   # or
   nslookup sillytavern.home <host-ip>
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
