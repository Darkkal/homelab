# Runner action staging: #82 checkpoint

Part of #82. Game PR86 tasks646/647 failed before checkout while copying the
remote JavaScript action. LFS package installation completed. No successful
checkout, LFS transfer or certificate-use result follows from those attempts.
The supplied upstream issue29813 is unrelated and is withdrawn as evidence.
No game workflow change, host version change or platform workaround is proposed.

## Exact source trace

Official runner tag v13.0.0 resolves to
`1a633ad51320631293dfcac99755b13659efe784`, matching prior binary revision evidence.
- [action.go](https://code.forgejo.org/forgejo/runner/src/commit/1a633ad51320631293dfcac99755b13659efe784/act/runner/action.go):
  maybeCopyToActionDir passes the remote-action destination to JobContainer.CopyDir.
- [docker/run.go](https://code.forgejo.org/forgejo/runner/src/commit/1a633ad51320631293dfcac99755b13659efe784/act/container/docker/run.go):
  copyDir builds a tar using DstDir=dstPath[1:], then calls CopyToContainer with
  DestinationPath="/". Thus action destination components are in tar member names;
  changing checkout alone does not remove the cache actions' same staging path.
- The same file's sanitizeConfig matches parsed bind Source against ValidVolumes
  globs and discards unmatched binds. An exact bundle-path entry admits the mount
  without a wildcard. [exec.go](https://code.forgejo.org/forgejo/runner/src/commit/1a633ad51320631293dfcac99755b13659efe784/internal/app/cmd/exec.go)
  instead sets ValidVolumes=["**"]. The previous local-exec probe therefore could
  not test daemon-mode allowlist rejection.

Official Podman tag v5.8.7 resolves to
`c593b672bf3db1173aebea565ebf1a724ea196dc`.
- [compat archive handler](https://github.com/containers/podman/blob/c593b672bf3db1173aebea565ebf1a724ea196dc/pkg/api/handlers/compat/containers_archive.go)
  delegates archive upload to ContainerCopyFromArchive.
- [container_copy_common.go](https://github.com/containers/podman/blob/c593b672bf3db1173aebea565ebf1a724ea196dc/libpod/container_copy_common.go)
  resolves the copy destination, then uses the vendored Buildah copier.Put.
- [vendored copier.go](https://github.com/containers/podman/blob/c593b672bf3db1173aebea565ebf1a724ea196dc/vendor/github.com/containers/buildah/copier/copier.go)
  opens targetDirectory with os.OpenRoot (line1946) and tests cleaned tar member
  names with osRoot.Lstat (line2020), returning non-ENOENT errors before extraction.
  This is consistent with the observed statat/path-escape error. An absolute
  symlink encountered beneath the confined root is a hypothesis to test, not a
  confirmed property of the deployed job container.

## Daemon-mode mount evidence and limits

Before the correction, task646 explicitly rejected the public bundle Source.
After owner reapply, task647 omitted that warning. Exact-source sanitizer tracing
and the rendered-config regression cover the necessary admission input. The
reported daemon attempt provides mount-acceptance evidence; it does not prove
mounted bytes, client trust, credentials or LFS transfer. No new daemon run was
performed by this PR. Disabled render fingerprints remain unchanged.

For literal admission, runner13 pins gobwas/glob v0.2.3. Its
[compiler](https://github.com/gobwas/glob/blob/5ccd90ef52e1e632236f7326478d4faa74f99438/compiler/compiler.go)
compiles plain text nodes to match.NewText; its
[Text.Match](https://github.com/gobwas/glob/blob/5ccd90ef52e1e632236f7326478d4faa74f99438/match/text.go)
uses string equality. Rejecting all glob operators/escape characters in the
validated source path therefore retains literal matching, including spaces.
Controller regressions verify metacharacter rejection and rendered plain/spaced
source exclusion of sibling/backup/config/unrelated paths. The Go matcher was
source-reviewed, not executed here: no Go toolchain is installed and none was
installed for this correction.

## Completed owner-executed smallest reproduction

The owner executed the prepared stopped-container synthetic probe published in
[#82 comment7188](https://forgejo.home/piclaw-horde/homelab/issues/82#issuecomment-7188).
The cached pinned image received tar members through the compatible archive API
with path=/. The var/run/act/actions/33/synthetic/.eslintignore member returned
HTTP500/path_escape; the otherwise identical run/act/actions prefix returned
HTTP200/accepted. Captured-container cleanup passed. Results are owner-reported
in [7190](https://forgejo.home/piclaw-horde/homelab/issues/82#issuecomment-7190);
this PR does not independently rerun that host operation.

This establishes a path-specific failure for the synthetic case. It does not
prove a repaired real checkout/LFS or certificate-use result. Runner13 hard-codes
Linux GetRoot=/var/run and GetActPath=/var/run/act in
[extensions.go](https://code.forgejo.org/forgejo/runner/src/commit/1a633ad51320631293dfcac99755b13659efe784/act/container/docker/extensions.go).
No corresponding path configuration field was found. A patched runner, Podman
correction or image adjustment remains a separately scoped platform decision.
No workflow rewrite, platform fix, repeat host reproduction or CI retry is part
of this source correction.
