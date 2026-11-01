#!/usr/bin/env bash
# Hem .deb hem de AppImage paketini üretir.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"

"$ROOT/packaging/build_deb.sh"
"$ROOT/packaging/build_appimage.sh"

echo "Paket özetleri yazılıyor…"
rm -f "$DIST/SHA256SUMS"
(
    cd "$DIST"
    sha256sum idm-studio_*.deb IDM-Studio-*-x86_64.AppImage > SHA256SUMS
    cat SHA256SUMS
)
echo "Hazır: $DIST"
