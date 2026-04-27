#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$APP_DIR/deploy/dist"
DEPLOY_DIR="$APP_DIR/deploy"
MAC_DEPLOY_DIR="$DEPLOY_DIR/mac"
WINDOWS_DEPLOY_DIR="$DEPLOY_DIR/windows"
WORK_DIR="$DIST_DIR/UntappdBeerHistory"
MAC_APP_DIR="$WORK_DIR/Untappd Beer History.app"
MAC_CONTENTS_DIR="$MAC_APP_DIR/Contents"
MAC_RESOURCES_ROOT="$MAC_CONTENTS_DIR/Resources"
MAC_RESOURCES_DIR="$MAC_CONTENTS_DIR/Resources/app"
MACOS_DIR="$MAC_CONTENTS_DIR/MacOS"
WINDOWS_DIR="$WORK_DIR/Windows"
ZIP_PATH="$DIST_DIR/UntappdBeerHistory-desktop.zip"

rm -rf "$WORK_DIR"
mkdir -p "$DIST_DIR"
mkdir -p "$MAC_RESOURCES_DIR" "$MACOS_DIR" "$WINDOWS_DIR" "$WORK_DIR/data"

cp -R "$APP_DIR/documentation" "$WORK_DIR/"
cp -R "$APP_DIR/src" "$WORK_DIR/"
cp "$MAC_DEPLOY_DIR/start_desktop_app.command" "$WORK_DIR/"
cp "$APP_DIR/.gitignore" "$WORK_DIR/"

cp -R "$APP_DIR/documentation" "$WINDOWS_DIR/"
cp "$WINDOWS_DEPLOY_DIR/start_desktop_app.bat" "$WINDOWS_DIR/"
cp "$APP_DIR/.gitignore" "$WINDOWS_DIR/"

cp -R "$APP_DIR/documentation" "$MAC_RESOURCES_DIR/"
cp -R "$APP_DIR/src" "$MAC_RESOURCES_DIR/"
mkdir -p "$MAC_RESOURCES_DIR/data"
cp "$APP_DIR/.gitignore" "$MAC_RESOURCES_DIR/"
cp "$MAC_DEPLOY_DIR/Info.plist" "$MAC_CONTENTS_DIR/Info.plist"
cp "$MAC_DEPLOY_DIR/UntappdBeerHistory" "$MACOS_DIR/UntappdBeerHistory"
if [ -f "$MAC_DEPLOY_DIR/AppIcon.icns" ]; then
  cp "$MAC_DEPLOY_DIR/AppIcon.icns" "$MAC_RESOURCES_ROOT/AppIcon.icns"
fi

chmod +x "$WORK_DIR/start_desktop_app.command"
chmod +x "$MACOS_DIR/UntappdBeerHistory"

rm -f "$ZIP_PATH"
cd "$DIST_DIR"
zip -rq "$(basename "$ZIP_PATH")" "$(basename "$WORK_DIR")"

echo "Created shareable desktop bundle:"
echo "  $ZIP_PATH"
