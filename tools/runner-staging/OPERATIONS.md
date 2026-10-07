# PR86 staging and delivery packets

Preparation only, under [planner7346](https://forgejo.home/piclaw-horde/homelab/pulls/86#issuecomment-7346).
Approve packet 1 and packet 2 separately or together before executing either.
The owner performs runner-account import and all admin-required deployment.
These packets do not restart a service or invoke a Forgejo job. PR86 remains
Part of #85; expanded review and live acceptance remain pending.

## Bound candidate

| Identity | Value |
| --- | --- |
| Retained archive | `/tmp/h85-delivery/candidate.oci.tar` |
| Archive SHA256 | `59bdbabe360a58e73ae003f8f1b50780b3c45953aa362ba937ee9fcce9a77f99` |
| OCI manifest digest | `sha256:ddd6cc2c7fa22f26c2d0827ff8c4846266ac629ef24f39a1738514ce9d026b24` |
| OCI config / local image ID | `sha256:7e048ab852dac206966554c2d347addb9d31001ea35481c8c498db5b4abaa734` |
| Runner binary SHA256 | `750e70b58440c2778706ce515f0ecd37a00b3564cb1367e780fe3d93ed874bf4` |

The manifest identifies the retained OCI object and its compressed layer blobs.
Podman's local image ID identifies the config, including ordered uncompressed
filesystem diffIDs. They are different hashes. The deployment recommendation is
that full local config ID; it is not a registry manifest reference. Existing
inspection records the inherited config/four diffIDs and one binary-only layer.
No rebuilding or packaging is included in either packet.

## Packet 1: isolated candidate staging

After approval, run as the ordinary owner account, without sudo:

```sh
timeout -k 15s 2100s python3 -B tools/runner-staging/stage.py --execute-approved
```

`stage.py` checks the archive hash before creating anything. It creates one
0700 `/tmp/h85-stage-*` directory; the printed exact directory binds the run.
All engine commands explicitly use `--remote=false`, fresh storage/runroot and
VFS. Every call, including the API service and cleanup, uses a packet-owned
`CONTAINERS_CONF` as its sole configuration input, explicit
`--default-mounts-file` pointing to an empty private file, and
`--network-config-dir` pointing inside the private root. The TOML also pins
Netavark and that network directory, clears configured container environment,
and disables host environment/proxy forwarding. No config module or override
variable is inherited. Paths/ownership/symlinks are checked before the first
engine mutation; missing/invalid controls fail rather than fall back. This
excludes system/rootless containers.conf and host subscription mount files,
without inspecting them. Built-in defaults and the pinned image environment
remain. It imports only the candidate and the owner-exported cached Node archive
(`/tmp/h85-node-pinned.oci.tar`, SHA256
`5c47e9e66b606f2460ee14f0a4e813bcb3bdb2834b8d574641674eb4be033592`),
with a 300-second limit per import. The archive records the original pinned
reference below. OCI export changes manifest representation while retaining the
old digest annotation, which Podman rejects on import. Staging changes only the
index reference annotation to a local transport name; config/layer blobs are
unchanged. Both job and Docker action use the full immutable local config ID
`sha256:2ff56a1e437102232fc4f3923138b9513f0d2e36bc0e57f39c3054a86c884e27`.
No registry acquisition is used because the registry returned manifest unknown
for that digest. The job image pin is unchanged:

```text
data.forgejo.org/oci/node:lts-bookworm@sha256:934240a162082fd8b8a2f90cd5114446443f1eba1c5378f6687167ca405e6584
```

Candidate runtime has a 600-second limit. It uses that fresh engine's Unix
socket, never the running runner's socket. Its environment is constructed from
an allowlist; only fixture home/cache/work and the private socket are mounted.
The candidate runs as container root for writable synthetic fixtures, with
SELinux labeling disabled for this private API consumer, without privileged
mode or host networking. This does not test the production daemon's user mapping.
The script does not read registration, vault, host Git configuration, dotenv
files or credentials; `exec --env-file /dev/null` receives no secret arguments.

The internal dual-stack network `h85-staging` uses `10.85.86.0/24` and
`fd85:86::/64`, without published ports or external routes. Source inspection
found `exec` always starts its artifact cache on an ephemeral TCP port bound to
all interfaces **inside the candidate container**. No host listener is created.
Dual stack gives the upstream outbound-IP fallback two global-unicast interface
addresses; its current single-address fallback would return nil. This listener
is stopped with the candidate; no cache protocol requests are claimed.

The two synthetic bare Git caches have exact URL-derived SHA256 directories and
full commit refs, with `origin=https://fixture.invalid/actions/{checkout,cache}`.
The actual upstream `git.Clone` route reuses those refs, creates worktrees and
runs the remote-action `CopyDir` code. It cannot fetch externally on the internal
network. Both trees contain `.eslintignore`, `action.yml` and executable JS in
`dist/`. JS asserts its real path under `/run/act/actions/` and reads the copied
file. Both main actions write marker files into the internal action volume and
save lifecycle state. A normal workflow script reads those files; a Docker
container action using the same Node image config ID reads the script marker through normal
`GetBindsAndMounts`. Real post actions run in reverse order, check restored state,
and the final checkout post verifies the cache post marker. Pass requires runner
exit zero plus all three assertion markers; no text/path mock substitutes for
runtime copying or post execution.

Source trace at runner v13 commit `1a633ad51320631293dfcac99755b13659efe784`:
`internal/app/cmd/exec.go` → `runner.New`/plan executor;
`act/runner/step_action_remote.go` → `act/common/git/git.go` cached full-ref
worktree → job container `CopyDir`; `run_context.go` action-cache and internal
volume construction; `step_docker.go` normal shared mounts; `act/runner/action.go`
main/post state consumers. The retained patch changes Linux root/act returns.
`exec` allows all volumes, so this is **not** daemon trust/valid-volume admission
coverage. It does not prove authenticated remote checkout, real cache upload or
restore, TLS trust, Git LFS, registration, game CI or web-gallery CI.

Each cleanup command has a 30-second limit. Cleanup captures exact container IDs,
volume names and the test-network ID from the fresh private engine, writes them
to three JSON files and removes only those captured resources. It stops the
private API process (five-second graceful stop then kill). No shared prune or
production commands. Imported images, fixture source and `private.log` remain
in the disposable private directory for diagnosis; no recursive deletion is
part of this packet. On interruption/failure stop and report the directory and
JSON results; do not rerun or operate on any shared engine. A forced outer kill
may leave private resources requiring separately reviewed cleanup.

Safe return schema: `packet.directory`; `staging` boolean fields `actual_copy`,
`script`, `docker_share`, `post` and `result`; `cleanup.result` and
`retained_private_images`. Missing staging record, nonzero exit or cleanup failure
is a failure. Retain logs locally; do not post raw logs/environments/configs.
The repaired offline packet completed staging and cleanup successfully after the
owner authorized autonomous investigation/remediation. That result covers the
synthetic lifecycle only; live CI and deployment remain pending.

## Packet 2: runner-account local import

Recommendation: import the retained archive into the existing rootless store of
`forgejo-runner` (HOME `/home/forgejo-runner`, UID1001 runtime `/run/user/1001`).
No registry, login, mutable tag, new service or extra pull flag is needed.

Read-only launcher evidence: installed Quadlet's dry-run generator preserves
`Image=sha256:7e048...` exactly in `podman run`; no `--pull` is generated by the
current template. Podman v5.8.7 `pkg/systemd/quadlet/quadlet.go:handleImageSource`
only rewrites `.image`/`.build` inputs. Its vendored
`go.podman.io/common/libimage/pull.go` handles full `sha256:` IDs by local lookup;
missing IDs fail, and `--pull=always` rejects an ID. Therefore default launch
cannot fall back to a mutable name or download this local identity. Keep
`AutoUpdate=disabled` and the current template's pull behavior.

After approval, the owner runs this finite transfer/check as one subshell:

```sh
(
  set -eu
  cd /tmp
  sudo -v
  archive=/tmp/h85-delivery/candidate.oci.tar
  candidate=sha256:7e048ab852dac206966554c2d347addb9d31001ea35481c8c498db5b4abaa734
  original=data.forgejo.org/forgejo/runner:13@sha256:7fb853bfe73c229be6349398359c0a7bd01fadfd17c106607b2221150b799ed2
  echo '59bdbabe360a58e73ae003f8f1b50780b3c45953aa362ba937ee9fcce9a77f99  /tmp/h85-delivery/candidate.oci.tar' | sha256sum --check --status
  runner_podman() {
    timeout -k 5s 300s sudo -n -u forgejo-runner \
      env -i PATH=/usr/bin:/bin HOME=/home/forgejo-runner \
      XDG_RUNTIME_DIR=/run/user/1001 podman --remote=false "$@"
  }
  # Fail before import if normal recovery image or archive access is missing.
  runner_podman image exists "$original"
  timeout -k 2s 15s sudo -n -u forgejo-runner test -r "$archive"
  runner_podman load -i "$archive" >/dev/null
  actual=$(runner_podman image inspect --format '{{.Id}}' "$candidate")
  test "${actual#sha256:}" = "${candidate#sha256:}"
  platform=$(runner_podman image inspect --format '{{.Os}}/{{.Architecture}}' "$candidate")
  test "$platform" = linux/amd64
  runner_podman image exists "$original"
  printf '{"import":"pass","config_id_equal":true,"platform":"linux/amd64","original_available":true}\n'
)
```

The archive is public image content, already mode0644; access is checked without
widening directory permissions. Import mutates this account's image store only;
it does not activate the candidate or remove the original. Archive hash plus
local full config ID/platform equality binds the transfer to retained evidence.
No imported-manifest equality is assumed if storage changes representation.
Return only the final JSON and exit status. Failure means stop; no automatic
pull, permission alteration, inventory update or restart.

## Finish PR86 after these approved operations pass

Set `forgejo_runner_image` in `inventory/group_vars/forgejo_runner_hosts.yml` to
the full local candidate ID above, then render/check and request complete direct
review of that expanded head. Staging/cleanup and owner-run import now passed; this inventory pin is included
for final exact-head review, not activation. Import returned config-ID equality,
linux/amd64 and original-image availability. Keep Node pin, ordinary/disabled policy behavior and the
owner's currently enabled trust policy. Any future host using this local pin
must import the same bound archive before deployment; fresh-host availability
is not supplied by a registry.

After expanded review and owner deployment approval, the owner applies that
reviewed checkout using their usual `homelab-deploy` command. Import alone and
source merge alone do not deploy. Owner verifies the running image ID, then
separately approved Monster Raiders checkout/LFS/full CI and representative
web-gallery CI provide live acceptance. Do not close #85/#80 before that evidence.

Recovery keeps today's enabled trust policy and switches only the daemon image
back to the original public digest. After recovery approval, from the same
reviewed checkout use the normal playbook with this explicit image override:

```sh
ansible-playbook playbooks/site.yml --ask-become-pass --vault-password-file .vault-pass \
  -e 'forgejo_runner_image=data.forgejo.org/forgejo/runner:13@sha256:7fb853bfe73c229be6349398359c0a7bd01fadfd17c106607b2221150b799ed2'
```

This can restart services as a normal full playbook does; only the owner executes
it. Original-image availability is checked before import and again before any
cutover. This is a proposed recovery command, not evidence recovery was executed.
