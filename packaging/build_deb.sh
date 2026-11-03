#!/usr/bin/env bash
# IDM Studio için mimariden bağımsız bir Debian (.deb) paketi üretir.
# Gereksinimler: dpkg-deb, coreutils, gzip, sed, awk.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' idm_studio/__init__.py | head -n1)"
if [[ -z "$VERSION" ]]; then
    echo "Hata: sürüm bilgisi okunamadı." >&2
    exit 1
fi

PKG="idm-studio"
ARCH="all"
BUILD_ROOT="$ROOT/.build/deb"
STAGE="$BUILD_ROOT/${PKG}_${VERSION}_${ARCH}"
DIST="$ROOT/dist"
OUT="$DIST/${PKG}_${VERSION}_${ARCH}.deb"

rm -rf "$STAGE"
mkdir -p \
    "$STAGE/DEBIAN" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/lib/$PKG" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$STAGE/usr/share/doc/$PKG" \
    "$DIST"

# Uygulama kaynakları
install -m 0644 "$ROOT/main.py" "$STAGE/usr/lib/$PKG/main.py"
install -m 0644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/README.md"
mkdir -p "$STAGE/usr/lib/$PKG/idm_studio"
for source in "$ROOT"/idm_studio/*.py; do
    install -m 0644 "$source" "$STAGE/usr/lib/$PKG/idm_studio/"
done

# Başlatıcı ve masaüstü bütünleşmesi
cat > "$STAGE/usr/bin/$PKG" <<'LAUNCHER'
#!/bin/sh
exec python3 /usr/lib/idm-studio/main.py "$@"
LAUNCHER
chmod 0755 "$STAGE/usr/bin/$PKG"

install -m 0644 "$ROOT/packaging/idm-studio.desktop" \
    "$STAGE/usr/share/applications/idm-studio.desktop"
install -m 0644 "$ROOT/packaging/idm-studio.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/idm-studio.svg"
install -m 0644 "$ROOT/packaging/idm-studio-256.png" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/idm-studio.png"

# Debian bakım betikleri
cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
POSTINST
cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
POSTRM
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

cat > "$STAGE/usr/share/doc/$PKG/copyright" <<'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: IDM Studio

Files: *
Copyright: 2026 IDM Studio contributors
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
COPYRIGHT

{
    printf '%s (%s) unstable; urgency=medium\n\n' "$PKG" "$VERSION"
    printf '  * Initial packaging of IDM Studio %s.\n\n' "$VERSION"
    printf ' -- IDM Studio Developers <idm-studio@example.invalid>  %s\n' \
        "$(date -R)"
} | gzip -9n > "$STAGE/usr/share/doc/$PKG/changelog.gz"

INSTALLED_SIZE="$(du -sk "$STAGE/usr" | awk '{print $1}')"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: IDM Studio Developers <idm-studio@example.invalid>
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.10), python3-tk, xdg-utils
Recommends: yt-dlp
Section: net
Priority: optional
Description: Material 3 internet download manager
 IDM Studio is a graphical download manager built with Python and Tkinter.
 It supports multi-segment HTTP/HTTPS, FTP/FTPS, HLS, and BitTorrent
 downloads, pause and resume, automatic retry, scheduled downloads,
 clipboard link capture, and a system tray. The interface has light and
 dark Material 3 themes and is available in 16 languages.
 .
 Video-platform support uses the optional yt-dlp package. The application
 keeps its download list in ~/.config/idm-studio and resumes unfinished and
 scheduled downloads after a restart.
CONTROL

(
    cd "$STAGE"
    find usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums
)

rm -f "$OUT"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(date +%s)}" \
    dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null

echo "Oluşturuldu: $OUT"
dpkg-deb --info "$OUT"
