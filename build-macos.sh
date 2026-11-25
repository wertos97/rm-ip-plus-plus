#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv-macos"
APP="$ROOT/dist/RM IP++.app"

"$PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"

"$PY" -m pip install --disable-pip-version-check -r requirements-dev.txt
"$PY" -m ruff check .
"$PY" -m ruff format --check .
QT_QPA_PLATFORM=offscreen "$PY" -m pytest
QT_QPA_PLATFORM=offscreen "$PY" tools/make_icns.py

VER="$("$PY" -c 'from src.version import __version__; print(__version__)')"

"$PY" -m PyInstaller \
    --noconfirm \
    --clean \
    --onedir \
    --windowed \
    --name "RM IP++" \
    --paths "src" \
    --icon "assets/icon.icns" \
    --add-data "assets/icon.icns:assets" \
    --add-data "assets/icon.svg:assets" \
    --osx-bundle-identifier "com.wertos97.rmipplusplus" \
    --distpath "dist" \
    main.py

VER="$VER" "$PY" - <<'PY'
import os
import plistlib

path = "dist/RM IP++.app/Contents/Info.plist"
with open(path, "rb") as file:
    info = plistlib.load(file)
info["LSMinimumSystemVersion"] = "13.0"
info["CFBundleShortVersionString"] = os.environ["VER"]
info["CFBundleVersion"] = os.environ["VER"]
with open(path, "wb") as file:
    plistlib.dump(info, file)
PY

codesign --force --deep --sign - "$APP"
codesign --verify --verbose "$APP"

mkdir -p dist/macos
ZIP="$ROOT/dist/macos/RMIPpp_${VER}_macos_arm64.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP"

echo "Done: $ZIP"
