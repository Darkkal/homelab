#!/bin/sh
# Called through env -i by the Quadlet. Never source a credential file or print
# upstream startup diagnostics: parser/DB errors may contain protected values.
set -eu
umask 077
fail() { printf '%s\n' "hatchet: $1 failed" >&2; exit 1; }

for name in server.yaml database.yaml database-url master.key private-jwt.key public-jwt.key grpc.crt grpc.key grpc-ca.crt; do
    file="/config/$name"
    [ -f "$file" ] && [ ! -L "$file" ] && [ -s "$file" ] || fail configuration
    [ "$(stat -c %a "$file")" = 600 ] || fail permissions
    [ "$(stat -c %u "$file")" = "$(id -u)" ] || fail ownership
done

[ "$(/hatchet-lite --version 2>/dev/null)" = v0.110.5 ] || fail version
if /hatchet-admin authdisabled >/dev/null 2>&1; then
    fail authentication-build
fi
openssl verify -CAfile /config/grpc-ca.crt /config/grpc.crt >/dev/null 2>&1 || fail trust
openssl x509 -in /config/grpc.crt -noout -checkhost hatchet >/dev/null 2>&1 || fail tls-name
openssl x509 -in /config/grpc.crt -noout -checkend 0 >/dev/null 2>&1 || fail tls-expiry
openssl x509 -in /config/grpc.crt -pubkey -noout >/tmp/cert.pub 2>/dev/null || fail tls-certificate
openssl pkey -in /config/grpc.key -pubout -out /tmp/key.pub </dev/null 2>/dev/null || fail tls-key
cmp -s /tmp/cert.pub /tmp/key.pub || fail tls-key-pair
rm -f /tmp/cert.pub /tmp/key.pub

# The migration CLI only accepts DATABASE_URL, not the server config directory.
DATABASE_URL=$(cat /config/database-url)
export DATABASE_URL
/hatchet-migrate >/dev/null 2>&1 || fail migration
unset DATABASE_URL
# Native seed is create-if-missing; it does not overwrite existing passwords.
/hatchet-admin seed --config /config >/dev/null 2>&1 || fail bootstrap
export LITE_STATIC_ASSET_DIR=/static-assets LITE_FRONTEND_BASE_PATH=/
export LITE_FRONTEND_PORT=8081 LITE_RUNTIME_PORT=8888
# Native engine package initialization creates the meter before it reads YAML.
# These fixed values mirror the reviewed config; inherited environment was cleared.
export SERVER_OTEL_SERVICE_NAME=hatchet
export SERVER_OTEL_COLLECTOR_URL=uptrace-otelcol:4317
export SERVER_OTEL_INSECURE=true
printf '%s\n' 'hatchet: starting native server'
exec /hatchet-lite --config /config >/dev/null 2>&1
