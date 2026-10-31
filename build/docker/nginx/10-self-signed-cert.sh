#!/bin/sh
# Creates a self-signed certificate on the first start if none is in the certs volume.
# To use your own, put server.crt (full chain) and server.key in data/certs and restart.
set -e
CERTS=/etc/nginx/certs
[ -s "$CERTS/server.crt" ] && [ -s "$CERTS/server.key" ] && exit 0
mkdir -p "$CERTS"
SAN="DNS:localhost,IP:127.0.0.1"
[ -n "$TLS_SUBJECT_ALT_NAMES" ] && SAN="$TLS_SUBJECT_ALT_NAMES,$SAN"
CN="$(echo "$SAN" | cut -d, -f1 | cut -d: -f2)"
echo "No certificate in $CERTS: creating a self-signed one for $SAN (valid 825 days)"
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 -subj "/CN=$CN/O=IDP" \
  -addext "subjectAltName=$SAN" -keyout "$CERTS/server.key" -out "$CERTS/server.crt" 2>/dev/null
chmod 600 "$CERTS/server.key"
