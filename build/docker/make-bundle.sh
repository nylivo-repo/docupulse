#!/usr/bin/env bash
# Builds the Docker images of IDP for a NAS or Linux server and packs them for an offline install:
#
#   build/docker/make-bundle.sh [platform]      platform: linux/amd64 (default; UGREEN, Synology Intel) | linux/arm64
#
# Result: ../IDP_dist/IDP-<version>-docker/ with docupulse-idp-images.tar.gz (both images),
# docker-compose.yml, .env.example and INSTALL.txt, plus a .zip of that folder. The NAS needs no internet.
source "$(dirname "$0")/../mac-linux/common.sh"

PLATFORM="${1:-linux/amd64}"
VERSION="$(cd "$BACKEND" && "$PY" -c 'from app.core.config import settings; print(settings.VERSION)' 2>/dev/null || echo dev)"
NAME="IDP-$VERSION-docker"
OUT_ROOT="$(dirname "$ROOT")/IDP_dist"
OUT="$OUT_ROOT/$NAME"
DOCKER="$ROOT/build/docker"

if node_ok; then
  echo "Building the web UI"
  (cd "$ROOT/frontend" && npm ci --silent && npm run build >/dev/null)
elif [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "frontend/dist is missing and Node.js 22/24 is not available to build it."; exit 1
fi

for part in api web; do
  echo "Building docupulse-idp-$part:$VERSION for $PLATFORM"
  docker buildx build --platform "$PLATFORM" --load -f "$DOCKER/Dockerfile.$part" \
    -t "docupulse-idp-$part:$VERSION" -t "docupulse-idp-$part:latest" "$ROOT"
done

rm -rf "$OUT" "$OUT_ROOT/$NAME.zip"
mkdir -p "$OUT"
echo "Saving the images"
docker save "docupulse-idp-api:$VERSION" "docupulse-idp-web:$VERSION" | gzip > "$OUT/docupulse-idp-images.tar.gz"
cp "$DOCKER/docker-compose.yml" "$OUT/"
sed "s/^IDP_VERSION=.*/IDP_VERSION=$VERSION/" "$DOCKER/.env.example" > "$OUT/.env.example"
cat > "$OUT/INSTALL.txt" <<NOTE
IDP $VERSION — Docker install ($PLATFORM)

1. Copy this folder to the NAS, e.g. /volume1/docker/docupulse-idp (any folder; data/ is created inside it).
2. In that folder:
     docker load -i docupulse-idp-images.tar.gz
     cp .env.example .env        (set PUID/PGID to the folder owner's ids, ports, TLS_SUBJECT_ALT_NAMES)
     docker compose up -d
   (UGOS Docker app: Project → Create, pick this folder; load the images first under Image → Import.)
3. Open https://<nas-address>:7443 and sign in as admin with the password in
     data/storage/initial_admin_password.txt   (you must change it; the file is then deleted)

Upgrade: load the new images, set IDP_VERSION in .env, docker compose up -d. data/ is kept.
Back up: the whole data/ folder (stop the containers first for a consistent SQLite copy).
Full guide: https://<nas-address>:7443/docs (admin), section 11.10 "Docker / NAS".
NOTE
(cd "$OUT_ROOT" && zip -qr "$NAME.zip" "$NAME")
echo "Done: $OUT ($(du -sh "$OUT" | cut -f1)) and $OUT_ROOT/$NAME.zip"
