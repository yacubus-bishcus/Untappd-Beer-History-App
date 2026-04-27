#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$APP_DIR"
PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/"

prompt_open_python_download() {
  echo
  read -r -p "Open the official Python download page now? [Y/n] " response
  case "$response" in
    [nN][oO]|[nN]) return 1 ;;
    *) open "$PYTHON_DOWNLOAD_URL"; return 0 ;;
  esac
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9+ is required, but python3 was not found on this Mac."
  echo "Please install the official Python 3.12 release from python.org."
  prompt_open_python_download || true
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
then
  echo "Python 3.9+ is required, but the detected python3 is too old."
  python3 --version || true
  echo "Please install Python 3.12 from python.org."
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
else
  echo "PyObjC/Cocoa is not available in this Python build."
  echo "Please install the official Python 3.12 release from python.org and rerun the launcher."
  prompt_open_python_download || true
  echo
  echo "Falling back to the browser-based Streamlit app..."
  exec python run.py streamlit
fi
