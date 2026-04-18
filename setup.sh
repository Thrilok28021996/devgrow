#!/bin/bash
# DevGrow setup — builds self-contained .app bundle (venv lives inside the bundle)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="DevGrow"
APP_DIR="$HOME/Applications/${APP_NAME}.app"
CONTENTS="${APP_DIR}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"

echo "=== DevGrow Setup ==="
echo ""

# ── [1/6] System deps ──────────────────────────────────────────────────────
echo "[1/6] Checking system dependencies..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "  python3 not found."
    echo "  Install: brew install python3   or   https://python.org"
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  python3 ${PY_VER} OK"

# ── [2/6] Build .app skeleton ──────────────────────────────────────────────
echo ""
echo "[2/6] Building .app structure..."
rm -rf "${APP_DIR}"
mkdir -p "${MACOS}" "${RESOURCES}"
echo "  ${APP_DIR}"

# ── [3/6] Venv INSIDE the bundle ──────────────────────────────────────────
echo ""
echo "[3/6] Creating venv inside bundle..."
python3 -m venv "${RESOURCES}/venv"
"${RESOURCES}/venv/bin/pip" install --upgrade pip --quiet
echo "  ${RESOURCES}/venv"

# ── [4/6] Install packages ─────────────────────────────────────────────────
echo ""
echo "[4/6] Installing packages..."
"${RESOURCES}/venv/bin/pip" install "${SCRIPT_DIR}[desktop]" Pillow --quiet
echo "  devgrow + PySide6 + Pillow installed"

# Verify
"${RESOURCES}/venv/bin/python3" -c "import PySide6;    print('  PySide6 OK')"
"${RESOURCES}/venv/bin/python3" -c "import fastapi;    print('  fastapi OK')"
"${RESOURCES}/venv/bin/python3" -c "import devgrow.db; print('  devgrow OK')"

# ── [5/6] Icon ─────────────────────────────────────────────────────────────
echo ""
echo "[5/6] Generating icon..."

ICON_PNG="${SCRIPT_DIR}/devgrow/assets/icon.png"
"${RESOURCES}/venv/bin/python3" "${SCRIPT_DIR}/make_icon.py" "${ICON_PNG}"

ICONSET="${SCRIPT_DIR}/AppIcon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 64 128 256 512; do
    sips -z $size $size "$ICON_PNG" \
        --out "${ICONSET}/icon_${size}x${size}.png"     >/dev/null 2>&1
    double=$((size * 2))
    sips -z $double $double "$ICON_PNG" \
        --out "${ICONSET}/icon_${size}x${size}@2x.png"  >/dev/null 2>&1
done
iconutil -c icns "$ICONSET" -o "${RESOURCES}/AppIcon.icns"
rm -rf "$ICONSET"
echo "  AppIcon.icns ready"

# ── [6/6] Assemble bundle ──────────────────────────────────────────────────
echo ""
echo "[6/6] Assembling bundle..."

# Launcher — uses only relative paths, never references source dir
cat > "${MACOS}/run" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${DIR}/../Resources/venv"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec "${VENV}/bin/python3" -c "from devgrow.desktop import main; main()"
LAUNCHER
chmod +x "${MACOS}/run"

# Info.plist
cat > "${CONTENTS}/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>             <string>DevGrow</string>
    <key>CFBundleDisplayName</key>      <string>DevGrow</string>
    <key>CFBundleIdentifier</key>       <string>com.devgrow.app</string>
    <key>CFBundleVersion</key>          <string>0.2.0</string>
    <key>CFBundleShortVersionString</key><string>0.2.0</string>
    <key>CFBundleExecutable</key>       <string>run</string>
    <key>CFBundleIconFile</key>         <string>AppIcon</string>
    <key>CFBundlePackageType</key>      <string>APPL</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
    <key>NSHighResolutionCapable</key>  <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key><true/>
</dict>
</plist>
EOF

# Ad-hoc sign (free — removes "unverified developer" block on your own machine)
if command -v codesign >/dev/null 2>&1; then
    codesign --deep --force --sign - "${APP_DIR}" 2>/dev/null
    echo "  Ad-hoc signed"
else
    echo "  codesign not found, skipping"
fi

echo ""
echo "=== Done ==="
echo ""
echo "  Launch:  open '${APP_DIR}'"
echo "  Dock:    Finder → Cmd+Shift+G → ~/Applications → drag DevGrow to Dock"
echo ""
echo "  To rebuild:  bash setup.sh"
echo "  To uninstall: rm -rf '${APP_DIR}'"
