#!/bin/sh
# One-shot, network-disabled material generation; no database or engine startup.
set -eu
umask 077
fail() { printf '%s\n' "hatchet-initialize: $1 failed" >&2; exit 1; }
[ "$#" = 2 ] || fail arguments
case "$1:$2" in 0:0|0:1|1:0|1:1) ;; *) fail arguments ;; esac
[ "$(/hatchet-lite --version 2>/dev/null)" = v0.110.5 ] || fail version
if /hatchet-admin authdisabled >/dev/null 2>&1; then fail authentication-build; fi
if [ "$1" = 1 ]; then
    /hatchet-admin --config /bootstrap/generated quickstart --skip certs --skip seed \
        --generated-config-dir /bootstrap/generated --overwrite=false >/dev/null 2>&1 || fail keysets
fi
if [ "$2" = 1 ]; then
    openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
        -subj '/CN=Hatchet private CA' -addext 'basicConstraints=critical,CA:TRUE' \
        -addext 'keyUsage=critical,keyCertSign,cRLSign' \
        -keyout /bootstrap/ca.key -out /bootstrap/ca.crt >/dev/null 2>&1 || fail ca
    openssl req -new -newkey rsa:3072 -nodes -sha256 -subj '/CN=hatchet' \
        -keyout /bootstrap/server.key -out /bootstrap/server.csr >/dev/null 2>&1 || fail request
    cat > /bootstrap/server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:hatchet
EOF
    openssl x509 -req -in /bootstrap/server.csr -CA /bootstrap/ca.crt \
        -CAkey /bootstrap/ca.key -CAcreateserial -days 365 -sha256 \
        -extfile /bootstrap/server.ext -out /bootstrap/server.crt >/dev/null 2>&1 || fail certificate
fi
