# Opt-in job routing and trust

This is the source prerequisite for homelab #81. It does not activate the repair
for #80. Operator activation, authenticated LFS, other-consumer checks, rollback
and exact-head game CI belong to #82.

With no `forgejo_runner_job_policy`, or with exactly `{enabled: false}`,
the role renders the pre-change runner config and Quadlet bytes. It does not
stage a trust bundle or notify a restart because of this feature. Other existing
role operations keep their existing semantics; a separate inventory change can
still notify a restart. Never use the shared host to test this branch.

## Inventory configuration

Set `forgejo_runner_job_policy` in ordinary Ansible inventory, for example
`inventory/group_vars/forgejo_runner_hosts.yml`. The hostname, public CA,
certificate fingerprints, image pin and enable flag are not secrets and may be
versioned with the configuration. Runner UUID/token credentials remain in Vault.
The controller requires `cryptography >= 42` in the Python environment used by
Ansible. No additional dependency is installed by this role.

With no policy defined, the role defaults to disabled. To enable it, supply all
fields below in the ordinary inventory. Public PEM files can be kept alongside
inventory and loaded using a controller-side `lookup('ansible.builtin.file',
path, rstrip=false)` to preserve their exact bytes. Use an explicit controller
path, such as one derived from `inventory_dir`.

If an installation previously set `vault_forgejo_runner_job_policy`, move its
public policy fields to `forgejo_runner_job_policy` and remove the old Vault
entry. The legacy Vault variable is still accepted when the ordinary variable is absent,
with a migration notice. If both exist, the ordinary variable takes precedence,
including an explicit `{enabled: false}`. No ordinary default is added to group
variables, so it cannot accidentally mask an existing legacy policy.
Do not move runner tokens or private keys into ordinary inventory.

| Field | Required value when enabled |
| --- | --- |
| `enabled` | Boolean `true` |
| `hostname` | Approved lowercase HTTPS DNS hostname, without scheme/port/IP |
| `job_image` | Exact immutable `forgejo_runner_job_image` digest reference |
| `ca_certificate` | One verified, currently valid public CA certificate in PEM form |
| `ca_sha256` | Approved lowercase SHA-256 fingerprint of that certificate's DER bytes |
| `base_bundle` | Unmodified `/etc/ssl/certs/ca-certificates.crt` bytes from that exact job image, as a YAML string |
| `base_bundle_sha256` | Approved lowercase SHA-256 of the original bundle bytes |

Every field is required; unknown fields and partial/disabled policies carrying
additional fields are rejected, even in check mode, before deployment tasks.
Only the existing single `ubuntu-latest` label tied to that exact image is
supported for activation. A different image or label arrangement needs new
runtime evidence. Private keys, non-certificate text, fingerprint mismatches,
expired/non-CA additions and unsafe mount paths are rejected with a fixed error.
The runner treats volume allowances as glob patterns. Enabled data-directory
paths containing `*`, `?`, `[`, `]`, `{`, `}` or backslash are rejected so the
public bundle allowance remains literal. Plain paths and spaces are supported.

The bundle digest verifies the supplied bytes, **not their provenance**. #82 must
independently extract/verify the base bundle from the pinned image and compare the
added root with the approved service identity. Do not substitute the controller's
trust store, only the added root, a reconstructed bundle, or an arbitrary bundle
with a matching self-supplied checksum. Preserve exact newlines in the inventory
value or public PEM file. Existing roots are copied without removing/reordering them;
the approved public CA is appended. Existing expired roots are preserved too.

## Generated behavior and precedence

On activation the role stages `job-ca-bundle.pem` under the runner data directory,
owned by the runner and mode 0644 (public certificates; protected parent directory).
It generates runner-controlled container options:

- `--add-host <approved-hostname>:host-gateway`: Podman resolves the gateway at job
  creation, without a tracked private IP or a global DNS/Forgejo URL change.
- A read-only `:ro,z` bind at `/opt/homelab/job-ca-bundle.pem`. Shared SELinux
  labeling is deliberate for a public file used by multiple job containers.
  The daemon's own trust remains unchanged. The volume allow-list admits only
  this exact public bundle path when enabled; other host paths remain excluded.
- Runner environment `GIT_SSL_CAINFO`, `SSL_CERT_FILE` and `CURL_CA_BUNDLE` point to
  the combined bundle; `GIT_SSL_CAPATH` is empty. The explicit LFS CAINFO source
  takes precedence over Git's URL/generic CA settings in the tested package.

Never set `GIT_SSL_NO_VERIFY`, even to `false` or an empty string: ordinary Git
checks its presence and disables certificate verification. The role never emits
it. Missing/malformed CAINFO can cause Git LFS fallback; pre-deployment validation
is mandatory. A missing mounted host file subsequently prevents normal container
startup/use rather than intentionally switching to another CA source. Operator
mutation/removal of staged material is outside this source validator's control.

The pinned runner 13 source (`1a633ad51320631293dfcac99755b13659efe784`) maps
`runner.envs` into execution config. Execution config wins over workflow/job env
defaults; runner container host options win the tested conflicting job option.
`container.env`, step-level env, action logic and later `GITHUB_ENV` writes can
still override client settings. A workflow can also invoke Git with its own
configuration or use a different container image. This is **not** isolation from
arbitrary workflow code. #82 must reject or resolve such conflicting consumer
settings, including any TLS-disable variable/configuration, proxy/CA overrides,
custom images or mounts that mask the bundle. Do not promise that this bundle
preserves the roots of a different workflow-selected image. Ansible extra-vars
and the controller remain trusted operator authority; ordinary inherited process
environment is not an opt-in source.

## Verification

Controller-only checks:

```sh
python3 -B -m unittest discover -s tests -p 'test_forgejo_runner*py'
bash tests/test_forgejo_runner_image_commands.sh
```

These use generated certificates and a temporary synthetic localhost inventory.
They replay actual policy/template tasks with check mode, assert unchanged
renders produce `changed=0` and no restart notification, and syntax-check the full
role. They do not execute its user/account/systemd tasks on the shared host.
Pre-change render hashes are fixed regression expectations, independent of main.

Prepare the real-launcher packet on the controller, using a fresh output path:

```sh
python3 -B tests/prepare_forgejo_runner_launcher.py /tmp/homelab-81-launcher
```

The packet uses only freshly generated synthetic certificates, a reserved test
hostname and rendered source policy. Its synthetic base bundle tests preservation
of supplied bytes; it is **not** the production image-root extraction gate.
After checking source and packet hashes, the owner runs:

```sh
sudo -u forgejo-runner env XDG_RUNTIME_DIR=/run/user/1001 \
  python3 -B /tmp/homelab-81-launcher/run_forgejo_runner_launcher.py --run
```

This runs default-before, opt-in and default-after workflows through the installed
local-exec launcher in the existing pinned daemon. It never starts/reconfigures a
daemon, uses a registration token, or contacts a production endpoint. The probe
checks gateway mapping, read-only bundle bytes and effective environment, and
runs ordinary Git against a new loopback-only untrusted TLS fixture. Only fixed
pass/fail records leave the harness. Job lifetime is bounded; cleanup removes
only invocation-named resources and checks the original daemon/config remains.
Local exec uses the equivalent explicit flags; production daemon-mode config
parsing remains a later activation check. Invalid policy tests run before any
launcher invocation; arbitrary malformed policy never reaches a job.

## Activation and rollback handoff

1. Merge/review source separately. Do not deploy merely because source checks pass.
2. Under #82 approval, recheck installed pins, public certificate identity/expiry,
   the nine-repository exposure inventory and chosen canaries. Obtain the exact
   image's original bundle and validate all consumer trust/proxy/image settings.
3. Privately snapshot protected config, trust files, image and prior service
   states. Drain the shared runner before applying the new opt-in policy.
4. Apply the exact merged source/policy only under activation authority. The new
   bundle/config changes deliberately notify the existing restart handler then.
   Keep direct checkout, ROOT_URL, Caddy, host DNS and TLS verification unchanged.
5. Prove route, normal authenticated Git LFS object/hash hydration, other consumers
   and rollback, then separately run canonical CI at the selected current head.
   The tested LFS 3.3.0 package does not pin the workflow's future apt result.
6. Before activation, source revert alone is sufficient. After activation first
   restore the protected pre-change config/image/trust and service snapshot,
   verify the old endpoint matrix (including its known LFS failure), and only then
   revert source. Simply deleting a policy is not the complete operator rollback.

Stop activation on certificate mismatch, missing image roots, unsupported client
or image, conflicting workflow inputs, inability to preserve rollback, or changes
outside runner-created containers. A provider-wide repair or workflow/package
pin needs a separate scope decision.
