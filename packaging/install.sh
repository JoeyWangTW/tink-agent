#!/bin/bash
# Install TinkAgent as a LaunchAgent: starts it now (menu-bar icon appears) and
# auto-starts it at every login. launchd runs it in the GUI/Aqua session, which
# a script-launched .app cannot reliably do.
#
# If Tink Agent.app has been built (packaging/build_app.sh), launchd runs the app
# so permissions belong to "Tink Agent"; otherwise it runs `python -m tink_agent`.
#
# Usage: packaging/install.sh
set -euo pipefail

REPO="${TINK_AGENT_REPO:-$(cd "$(dirname "$0")/.." && pwd -P)}"
PY="${TINK_AGENT_PYTHON:-$REPO/.venv/bin/python}"
APP_EXEC="${TINK_AGENT_APP_EXEC:-$HOME/Applications/Tink Agent.app/Contents/MacOS/TinkAgent}"
[ -x "$APP_EXEC" ] || APP_EXEC=""

if [ ! -x "$PY" ]; then
  echo "error: python not found at $PY — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# PYTHONPATH: stdin scripts import from the cwd, which may not be the repo.
TINK_AGENT_APP_EXEC="$APP_EXEC" PYTHONPATH="$REPO" "$PY" - "$REPO" <<'PYEOF'
import sys
from tink_agent import launchagent
repo = sys.argv[1]
launchagent.install_and_start(launchagent.current_python(), repo)
print(f"installed + started LaunchAgent: {launchagent.PLIST_PATH}")
print(f"logs: {launchagent.LOG_PATH}")
PYEOF

WHO="Python"; [ -n "$APP_EXEC" ] && WHO="Tink Agent"
echo "The Tink Agent menu-bar icon should now appear. Grant Microphone + Accessibility"
echo "to '$WHO' in System Settings > Privacy & Security if prompted."
