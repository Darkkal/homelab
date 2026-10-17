# Web Gallery source codification

Part of #52. This addition is inactive: `webgallery_enabled: false` selects no
unit, creates no application directories, and adds no Caddy route. Source merge
is not deployment or operational closeout.

The existing Compose service is the baseline. Ansible owns **both complete JSON
files**, `settings.json` and `scrapers/gallery-dl/gallery-dl.conf` under the adopted
data directory. It replaces them on apply, restoring the declared configuration
if the application UI has edited them. Change desired variables to retain UI
changes. These are ordinary full-file templates, not application defaults,
seed-once files, or a live credential-subtree merge. Neither file is read-only.

## Operator variables

Keep host paths, image identity and full preserved dictionaries in protected,
gitignored `inventory/host_vars/<host>/webgallery.yml` (mode 0600). The initial
sanitized desktop file was prepared locally; it contains a Vault **reference**,
not a copied token. Protect and back up that file separately; a checkout alone
cannot reconstruct the owner's configuration. Tracked examples use placeholders.
Do not enable the example as a new installation or treat it as an app seed.

```yaml
webgallery_image: "sha256:<existing-local-image-id>"
webgallery_data_dir: /absolute/existing/data
webgallery_media_dir: /absolute/existing/media
webgallery_browser_dir: /absolute/existing/firefox
webgallery_port: 3000  # preserve the existing Compose port
webgallery_timezone: UTC  # preserve the existing TZ
# Full adopted dictionaries, including all existing non-secret options:
webgallery_settings: <complete-preserved-settings-mapping>
webgallery_gallery_dl_config: <complete-preserved-gallery-dl-mapping>
webgallery_extractor_credentials:
  pixiv:
    refresh-token: "{{ vault_webgallery_pixiv_refresh_token }}"
```

The credential mapping is combined with the **declared dictionary**, then the
entire gallery-dl configuration is JSON-encoded and written. This never reads or
merges a live file. Pixiv's token must be defined and nonempty. Later extractor
credentials can be ordinary mapping entries referencing their own Vault variables.
The only current required Vault key is `vault_webgallery_pixiv_refresh_token`, in
the existing encrypted, gitignored `inventory/group_vars/all/vault.yml`. Populating
that Vault is a separate operator action. Templates and validation suppress logs
and diffs; both JSON files use mode 0600 and the deploying user's UID/GID.

`DATA_DIR=/data`, `MEDIA_DIR=/media`, production mode, existing host port,
`UserNS=keep-id` and the image's node UID/GID (1000 by default) mirror Compose.
The image is an existing local image ID with `Pull=never`; no build/pull pipeline
or implicit image auto-update is introduced. Data/media mounts follow the repo's
`:Z` policy. The existing Firefox-profile and `/etc/localtime` mounts stay
read-only **without relabeling**. No browser data is read, exported, logged or put
in Vault. Database, media, scraper archives and logs are not templated, migrated,
or recursively chowned. Systemd captures stdout/stderr and restarts on failure;
no new scrape/transcode limits or provider health probes are introduced.

Once separately activated, Caddy's optional `webgallery.home` route targets
`webgallery:3000` on `homelab.network`, and Homepage discovers the container labels.
Direct HTTP retains the adopted host port. Adding that route happens only after
opt-in; no proxy, firewall, DNS or client-trust changes are part of source work.

## Baseline evidence and limitations

Read-only discovery on 2026-10-17 used stored OCI metadata and compared the local
Compose file to its tracked source. Both data/media sources matched the Compose
inputs. All four expected mounts existed; browser/timezone were read-only; the
process UID was 1000. Both complete JSON files were present. A sanitizer tested
with synthetic data replaced the one detected credential (Pixiv refresh token)
with a Vault reference before writing protected operator variables. No `.env`,
configuration values, cookies, full inspect, process environment or Vault was
printed. Existing config files remain in place as the future rollback source.

The local application checkout is revision
`2f74409360d8be57bfb965a1b7232f51020f1796`; its explicit gallery-dl config path,
settings writer and runtime Dockerfile were inspected. The stored container image
ID is retained privately, but **its build revision and current running state are
unverified**. The Podman metadata CLI attempted a runtime-directory mutation and
was blocked by the sandbox; it was not retried. Stored metadata is not a fresh
live inspect. The Compose port is preserved from its inputs, but effective live
port bindings, image contents, UID/GID mappings and SELinux behavior must be
rechecked during the approved takeover window.

## Isolated validation

```sh
python3 -m unittest discover -s tests -p 'test_webgallery_ansible.py' -v
python3 -m unittest discover -s tests -p 'test_decommission_source_audit.py' -v
ANSIBLE_LOCAL_TEMP=/tmp/webgallery-policy-ansible python3 -m unittest discover -s tests -p 'test_decommission_policy.py' -v
```

The Ansible harness uses temporary inventory, temporary configuration paths and
dummy credentials, with service handlers replaced by debug events. It runs native
syntax/check/template tasks, proves repeat-run idempotence and desired-state
restoration, and rejects missing/empty tokens before configuration writes. The
actual user Quadlet generator is run against temporary unit files; its generated
arguments verify space-containing mounts, environment, port, labels and read-only
browser access. No production inventory, decrypted Vault, host service, browser
or provider endpoint participates. Ansible requires permission for local IPC in
restricted sandboxes. All 6 Web Gallery tests, 20 lifecycle-audit tests and 9
lifecycle-policy tests passed, along with full-site syntax checking against a
temporary inventory. The sanitized adopted dictionaries were additionally rendered
with a dummy token into temporary files: both dictionaries retained their complete
contents, and a second run reported `changed=0`. The lifecycle audit traces the optional user service too;
its stale AdGuard pin from #90 was also refreshed after verifying that upstream
change only replaced fallback DNS addresses.

## Separately approved adoption, upgrade and rollback

Before authorizing takeover, review the exact source revision, desktop variables,
image identity, current effective mounts/port/user mapping, ownership and SELinux
labels. Retain the current Compose definition and `.env` in their protected
location, and take a stopped-service backup of the data/database and both JSON
files; back up media separately according to the existing storage policy. Cookies
stay at their original protected source. Verify backup restore in isolation.

In the approved maintenance window, stop the existing Compose service before
Ansible replaces configuration or starts the Quadlet. Populate the encrypted Vault,
then opt in with `webgallery_enabled: true` and apply the reviewed target. Never
start both services against the same database. Verify readiness and an agreed
scraper fixture, then repeat the apply for idempotence. No such actions have been
performed by the source change.

For upgrades, explicitly select/review the new local image and preserve the old
image and stopped-service database/config backup. Application startup may migrate
the database; reverting an image alone is insufficient. Rollback means stopping
the new unit, restoring the matching database/config backup when needed, and
starting the retained original Compose definition. Disabling the variable only
prevents further management; it does **not** remove an already deployed unit or
stop it. Unit cleanup, proxy reversal and operational tests require the approved
rollback plan. Reverting this inactive source PR alone changes no running service.
