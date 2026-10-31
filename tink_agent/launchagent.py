"""Manage the macOS LaunchAgent that runs TinkAgent in the GUI session.

A LaunchAgent is how a Python menu-bar app reliably gets an Aqua session (so its
status item draws) and auto-starts at login. A plain `.app` whose launcher execs
the framework Python does not join the GUI session, so its icon never appears.

Functions take an injectable `runner` (defaults to subprocess.run) for tests.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

LABEL = "io.github.tajchert.tinkagent"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_PATH = Path.home() / "Library" / "Logs" / "TinkAgent.log"


def program_arguments(python: str) -> list[str]:
    """Command launchd runs. `python` is either an interpreter (run the module) or
    the Tink Agent.app launcher executable, which already knows what to run."""
    if ".app/Contents/MacOS/" in python:
        return [python]
    return [python, "-u", "-m", "tink_agent"]


def plist_contents(python: str, repo: str) -> str:
    """LaunchAgent plist: run tink_agent (via the app or `python -m`) at login."""
    args = "\n".join(f"    <string>{a}</string>" for a in program_arguments(python))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>WorkingDirectory</key><string>{repo}</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{LOG_PATH}</string>
  <key>StandardErrorPath</key><string>{LOG_PATH}</string>
</dict>
</plist>
"""


def is_enabled(plist_path: Path = PLIST_PATH) -> bool:
    """Auto-start at login is on iff the plist file is present."""
    return Path(plist_path).exists()


def set_run_at_login(enabled: bool, python: str, repo: str,
                     plist_path: Path = PLIST_PATH) -> None:
    """Toggle login auto-start by writing/removing the plist file only.

    Deliberately does NOT bootstrap/bootout — toggling must not start a second
    instance or kill the currently-running one. It only governs the next login.
    """
    plist_path = Path(plist_path)
    if enabled:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(plist_contents(python, repo))
    elif plist_path.exists():
        plist_path.unlink()


def install_and_start(python: str, repo: str, plist_path: Path = PLIST_PATH,
                      runner=subprocess.run) -> None:
    """Write the plist and bootstrap it into the GUI domain (starts it now)."""
    set_run_at_login(True, python, repo, plist_path)
    uid = os.getuid()
    domain = f"gui/{uid}"
    runner(["launchctl", "bootout", domain, str(plist_path)],
           capture_output=True, text=True)
    runner(["launchctl", "bootstrap", domain, str(plist_path)],
           capture_output=True, text=True)


def uninstall(plist_path: Path = PLIST_PATH, runner=subprocess.run) -> None:
    """Stop the agent and remove auto-start."""
    uid = os.getuid()
    runner(["launchctl", "bootout", f"gui/{uid}", str(plist_path)],
           capture_output=True, text=True)
    set_run_at_login(False, "", "", plist_path)


def current_python() -> str:
    """What launchd should run: the app launcher when running inside
    Tink Agent.app (keeps its permissions identity), else this interpreter."""
    return os.environ.get("TINK_AGENT_APP_EXEC") or sys.executable


def repo_root() -> str:
    return str(Path(__file__).resolve().parent.parent)
