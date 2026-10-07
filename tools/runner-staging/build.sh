#!/usr/bin/env bash
# Build a local amd64 candidate in new disposable storage. Never push or deploy.
set -euo pipefail
recipe=$(cd -- "$(dirname -- "$0")" && pwd)
out=${1:?Usage: build.sh NEW_ABSOLUTE_OUTPUT_DIRECTORY [VERIFIED_PACKAGE_DIRECTORY]}
reuse=${2:-}
[[ "$out" == /tmp/* && ! -e "$out" ]] || { echo 'Use a new directory under /tmp' >&2; exit 1; }
mkdir -p "$out/inputs/packages" "$out/candidate"
timeout -k 10s 180s git clone --branch v13.0.0 --depth 1 https://code.forgejo.org/forgejo/runner.git "$out/source"
test "$(git -C "$out/source" rev-parse HEAD)" = 1a633ad51320631293dfcac99755b13659efe784
test -z "$(git -C "$out/source" status --porcelain)"
git -C "$out/source" apply --check "$recipe/staging.patch"
git -C "$out/source" apply "$recipe/staging.patch"
git -C "$out/source" diff --exit-code -- go.mod go.sum
while read -r digest url; do
    file=${url##*/}
    if [[ -n "$reuse" ]]; then
        cp -- "$reuse/$file" "$out/inputs/packages/$file"
    else
        timeout -k 5s 30s curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' "$url" -o "$out/inputs/packages/$file"
    fi
    printf '%s  %s\n' "$digest" "$out/inputs/packages/$file" | sha256sum -c -
    printf '%s  %s\n' "$digest" "$file" >> "$out/inputs/packages.sha256"
done < "$recipe/packages.lock"
cp "$out/source/go.mod" "$out/source/go.sum" "$out/inputs/"
cp "$recipe/Containerfile.inputs" "$out/inputs/Containerfile"
engine=(podman --remote=false --root "$out/storage" --runroot "$out/runroot")
timeout -k 15s 1200s "${engine[@]}" build --platform linux/amd64 -t localhost/h85-inputs "$out/inputs"
run=("${engine[@]}" run --rm --network=none --cap-drop=all --security-opt=no-new-privileges --security-opt=label=disable --pids-limit=512 --cpus=4 --memory=4g -v "$out/source:/srv" localhost/h85-inputs)
timeout -k 15s 900s "${run[@]}" sh -ec 'go test -short -count=1 -timeout=180s ./act/container/docker ./act/runner'
timeout -k 15s 900s "${run[@]}" sh -ec 'go mod verify; make build RELEASE_VERSION=13.0.0; go version -m forgejo-runner; clang --version; ld.lld --version; gcc --version; git diff --exit-code -- go.mod go.sum'
file "$out/source/forgejo-runner"
readelf -h "$out/source/forgejo-runner" | grep -q 'Machine:.*Advanced Micro Devices X86-64'
readelf -l "$out/source/forgejo-runner" > "$out/elf-program-headers.txt"
! grep -q INTERP "$out/elf-program-headers.txt"
readelf -d "$out/source/forgejo-runner" > "$out/elf-dynamic.txt"
grep -q 'There is no dynamic section' "$out/elf-dynamic.txt"
cp "$out/source/forgejo-runner" "$out/candidate/"
cp "$recipe/Containerfile" "$out/candidate/"
timeout -k 15s 180s "${engine[@]}" build --no-cache --identity-label=false --network=none --platform linux/amd64 -t localhost/homelab-runner-staging:85 "$out/candidate"
"${engine[@]}" image inspect localhost/homelab-runner-staging:85 --format '{{.Id}}' > "$out/image-id.txt"
timeout -k 10s 180s "${engine[@]}" save --format oci-archive -o "$out/candidate.oci.tar" localhost/homelab-runner-staging:85
sha256sum "$recipe/staging.patch" "$recipe/packages.lock" "$recipe/Containerfile" "$recipe/Containerfile.inputs" "$recipe/build.sh" "$out/source/forgejo-runner" "$out/candidate.oci.tar" > "$out/provenance.sha256"
printf 'Candidate and provenance retained at %s; no publication or activation performed.\n' "$out"
