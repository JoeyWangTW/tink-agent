#!/bin/bash
# Stop TinkAgent and remove its LaunchAgent (no more auto-start at login).
# Usage: packaging/uninstall.sh
set -euo pipefail

REPO="${TINK_AGENT_REPO:-$(cd "$(dirname "$0")/.." && pwd -P)}"
PY="${TINK_AGENT_PYTHON:-$REPO/.venv/bin/python}"

PYTHONPATH="$REPO" "$PY" - <<'PYEOF'
from tink_agent import launchagent
launchagent.uninstall()
print(f"stopped + removed LaunchAgent: {launchagent.PLIST_PATH}")
PYEOF
