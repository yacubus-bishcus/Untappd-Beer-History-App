#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$APP_DIR/dist"
WORK_DIR="$DIST_DIR/UntappdBeerHistory"
MAC_APP_DIR="$WORK_DIR/Untappd Beer History.app"
MAC_CONTENTS_DIR="$MAC_APP_DIR/Contents"
MAC_RESOURCES_DIR="$MAC_CONTENTS_DIR/Resources/app"
MACOS_DIR="$MAC_CONTENTS_DIR/MacOS"
WINDOWS_DIR="$WORK_DIR/Windows"
ZIP_PATH="$DIST_DIR/UntappdBeerHistory-desktop.zip"

rm -rf "$WORK_DIR"
mkdir -p "$DIST_DIR"
mkdir -p "$MAC_RESOURCES_DIR" "$MACOS_DIR" "$WINDOWS_DIR"

cp "$APP_DIR/README.md" "$WORK_DIR/"
cp "$APP_DIR/QUICKSTART.md" "$WORK_DIR/"
cp "$APP_DIR/start_desktop_app.command" "$WORK_DIR/"

cp "$APP_DIR/README.md" "$WINDOWS_DIR/"
cp "$APP_DIR/QUICKSTART.md" "$WINDOWS_DIR/"
cp "$APP_DIR/start_desktop_app.bat" "$WINDOWS_DIR/"
cp "$APP_DIR/requirements.txt" "$WINDOWS_DIR/"
cp "$APP_DIR/run.py" "$WINDOWS_DIR/"
cp "$APP_DIR/app_config.py" "$WINDOWS_DIR/"
cp "$APP_DIR/desktop_launcher.py" "$WINDOWS_DIR/"
cp "$APP_DIR/streamlit_app.py" "$WINDOWS_DIR/"
cp "$APP_DIR/untapped.py" "$WINDOWS_DIR/"
cp "$APP_DIR/untapped_selenium.py" "$WINDOWS_DIR/"
cp "$APP_DIR/.gitignore" "$WINDOWS_DIR/"

cp "$APP_DIR/requirements.txt" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/run.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/app_config.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/desktop_launcher.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/streamlit_app.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/untapped.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/untapped_selenium.py" "$MAC_RESOURCES_DIR/"
cp "$APP_DIR/.gitignore" "$MAC_RESOURCES_DIR/"

cat > "$MAC_CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Untappd Beer History</string>
  <key>CFBundleExecutable</key>
  <string>UntappdBeerHistory</string>
  <key>CFBundleIdentifier</key>
  <string>com.local.untappdbeerhistory</string>
  <key>CFBundleName</key>
  <string>Untappd Beer History</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/UntappdBeerHistory" <<'SCRIPT'
#!/bin/bash
set -e

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$BUNDLE_DIR/Resources/app"
PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/"

prompt_open_python_download() {
  local button
  button="$(osascript <<'APPLESCRIPT'
button returned of (display dialog "Python 3.9 or newer is required to run Untappd Beer History. Open the official Python download page now?" buttons {"Cancel", "Open Download Page"} default button "Open Download Page")
APPLESCRIPT
)" || return 1
  if [ "$button" = "Open Download Page" ]; then
    open "$PYTHON_DOWNLOAD_URL"
  fi
}

cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  prompt_open_python_download || true
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
then
  prompt_open_python_download || true
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt >/dev/null

if python - <<'PY' >/dev/null 2>&1
import AppKit
PY
then
  exec python desktop_launcher.py
fi

button="$(osascript <<'APPLESCRIPT'
button returned of (display dialog "The installed Python build does not include the Cocoa bridge required for the native macOS launcher. Install the official Python release from python.org for the best experience." buttons {"Continue in Browser", "Open Download Page"} default button "Continue in Browser")
APPLESCRIPT
)" || exit 1

if [ "$button" = "Open Download Page" ]; then
  open "$PYTHON_DOWNLOAD_URL"
  exit 1
fi

if [ "$button" = "Continue in Browser" ]; then
  exec python run.py streamlit
fi
SCRIPT

chmod +x "$WORK_DIR/start_desktop_app.command"
chmod +x "$MACOS_DIR/UntappdBeerHistory"

rm -f "$ZIP_PATH"
cd "$DIST_DIR"
zip -rq "$(basename "$ZIP_PATH")" "$(basename "$WORK_DIR")"

echo "Created shareable desktop bundle:"
echo "  $ZIP_PATH"
