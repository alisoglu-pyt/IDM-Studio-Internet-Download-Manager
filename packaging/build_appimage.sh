#!/usr/bin/env bash
# IDM Studio için taşınabilir bir x86_64 AppImage üretir.
#
# Derleme ortamı: Debian/Ubuntu, Python 3.10+.
# Sistemde Tkinter ve PyInstaller varsa doğrudan kullanılır. Yoksa, root
# gerektirmeyen bir yerel derleme araç zinciri .build/ altına indirilir.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' idm_studio/__init__.py | head -n1)"
if [[ -z "$VERSION" ]]; then
    echo "Hata: sürüm bilgisi okunamadı." >&2
    exit 1
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Hata: $PYTHON bulunamadı." >&2
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "x86_64" ]]; then
    echo "Hata: Bu betik yalnızca x86_64 için AppImage üretir (bulunan: $ARCH)." >&2
    exit 1
fi

BUILD_ROOT="$ROOT/.build/appimage"
TOOLCHAIN="$BUILD_ROOT/toolchain"
PYI_DIST="$BUILD_ROOT/pyinstaller/dist"
PYI_WORK="$BUILD_ROOT/pyinstaller/work"
APPDIR="$BUILD_ROOT/AppDir"
DIST="$ROOT/dist"
OUT="$DIST/IDM-Studio-${VERSION}-x86_64.AppImage"
APPIMAGETOOL="${APPIMAGETOOL:-}"

mkdir -p "$DIST" "$BUILD_ROOT" "$TOOLCHAIN"

# --------------------------------------------------------------- derleme aracı
EXTRA_ENV=()
MISSING_TK=0
MISSING_PYI=0

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    MISSING_TK=1
fi
if ! "$PYTHON" -c 'import PyInstaller' >/dev/null 2>&1; then
    MISSING_PYI=1
fi

if (( MISSING_TK || MISSING_PYI )); then
    if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-deb >/dev/null 2>&1; then
        cat >&2 <<'MSG'
Hata: Tkinter veya PyInstaller eksik ve yerel araç zinciri yalnızca
Debian/Ubuntu sistemlerde otomatik hazırlanabiliyor.

Şunları kurup yeniden deneyin:
  sudo apt install python3-tk pyinstaller
MSG
        exit 1
    fi

    PY_VER="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PACKAGES=()
    if (( MISSING_TK )); then
        PACKAGES+=("python3-tk" "python${PY_VER}-tk" "tk8.6" "libtk8.6" "tcl8.6" "libtcl8.6")
    fi
    if (( MISSING_PYI )); then
        PACKAGES+=("python3-pyinstaller" "pyinstaller" "python3-altgraph" "python3-setuptools" "python3-importlib-metadata")
    fi

    if (( MISSING_TK || MISSING_PYI )); then
        TOOL_DEBS="$TOOLCHAIN/debs"
        TOOL_ROOT="$TOOLCHAIN/root"
        PACKAGE_KEY="$(printf '%s\n' "${PACKAGES[@]}" | sha256sum | cut -c1-12)"
        MARKER="$TOOL_ROOT/.idm-studio-toolchain-$PACKAGE_KEY"
        if [[ ! -f "$MARKER" ]]; then
            echo "Yerel Tkinter/PyInstaller araç zinciri hazırlanıyor…"
            rm -rf "$TOOL_ROOT" "$TOOL_DEBS"
            mkdir -p "$TOOL_DEBS" "$TOOL_ROOT"
            subshell_status=0
            (
                cd "$TOOL_DEBS"
                apt-get download "${PACKAGES[@]}"
            ) || subshell_status=$?
            if (( subshell_status != 0 )); then
                echo "Hata: Derleme bağımlılıkları indirilemedi." >&2
                echo "İpucu: 'sudo apt update && sudo apt install python3-tk pyinstaller' deneyin." >&2
                exit 1
            fi
            for package in "$TOOL_DEBS"/*.deb; do
                dpkg-deb -x "$package" "$TOOL_ROOT"
            done
            touch "$MARKER"
        fi

        PY_DIST="$(find "$TOOL_ROOT/usr/lib" -maxdepth 2 -type d -path '*/python3/dist-packages' -print -quit 2>/dev/null || true)"
        TK_PY_DIR="$(find "$TOOL_ROOT/usr/lib" -maxdepth 2 -type d -name "python${PY_VER}" -print -quit 2>/dev/null || true)"
        TK_DYNLOAD=""
        if [[ -n "$TK_PY_DIR" && -d "$TK_PY_DIR/lib-dynload" ]]; then
            TK_DYNLOAD="$TK_PY_DIR/lib-dynload"
        fi
        MULTIARCH="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || true)"
        if [[ -z "$MULTIARCH" ]]; then
            MULTIARCH="$(uname -m)-linux-gnu"
        fi
        TK_LIBS="$TOOL_ROOT/usr/lib/$MULTIARCH"
        TCL_DATA="$TOOL_ROOT/usr/share/tcltk/tcl8.6"
        TK_DATA="$TOOL_ROOT/usr/share/tcltk/tk8.6"

        BOOTSTRAP_PATH=""
        if (( MISSING_PYI )) && [[ -n "$PY_DIST" ]]; then
            BOOTSTRAP_PATH="$PY_DIST"
        fi
        if (( MISSING_TK )) && [[ -n "$TK_PY_DIR" ]]; then
            BOOTSTRAP_PATH="${BOOTSTRAP_PATH:+$BOOTSTRAP_PATH:}$TK_PY_DIR"
            if [[ -n "$TK_DYNLOAD" ]]; then
                BOOTSTRAP_PATH="$BOOTSTRAP_PATH:$TK_DYNLOAD"
            fi
            EXTRA_ENV+=("LD_LIBRARY_PATH=${TK_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}")
            EXTRA_ENV+=("TCL_LIBRARY=$TCL_DATA")
            EXTRA_ENV+=("TK_LIBRARY=$TK_DATA")
        fi
        if [[ -n "$BOOTSTRAP_PATH" ]]; then
            EXTRA_ENV+=("PYTHONPATH=${BOOTSTRAP_PATH}${PYTHONPATH:+:$PYTHONPATH}")
        fi

        # Yerel araç zincirinin gerçekten kullanılabilir olduğunu doğrula.
        if ! env "${EXTRA_ENV[@]}" "$PYTHON" -c 'import tkinter, PyInstaller' >/dev/null 2>&1; then
            echo "Hata: Yerel Tkinter/PyInstaller araç zinciri doğrulanamadı." >&2
            echo "İpucu: 'sudo apt install python3-tk pyinstaller' ile sistem kurulumunu deneyin." >&2
            exit 1
        fi
    fi
fi

if ! env "${EXTRA_ENV[@]}" "$PYTHON" -c 'import tkinter, PyInstaller' >/dev/null 2>&1; then
    echo "Hata: Tkinter veya PyInstaller kullanılamıyor." >&2
    exit 1
fi

# ---------------------------------------------------------------- PyInstaller
echo "PyInstaller paketi oluşturuluyor…"
rm -rf "$PYI_DIST" "$PYI_WORK" "$BUILD_ROOT/spec"
mkdir -p "$PYI_DIST" "$PYI_WORK" "$BUILD_ROOT/spec"

PYI_EXTRA_ARGS=()
if env "${EXTRA_ENV[@]}" "$PYTHON" -c 'import yt_dlp' >/dev/null 2>&1; then
    PYI_EXTRA_ARGS+=(--collect-all yt_dlp)
    echo "yt-dlp bulundu; video platformu desteği paketlenecek."
fi
if env "${EXTRA_ENV[@]}" "$PYTHON" -c 'import pystray' >/dev/null 2>&1; then
    PYI_EXTRA_ARGS+=(--collect-all pystray)
    echo "pystray bulundu; Linux/macOS tepsi desteği paketlenecek."
fi

env "${EXTRA_ENV[@]}" "$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --log-level WARN \
    --windowed \
    --onedir \
    --name idm-studio \
    --distpath "$PYI_DIST" \
    --workpath "$PYI_WORK" \
    --specpath "$BUILD_ROOT/spec" \
    --paths "$ROOT" \
    --collect-submodules idm_studio \
    "${PYI_EXTRA_ARGS[@]}" \
    "$ROOT/main.py"

if [[ ! -x "$PYI_DIST/idm-studio/idm-studio" ]]; then
    echo "Hata: PyInstaller çıktısı bulunamadı." >&2
    exit 1
fi

# ------------------------------------------------------------------- AppDir
echo "AppDir oluşturuluyor…"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "$PYI_DIST/idm-studio" "$APPDIR/usr/lib/idm-studio"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/usr/lib/idm-studio/idm-studio" "$@"
APPRUN
chmod 0755 "$APPDIR/AppRun"

install -m 0644 "$ROOT/packaging/idm-studio.desktop" "$APPDIR/idm-studio.desktop"
install -m 0644 "$ROOT/packaging/idm-studio-256.png" "$APPDIR/idm-studio.png"
install -m 0644 "$ROOT/packaging/idm-studio-256.png" "$APPDIR/.DirIcon"

# ----------------------------------------------------------------- appimagetool
if [[ -z "$APPIMAGETOOL" ]]; then
    if command -v appimagetool >/dev/null 2>&1; then
        APPIMAGETOOL="$(command -v appimagetool)"
    else
        APPIMAGETOOL="$BUILD_ROOT/appimagetool-x86_64.AppImage"
        if [[ ! -x "$APPIMAGETOOL" ]]; then
            echo "appimagetool indiriliyor…"
            mkdir -p "$(dirname "$APPIMAGETOOL")"
            if command -v curl >/dev/null 2>&1; then
                curl -L --fail --retry 3 \
                    -o "$APPIMAGETOOL" \
                    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
            elif command -v wget >/dev/null 2>&1; then
                wget -O "$APPIMAGETOOL" \
                    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
            else
                echo "Hata: appimagetool indirmek için curl veya wget gerekir." >&2
                exit 1
            fi
            chmod 0755 "$APPIMAGETOOL"
        fi
    fi
fi

if [[ ! -x "$APPIMAGETOOL" ]]; then
    echo "Hata: appimagetool çalıştırılabilir değil: $APPIMAGETOOL" >&2
    exit 1
fi

# ------------------------------------------------------------------- AppImage
echo "AppImage paketleniyor…"
rm -f "$OUT"
# FUSE bulunmayan derleme makinelerinde de çalışabilmesi için çıkararak çalıştır.
APPIMAGE_EXTRACT_AND_RUN="${APPIMAGE_EXTRACT_AND_RUN:-1}" \
ARCH=x86_64 \
    "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUT"

chmod 0755 "$OUT"
echo "Oluşturuldu: $OUT"
sha256sum "$OUT"
ls -lh "$OUT"
