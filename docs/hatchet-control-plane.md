# Hatchet control-plane deployment (#109)

This source defines Hatchet as an ordinary service on `service_hosts` using
rootless Podman user Quadlets and the existing `homelab.network`. There is no
additional enable flag. Applying the normal playbook starts `hatchet-postgres`
and `hatchet`; a fresh apply generates and retains its initial settings.
Source merge does not apply the playbook. Live installation and acceptance
belong to [#110](https://forgejo.home/Onmyodo/homelab/issues/110).

## Selected native contract

The initial engine is **v0.110.5** from
[Hatchet commit 56c617e](https://github.com/hatchet-dev/hatchet/tree/56c617e0da399bc9d8a10d2ba74b4950f8a950b8),
packaged as `ghcr.io/hatchet-dev/hatchet/hatchet-lite:v0.110.5`. This is the
standard native server, not the embedded sidecar. Podman runs the published OCI
package without a Docker daemon. No image build or extra queue platform is needed.
The [package recipe](https://github.com/hatchet-dev/hatchet/blob/56c617e0da399bc9d8a10d2ba74b4950f8a950b8/build/package/lite.dockerfile)
provides `/hatchet-lite`, `/hatchet-admin`, `/hatchet-migrate`, static UI assets,
OpenSSL, curl and the PostgreSQL client. Its quickstart generates native
keysets during a pristine first apply; migration and seeding remain separate.
H2 must bind the actual pulled digest, version, build/authentication behavior and
contents to this source; source inspection is not image/runtime qualification.

TypeScript SDK **1.38.0** remains the consumer contract locked by PR #108.
[#100](https://forgejo.home/Onmyodo/homelab/issues/100#issuecomment-9101) supplies
historical same-engine/SDK synthetic registration, affinity and integration
observations. No new qualification campaign or inference was run here. Native
server packaging uses the same engine protocol; later consumers still need
accepted deployed reachability/authentication evidence.

The [native entry point](https://github.com/hatchet-dev/hatchet/blob/56c617e0da399bc9d8a10d2ba74b4950f8a950b8/cmd/hatchet-lite/main.go)
loads the configurable
[server schema](https://github.com/hatchet-dev/hatchet/blob/56c617e0da399bc9d8a10d2ba74b4950f8a950b8/pkg/config/server/server.go).
The tracked launcher clears inherited environment before reading generated
configuration. It validates file presence/mode/ownership, the engine version,
normal auth build and TLS chain/name/key pair; runs the native migration CLI;
then runs native create-if-missing seeding and execs the native server. No
handshake token, quickstart overwrite or stdin keepalive is involved. Key
generation is a separate first-apply task, never a service-start action. Upstream migration connection retry is bounded to 30
seconds; the launcher does not add retry/replay or durable coordination.

PostgreSQL **17-bookworm** is the only backing service: database, PostgreSQL
message queue and PostgreSQL pub/sub are explicit. PostgreSQL traffic stays
inside the existing container network with password authentication and no host
publication; database TLS is disabled within that boundary. The DB is not a
public listener. Rootless keep-id maps container UID/GID 999 to the invoking
host user; Hatchet runs as that same host user's numeric UID/GID. Host state
paths are registered by `base` with mode `0700`. Config/key files are `0600`.
Data is under `pg/pgdata`; packaged code is never masked by a host volume.
Each container gets separate `:Z` mounts, including separate password files,
so one container does not relabel another container's private config directory.

## Interfaces and access

| Interface | Bind / advertised address | Publication and verification |
|---|---|---|
| Worker gRPC | `0.0.0.0:7070`; advertised `hatchet:7070` | Existing network only; TLS 1.3 with retained CA and certificate SAN `hatchet`; tenant token required. |
| API | `:8080`; canonical URL `https://hatchet.{{ lan_domain }}` | Existing network only behind Lite and Caddy; native authentication, signup disabled. |
| Native Lite UI / proxy | `:8081` / `:8888` inside container | Caddy proxies `https://hatchet.{{ lan_domain }}` to `hatchet:8888`; Homepage discovers the labeled service. No host backend port; secure cookies are required. |
| Engine health | `:8733/ready` and `/live` | Internal only. `/ready` checks queue and repository, returns 503 during shutdown/unhealthy state. |
| PostgreSQL | `hatchet-postgres:5432` | Internal only; not published to host/LAN. |

Workers connect to Hatchet; Hatchet does not call worker HTTP servers. H2's
forward checks must use the accepted engine endpoint from a separate container
on the existing network and distinguish TLS/authentication from TCP reachability.
No worker activation or model execution is implied by engine readiness.

The API-to-engine internal gRPC client explicitly disables server TLS identity
inheritance. It verifies the `hatchet` hostname against the retained CA using
TLS 1.3, without presenting the server certificate/private key as a client
identity. A server-only `serverAuth` certificate is therefore supported; native
token admission remains required. No insecure or client-certificate fallback
is configured.

Caddy terminates HTTPS at `hatchet.{{ lan_domain }}` (normally
`hatchet.home`) and forwards to the Lite proxy at `hatchet:8888`. Hatchet's
canonical URL, allowed origin and secure cookie domain use the same LAN name.
The shared Podman network remains a trust boundary, not role isolation; API
and Lite proxy HTTP are private to that network and worker gRPC uses TLS.
Backend ports 7070, 8080, 8081, 8733, 8888 and 5432 are not host-published.
The Homepage link uses the LAN domain; no direct-host rewrite is needed.

The existing Uptrace collector polls `http://hatchet:8733/ready` every 30
seconds and sends availability to the existing service-health dashboard and
monitor. Hatchet also configures native OTLP traces and metrics with service
name `hatchet` over gRPC to `uptrace-otelcol:4317`. The collector's gRPC
receiver listens on the shared network and forwards through its existing
Uptrace-authenticated exporters. The launcher supplies fixed matching OTLP
settings to the native process before its metric exporter initializes; the
cleared inherited environment cannot override them. The Hatchet-to-collector hop is plaintext and
unauthenticated on that network, consistent with the existing collector trust
boundary; do not transmit secrets in telemetry. Native telemetry and the
collector pipeline require #110 runtime verification. Prometheus scraping and
application log export are not configured; no claim is made that they are
unsupported. Third-party analytics and external reporting remain disabled.

## Automatic initialization and optional overrides

No settings file needs to be prepared before a fresh apply. The role generates
an admin password, database password, two independent cookie secrets and a tenant
UUID. The initial admin email is `admin@hatchet.local`; the tenant name and slug
are `Default` and `default`. The pinned native image runs a separate one-shot
`hatchet-admin quickstart`
with certificate generation and seeding skipped. Its private generated server
configuration supplies native master and JWT keysets without printing them.
The role retains its own generated 32-character cookie secrets and credentials
for the homelab policy rather than adopting quickstart defaults. OpenSSL in that
image generates a private CA
(valid for 3,650 days) and a server-only certificate for DNS name `hatchet` (365
days). Certificate renewal is an explicit operator action before expiry.

This initialization container has no network, a read-only root filesystem,
no capabilities, no logs and a 60-second execution limit. Podman may pull the
configured image before starting it. It starts neither the database nor the
engine. The ordinary service launcher still performs migrations and
create-if-missing admin/tenant seeding after configuration is ready.

Before rendering configuration, the role publishes
`{{ hatchet_data_dir }}/initial-settings.json`: a service-account-owned `0600`
regular file inside the private data directory. Its version-1 record contains
`settings` (all 14 effective values) and `generated_ca_private_key` (empty if an
external TLS bundle was supplied). Publication is atomic and refuses to replace
an existing record, including a concurrent initializer's record. The generated
CA signing key stays in this record, outside application mounts. Temporary
material is removed even after failure. Secret tasks suppress values and diffs.

Later applies load that record, validate it and render the same settings without
generating new identities. A failed first apply after record publication can
resume using the record. If it is missing alongside existing database or config
state, the role fails rather than generating replacement credentials. Restore
the matching record; existing manually configured deployments require an
operator-reviewed adoption of their original values. Check mode on a fresh host
defers generation and secret-dependent rendering; it does not initialize Hatchet.

Optional `hatchet_settings` values may come from protected **untracked** operator
inventory or encrypted external vars. Unknown keys, invalid types and incomplete
TLS/keyset bundles are rejected. Other keys may be supplied individually before
initialization; generated defaults fill the rest. No real credentials belong in
tracked inventory or examples.

| Keys | Format / purpose |
|---|---|
| `database_password` | 32–128 URL-safe alphanumeric/underscore/hyphen characters; shared by DB initialization and connection configs. |
| `admin_email`, `admin_password` | Email and 8–64 character password with upper/lowercase and a digit; upstream default password rejected. |
| `tenant_id`, `tenant_slug`, `tenant_name` | Lowercase UUID, lowercase slug, nonempty name up to 128 characters. |
| `master_keyset`, `private_jwt_keyset`, `public_jwt_keyset` | Native encoded keysets; supply all three together or let initialization generate them. |
| `cookie_hash_key`, `cookie_block_key` | Distinct 32-character URL-safe strings, retained across restarts. |
| `grpc_cert`, `grpc_key`, `grpc_ca` | PEM certificate, unencrypted private key and CA; supply all three together or use generated TLS. Chain must be valid, key must match and SAN must include `hatchet`. |

After initialization, supplied overrides must match retained values exactly.
Changing inventory cannot silently rotate existing credentials. Bootstrap seed
creates an absent admin/tenant; it does not change an existing user's password.
Database initialization does not change an existing DB role password either.

Back up the private initialization record with matching database and identity
state. Store the generated admin password in the owner's protected password
manager through an approved private local workflow; do not dump the record into
terminal/chat logs or tracked vars. There is no manual copy-out requirement for
subsequent playbook runs. No tenant API token is generated by initialization.

Input assertions validate shape rather than cryptographic keyset validity.
OpenSSL validates TLS before migrations; native loaders reject malformed keysets
before serving, potentially **after migrations**. H2 must validate the actual
native image and generated or supplied material before persistent acceptance.
Native command errors are suppressed to avoid exposing protected values. Native
keyset files must contain the exact encoded value without a trailing newline;
the templates trim surrounding whitespace when rendering them.

| Source | Precedence / reload behavior |
|---|---|
| Private initialization record / optional initial vars | First apply combines generated defaults with optional protected overrides. Later applies use the retained record and reject conflicting overrides. Secret-bearing tasks use `no_log: true`, `diff: false`. |
| Generated files | `config/server.yaml`, `database.yaml`, `database-url`, keysets and TLS files; private atomically replaced individual files, read on startup. File-group replacement is not transactional; stop consumers for identity/credential changes. |
| Process environment | Cleared by `env -i` before the launcher. Image/inherited `SERVER_*`, `DATABASE_*`, `ADMIN_*`, proxy and reporting settings cannot override the protected files. The launcher sets fixed `SERVER_OTEL_SERVICE_NAME`, `SERVER_OTEL_COLLECTOR_URL` and `SERVER_OTEL_INSECURE` values immediately before the native server starts so its early metric initialization matches YAML. Migration alone receives the DSN via its required `DATABASE_URL`; it is unset before server startup. |
| Stable process policy | Container DNS names/bind/ports, private network, TLS, no signup, Caddy LAN UI, no external reporting, startup bounds and path layout are tracked invariants. No arbitrary endpoint/trust override is accepted through ambient environment. |
| Package/update policy | `hatchet_image`, `hatchet_postgres_image`, their `*_autoupdate` settings and `hatchet_data_dir` are operator inputs. Allowed initial version tags may include a digest pin; only registry/disabled update modes are accepted. |

Changing config/launcher notifies Hatchet restart. PostgreSQL password-file
changes notify PostgreSQL then Hatchet; existing DB role rotation still requires
a stopped operator rotation procedure. No hot reload is claimed. Units use
bounded on-failure restart (three starts in five minutes), not an unbounded
restart loop. `Notify=healthy` holds systemd startup open until Podman's first
successful `/ready` healthcheck, so `TimeoutStartSec=180` bounds migration,
seeding and engine readiness rather than only container creation. Healthchecks
run every 10 seconds with a five-second execution limit, a 120-second startup
grace and three failure retries. Failure to become ready within 180 seconds
makes systemd fail and stop that startup attempt; cleanup has the separate
45-second stop bound. No automatic task replay or worker restart scheme is
added. PostgreSQL starts first; migrations also have the native 30-second
connection wait. A startup failure leaves Hatchet unavailable, not skipped.

The native Lite parent returns on interrupt without joining the engine's
cleanup goroutine. `exec` delivers the container signal directly to that native
process; the unit's 45-second stop bound does not prove graceful engine drain.
H2 must verify stop/recovery behavior honestly, including this upstream limit;
no successful task drain is claimed by this source.

The Hatchet container sends the launcher’s fixed stage messages to the user
journal; PostgreSQL container logging remains disabled. All native startup
output is discarded: upstream errors can include URLs/configuration. Do not
use raw process environments, logs, inspect dumps or secret diffs for diagnosis.
Use file names/counts/permissions, exit/service state, health status and approved
non-secret image/version identities. H2 owns any additional reviewed secret-safe
diagnostic procedure; this source adds no verifier framework.

## Updates, persistence and rollback limits

Credential or certificate rotation requires a reviewed stopped procedure: stop
consumers and services, back up matching state, use the native DB/admin mechanisms
where needed, update the private record and protected rendered files together,
and validate before restart. Preserve the CA signing key for certificate renewal.
Do not remove the record to request rotation or leave conflicting initial vars.
No automatic rotation or renewal is implemented.

The ordinary Podman auto-update timer remains in charge. Both units default to
`AutoUpdate=registry` on their configured version tags. This refreshes those
tags, not arbitrary future engine or PostgreSQL major versions. No new updater,
local build or timer is introduced. A temporary digest pin plus `disabled`
override uses the existing policy inputs; version/platform changes require
reviewed source compatibility work. H2 must record actual image identities and
retain the previously accepted images/configuration and a usable database backup.

Startup migrations precede readiness and can change schema. A binary rollback
or Git revert does **not** undo a migration; restoring an old binary against a
new schema is unsupported until compatibility is established. Preserve
PostgreSQL data together with the private initialization record, master/JWT
keysets, tenant identity, cookie secrets and TLS/CA material. Restoring data without its matching identities is not a rollback.
New tokens are issued explicitly through native administration with a bounded
expiry and stored directly in the protected consumer source; no token is minted
or printed by normal startup. Revocation/rotation and worker deployment remain
separate operator work.

## #110 installation and acceptance handoff

1. Obtain #110's fresh operational authority for a specific intended service
   host and the exact reviewed **merged** source revision. Record the digest,
   package/auth build, clean source state and retained backups. The current
   source branch is not an installation approval.
2. For a fresh deployment, leave `hatchet_settings` absent unless specific initial
   overrides are needed. Confirm no prior state exists. For existing state,
   restore its matching private initialization record before applying. Check
   ownership, mode and parser outcomes without printing values.
3. Under that authority, run the normal `playbooks/site.yml` with the approved
   host limit and vault password source (plus optional protected overrides). Verify
   native first-run generation and the retained record, generated units, rootless
   UID mappings and separate SELinux labels. Validate the actual CA/certificate
   and keysets. Repeat the approved apply: settings must remain unchanged and
   generation must be skipped. Check fresh-host check-mode deferral, lost-record
   refusal and conflicting-override rejection. Back up the record privately.
   No additional Hatchet feature flag is needed. Keep other services unchanged.
4. Record only bounded results: `systemctl --user is-active hatchet-postgres
   hatchet`, each container's health state, internal `/ready` status and exact
   version/digest. Check actual listeners and absence of host port publication;
   separately verify HTTPS browser login and cookie/origin behavior at the LAN
   name, Homepage discovery, API admission, internal API-to-engine TLS with a
   server-only certificate, and TLS/token gRPC reachability from the consumer
   network, including rejected unauthenticated access. Verify the Uptrace
   readiness check and native Hatchet traces/metrics. Verify service startup remains
   pending until healthy and a stalled pre-readiness phase reaches the configured
   deadline and stop bound. Do not print
   token commands/results or full container inspect/config objects.
5. Verify retained tenant/signing identity and data after an approved engine/DB
   restart. Check startup bounds and stop/backout before persistent acceptance.
   Stop on unexpected listeners, wrong target, secret output, restart loops,
   drift or uncertain storage compatibility. No blind replay or data downgrade.
6. Stop consumers first, then `systemctl --user stop hatchet.service
   hatchet-postgres.service`. Confirm those endpoints are unavailable and other
   services remain unchanged. To withdraw deployment, remove only the installed
   `hatchet.container` / `hatchet-postgres.container` sources under the approved
   backout, reload the user manager, and retain all data/config. Reverting Git
   alone does not remove already installed Quadlet files. Do not delete `pg/`
   or replace keysets. Restore only an accepted compatible image/configuration
   and matching storage backup under #110's explicit restoration authority.

## Authority and verification matrix

| Outcome | Authority / evidence |
|---|---|
| Native source and protected schema | #109; normal service placement, base directories, launch/config templates and bounded source checks. |
| Independent source review / merge | Separate reviewer and owner; pending until recorded against the exact source head. |
| Protected configuration / host installation | Owner-operated playbook run; full #110 acceptance remains to be recorded. |
| Generated units, readiness, auth, network and persistence | #110 host agent; not claimed passed by syntax/template checks. |
| Worker activation / inference / webhook cutover | Later child contracts; no authority from engine health. |

Available source validation: playbook syntax (controller temp directory under
`/tmp`), shell syntax, template render/YAML parse with synthetic values and
package/schema assertion evaluation and synthetic atomic record publication
checks. The owner also requested an isolated manual native quickstart and
disposable database investigation; that study is not live acceptance. No new
fixture suite, reusable harness or pipeline was added. The existing lifecycle source audit now explicitly classifies the two
additional user Quadlets, private file destinations, user-scoped restart handlers,
native launcher and configuration templates; its mutation checks remain active.
Required remote CI, independent review and all H2 runtime checks must be
recorded separately. Source and runtime remain separately reversible outcomes;
no new child or parent approval gate is introduced.

## Historical embedded-launcher findings

The original checkpoint inspected `hatchet-embedded v0.110.5`, commit
[`3dc26f9`](https://github.com/hatchet-dev/hatchet-embedded/tree/3dc26f939dfc5c1072c35dedc65bf51313d665a7).
Its `go.mod` selects engine v0.110.5 and embedded-postgres v1.34.0. Its published
sidecar requires a private handshake file and exits on stdin EOF or signal.
Bundled PostgreSQL uses development credentials. These findings led to selecting
the standard native entry point within #109; the earlier parent escalation was
withdrawn at the owner's direction.

`embed.go` sets the following values after loading server configuration:

| Interface | Forced behavior | Deployment consequence |
|---|---|---|
| gRPC bind | `127.0.0.1`, configurable port | Separate worker containers cannot connect over the existing network. |
| gRPC advertised address | `127.0.0.1:<port>` | Advertising a container DNS name through an environment variable does not override this assignment. |
| gRPC TLS | Insecure | Protected trust policy cannot be implemented by setting a TLS variable that this override replaces. |
| REST server URL | `http://localhost:<port>` | Not a configured LAN URL or evidence of private binding. |
| REST listener | `:<port>` in the engine's API server | Wildcard listener needs an actual containing network boundary. |
| Session cookies | Domain `localhost`, insecure, random secrets on each start | Ordinary LAN UI sessions and stable restart behavior need a different accepted interface. |
| Engine healthcheck | Disabled | TCP listener readiness alone is not authenticated service health. |

The REST listener is established in
[api/v1/server/run/run.go](https://github.com/hatchet-dev/hatchet/blob/56c617e0da399bc9d8a10d2ba74b4950f8a950b8/api/v1/server/run/run.go#L177).
The complete embedded [options](https://github.com/hatchet-dev/hatchet-embedded/blob/3dc26f939dfc5c1072c35dedc65bf51313d665a7/options.go)
and sidecar flag list expose port selection, API/migration suppression, storage,
queue and logging controls, but no bind/advertisement/TLS/cookie override.
The Go options include admin credentials and keysets; even those do not replace
the forced network settings.

Publishing a container port cannot forward to a loopback-only listener in that
container. Sharing a network namespace with every worker, adding a forwarding
gateway or patching upstream would change the agreed topology. Selecting the
standard native entry point remains implementation work within #109.

Startup waits for TCP connections to the gRPC and optional API ports, with a
30-second bound, before writing the handshake. It mints a tenant token with a
90-day expiry and may register a CLI profile in the process home. Those are
sensitive state and lifecycle concerns for a future deployment; TCP readiness
does not prove worker admission, model execution or restart recovery.
