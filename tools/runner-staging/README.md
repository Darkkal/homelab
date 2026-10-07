# Runner 13 Linux action staging correction

Runner 13 uploads remote-action archives at the container root with members under
`var/run/act`. Podman 5.8.7 rejects that path through the job image's absolute
`/var/run -> /run` symlink. The patch changes only the Linux extension's root/act
pair to `/run` and `/run/act`. It does not relax archive confinement.

This source/build delivery is Part of #85; merging it does not close that issue.
#82 is completed history. This recipe does not deploy, push,
change runner inventory, alter game workflows, or establish successful real LFS.
The live image, registration, trust policy and pinned Node job image stay outside
this recipe. Pending delivery, publication, staging and runtime acceptance require #85's
separate release; source merge does not authorise those operations.

## Build

Prerequisites already available on the build host: Bash, Git, curl, sha256sum,
GNU timeout, rootless Podman, file and readelf. No host package installation.

```sh
bash tools/runner-staging/build.sh /tmp/runner-85-candidate
# Or reuse the retained packages; all hashes/signatures are checked again:
bash tools/runner-staging/build.sh /tmp/runner-85-candidate /tmp/h85-package-binding/packages
```

Choose one command and a new output directory. The recipe uses separate Podman
storage there. Package fetches have 30-second limits; source fetch180s, input
acquisition1200s (module fetch600s), each test/build900s, candidate/export180s.
Timeouts fail closed and preserve disposable artifacts for inspection. They do
not prune shared resources. A timeout may leave a build container in this
isolated storage; inspect it there before removing only that owned resource.

Source is verified at `1a633ad51320631293dfcac99755b13659efe784` before applying
`staging.patch`. Builder/helper/base digest pins are in the Containerfiles. The
48-package lock records exact official URLs and SHA256s; normal builder APK keys
verify signatures before offline installation. Missing/changed inputs fail.
The recipe cannot silently select newer packages or another Go toolchain.

Module acquisition uses unchanged upstream go.mod/go.sum, then `go mod verify`.
Tests and compilation run with no network, production sockets, service binds,
registration or secrets; only the disposable source directory is mounted.
The compiler is Go1.25.14 with CGO enabled, linux/amd64/GOAMD64=v1, and upstream
netgo/osusergo/static/version flags. Build metadata truthfully records modified
source. This is repeatable pinned-input construction, not proven bit-identical
output or a recreation of upstream's Go1.25.12 binary.

## Contract tests and evidence

| Contract | Executable coverage |
| --- | --- |
| Root/act consistency, `/tmp`, Docker-action support | `TestStagingCopyDirUsesConfinedRunPaths` |
| Actual checkout/cache CopyDir tar headers and confined parent lookup | Same test, real tar collector and disposable absolute-symlink fixture |
| Internal action volume, work mount, host cache, unchanged socket/trust allowlist | `TestStagingMountAndRemoteActionPaths` |
| Script/environment command files, local/remote pre/post, Docker action paths | Updated existing StepRun, StepActionRemote/Local, StepDocker and Action tests |
| Daemon job/service input construction and valid volume admission | Existing `TestRunContext_PrepareJobContainer`, with its endpoint fixture made daemon-free |

Both package suites run with `-short -count=1`; upstream integration tests needing
a real Docker daemon are not claimed. The new tests fail on the original paths.
Negative confined-root cases remain rejected; Podman/copier code is unchanged.
Non-Linux backends and all production files except the two Linux returns remain
unchanged in the upstream patch.

Output includes source/binary, local candidate OCI archive/image ID, ELF reports
and SHA256 provenance. Before accepting a build, inspect its Go metadata and ELF
for the target/static linkage. Compare final OCI config against the pinned base
(entrypoint, CMD, user, working directory, environment, volumes) and require all
original layers plus one layer containing only root:root0755 runner binary and
its parent directory metadata. Candidate runtime is deliberately not executed.

## Deployment readiness

[Staging and local delivery packets](OPERATIONS.md) bind the retained candidate,
finite isolated test, local Podman identity and owner-run import commands.
They require separate execution approval; preparation does not deploy.
