#!/bin/bash
# Build "Tink Agent.app": a native launcher that embeds this checkout's Python,
# so the app has its own name + icon in the Dock and in Privacy & Security.
#
# Usage: packaging/build_app.sh [DEST_DIR]      (default: ~/Applications)
# Requires: Xcode command line tools, and .venv set up per README.
set -euo pipefail

REPO="${TINK_AGENT_REPO:-$(cd "$(dirname "$0")/.." && pwd -P)}"
PY="${TINK_AGENT_PYTHON:-$REPO/.venv/bin/python}"
DEST="${1:-$HOME/Applications}"
APP="$DEST/Tink Agent.app"
BUNDLE_ID="io.github.tajchert.tinkagent"

if [ ! -x "$PY" ]; then
  echo "error: python not found at $PY — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
# python3.X-config next to the real (non-venv) interpreter gives the embed flags.
BASE_PY="$("$PY" -c 'import sys; print(sys._base_executable)')"
PYCONFIG="$(dirname "$(readlink -f "$BASE_PY")")/$(basename "$(readlink -f "$BASE_PY")")-config"
VERSION="$(cd "$REPO" && git describe --tags --always 2>/dev/null || echo 0.1.0)"

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "→ compiling launcher"
# shellcheck disable=SC2046
clang -O2 -o "$BUILD/TinkAgent" "$REPO/packaging/app/launcher.c" \
  $("$PYCONFIG" --cflags) $("$PYCONFIG" --ldflags --embed) \
  -Wl,-rpath,"$("$PY" -c 'import sysconfig; print(sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX"))')"

echo "→ rendering icon"
ICONSET="$BUILD/AppIcon.iconset"
mkdir -p "$ICONSET"
"$PY" "$REPO/packaging/app/make_app_icon.py" "$BUILD/icon.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$BUILD/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/AppIcon.icns"

echo "→ assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/TinkAgent" "$APP/Contents/MacOS/TinkAgent"
cp "$BUILD/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Tink Agent</string>
  <key>CFBundleDisplayName</key><string>Tink Agent</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleExecutable</key><string>TinkAgent</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Tink Agent listens to your mic for voice commands and button tones.</string>
  <key>TinkAgentRepo</key><string>$REPO</string>
  <key>TinkAgentPython</key><string>$PY</string>
</dict>
</plist>
PLIST

echo "→ signing (ad-hoc)"
codesign --force --sign - --identifier "$BUNDLE_ID" "$APP"

echo "built: $APP"
echo "Run packaging/install.sh to start it now and at every login."
