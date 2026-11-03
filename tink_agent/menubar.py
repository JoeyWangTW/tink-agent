from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import time
import rumps
from .config import Config, DEFAULT_PATH
from .audio import AudioCapture, DeviceNotFound, reinitialize as audio_reinitialize
from .detector import ToneDetector, VoiceGate
from .transcribe import Transcriber, make_transcriber, resolve_stt
from .actions import ActionRouter
from .engine import Engine
from .activity_log import ActivityLogger, DEFAULT_LOG
from . import launchagent

_REPO = Path(__file__).resolve().parent.parent
_ASSETS = _REPO / "assets"
ICON_IDLE = str(_ASSETS / "tink_icon.png")
ICON_ACTIVE = str(_ASSETS / "tink_icon_active.png")


def _main_thread_dispatch(fn):
    """Schedule fn to run on the AppKit main thread/run loop. Keyboard actions
    fire from the audio callback and transcription worker threads, but pynput's
    macOS layout query (HIToolbox TSM) must run on the main thread or the
    process traps. callAfter is thread-safe to call from any thread."""
    from PyObjCTools import AppHelper
    AppHelper.callAfter(fn)


class TinkAgentApp(rumps.App):
    def __init__(self):
        # No dropdown menu (and so no rumps Quit item): clicking the icon opens
        # the settings popover, which carries its own Quit link.
        super().__init__("Tink Agent", icon=ICON_IDLE, template=True,
                         quit_button=None)
        self.config = Config.load()
        self.engine = self._build_engine()
        self.capture = None
        self._settings = None  # settings panel, hosted in the status-item popover
        self._popover = None
        self._button_actions = None  # lazily-created Button Actions window

        # State stashed from background threads (atomic attribute writes); the
        # main-thread timer renders it, keeping all UI mutation on the main thread.
        self._last_heard = "—"
        self._last_action = "—"
        self._status = "stopped"
        self._icon_active = False

        # Verify-step plumbing: the audio thread stashes the last detected tone;
        # the onboarding window reads these (never touches the audio thread).
        self._last_tone_slot = None
        self._last_tone_at = 0.0
        self._onboarding = None       # lazily-created OnboardingController
        self._onboarding_shown = False

        # Start audio AFTER the run loop is up (opening the mic can block/prompt;
        # doing it in __init__ would delay run() and the status item appearing).
        self._autostart_done = False
        self._timer = rumps.Timer(self._tick, 0.2)
        self._timer.start()

    def _build_engine(self) -> Engine:
        c = self.config
        det = ToneDetector(c.tones, c.tone_rms_min, c.tone_dominance_min,
                           c.tone_debounce_ms, c.sample_rate,
                           tonality_min=c.tone_tonality_min)
        vg = VoiceGate(c.vad_rms_start, c.vad_rms_end, c.vad_hangover_ms,
                       c.min_utterance_ms, c.sample_rate, c.block_size,
                       c.max_utterance_ms, release_rms=c.vad_release_rms,
                       release_ms=c.vad_release_ms)
        tr = self._make_transcriber()
        router = ActionRouter(c.slot_actions, dispatch=_main_thread_dispatch,
                              output_mode=c.output_mode)
        self.activity_log = ActivityLogger(
            enabled=c.log_activity, path=(c.log_path or None))
        return Engine(c, det, vg, tr, router, on_event=self._on_event,
                      logger=self.activity_log)

    def _make_transcriber(self) -> Transcriber:
        return make_transcriber(self.config)

    @property
    def log_path(self):
        return self.config.log_path or DEFAULT_LOG

    # --- called from background threads: only stash state, never touch UI ---
    def _on_event(self, kind, payload):
        if kind == "transcript":
            self._last_heard = str(payload)[:40]
        elif kind == "tone":
            self._last_action = f"slot {payload}"
            self._last_tone_slot = payload
            self._last_tone_at = time.monotonic()
        elif kind == "blocked":
            self._last_action = f"blocked (wrong app): {payload}"
        elif kind == "error":
            self._status = f"error: {str(payload)[:34]}"

    def _on_audio_status(self, status):
        # Audio callback thread: PortAudio reported input overflow / a device
        # drop (which truncates speech). Only stash + write to the run log here;
        # never touch AppKit off the main thread.
        import sys
        print(f"[audio] stream status: {status}", file=sys.stderr, flush=True)
        self._status = f"audio glitch: {str(status)[:24]}"

    # --- main-thread rendering ---
    def _tick(self, _):
        if not self._autostart_done:
            self._autostart_done = True
            self._install_popover()
            _request_missing_permissions()
            if self.config.enabled:  # disabled = mic closed, even across restarts
                self.start_listening(None)
        if not self.config.onboarding_done and not self._onboarding_shown:
            self._onboarding_shown = True
            self.open_onboarding(None)
        capturing = self.capture is not None and self.engine.is_capturing
        if capturing != self._icon_active:
            self._icon_active = capturing
            self.icon = ICON_ACTIVE if capturing else ICON_IDLE
        if self.capture is not None and self.capture.is_running:
            self.engine.keep_warm(self.config.stt_keep_warm_s)
        if self._settings is not None and self.window_is_visible():
            self._settings.refresh()

    def status_text(self) -> str:
        listening = self.capture is not None and self.capture.is_running
        shown = "Listening" if listening else "Stopped"
        if self._status.startswith("error"):
            shown = self._status[len("error: "):].capitalize()
        if not self.engine.enabled:
            shown = "Disabled (mic off)"
        if self._icon_active:
            shown += " · capturing"
        return shown

    def window_is_visible(self) -> bool:
        try:
            return bool(self._popover.isShown())
        except Exception:  # noqa: BLE001
            return False

    # --- shared setters (called by both the menu and the Settings window) ---
    def set_enabled(self, value: bool):
        self.engine.enabled = bool(value)
        self.config.enabled = bool(value)
        self.config.save()
        # Close the input stream when disabled so macOS's mic-in-use indicator
        # goes away; reopen it when re-enabled.
        if value:
            self.start_listening(None)
        else:
            self.stop_listening(None)

    def set_listening(self, value: bool):
        if value:
            self.start_listening(None)
        else:
            self.stop_listening(None)

    def set_start_at_login(self, value: bool) -> bool:
        try:
            launchagent.set_run_at_login(
                bool(value), launchagent.current_python(), launchagent.repo_root())
        except Exception as e:  # noqa: BLE001
            rumps.alert("Could not update Start at login", str(e))
            return False
        self.config.start_at_login = bool(value)
        self.config.save()
        return True

    def toggle_target(self, identifier: str, on: bool):
        identifier = str(identifier or "").strip()
        if not identifier:
            return
        ids = [i for i in (self.config.target_apps or []) if i]
        if on and identifier not in ids:
            ids.append(identifier)
        elif not on:
            ids = [i for i in ids if i != identifier]
        self.config.target_apps = ids
        self.config.save()

    def set_stt_backend(self, name: str):
        # When switching to custom, seed the editable command from whatever was
        # effective so the user starts from a working template.
        if name == "custom" and not self.config.stt_command:
            cmd, mode = resolve_stt(self.config)
            self.config.stt_command = cmd
            self.config.stt_output = mode
        self.config.stt_backend = name
        self.config.save()
        self.engine.transcriber = self._make_transcriber()

    def set_speech_model(self, name: str):
        self.config.stt_server_engine = name
        self.config.save()
        tr = self._make_transcriber()
        self.engine.transcriber = tr
        # The server loads a model on its first request; trigger that now, off
        # the main thread, so the next dictation doesn't wait for it.
        import threading
        import numpy as np
        threading.Thread(target=tr.transcribe, daemon=True,
                         args=(np.zeros(8000, dtype=np.int16), self.config.sample_rate)
                         ).start()

    def set_output_mode(self, mode: str):
        self.config.output_mode = mode
        self.config.save()
        self.engine.router.output_mode = mode

    def set_log_activity(self, value: bool):
        self.config.log_activity = bool(value)
        self.config.save()
        self.activity_log.set_enabled(bool(value))

    def set_device_name(self, name: str):
        self.config.device_name = name
        self.config.save()
        # Apply immediately: re-open the input stream on the new device.
        if self.capture and self.capture.is_running:
            self.stop_listening(None)
            self.start_listening(None)

    def set_slot_action(self, slot, action_id: str):
        """Assign the action a slot fires. Persists to config and updates the
        running router so it takes effect without restarting capture."""
        slot = int(slot)
        self.config.slot_actions[slot] = action_id
        self.config.save()
        self.engine.router.slot_actions[slot] = action_id

    def restore_default_slot_actions(self):
        """Reset all 8 slot→action mappings to the factory defaults. Persists and
        applies to the running router immediately."""
        defaults = dict(Config().slot_actions)
        self.config.slot_actions = defaults
        self.config.save()
        self.engine.router.slot_actions = dict(defaults)

    def rescan_devices(self):
        """Re-enumerate audio devices for the Settings dropdown. PortAudio caches
        its device list, so we stop capture, re-init PortAudio, then restart so
        hot-plugged/unplugged devices are reflected."""
        running = bool(self.capture and self.capture.is_running)
        if running:
            self.stop_listening(None)
        try:
            audio_reinitialize()
        except Exception as e:  # noqa: BLE001 — a failed rescan must not crash
            print(f"[audio] device rescan failed: {e}", file=sys.stderr, flush=True)
        if running:
            self.start_listening(None)

    def open_log(self, _):
        from pathlib import Path as _P
        p = _P(self.log_path)
        if not p.exists():
            rumps.alert("No activity log yet",
                        f"Nothing has been logged. It will be created at:\n{p}")
            return
        subprocess.run(["open", str(p)])

    # --- status-item popover ---
    def _install_popover(self):
        """Swap rumps' dropdown for a popover: one click on the icon shows the
        settings panel directly."""
        from AppKit import NSAppearance, NSAppearanceNameAqua, NSPopover, NSViewController
        from . import theme
        from .settings_ui import SettingsController
        item = self._nsapp.nsstatusitem
        item.setMenu_(None)
        self._settings = SettingsController.alloc().initWithApp_(self)
        vc = NSViewController.alloc().init()
        vc.setView_(self._settings.view)
        pop = NSPopover.alloc().init()
        pop.setContentViewController_(vc)
        pop.setContentSize_(self._settings.view.frame().size)
        pop.setBehavior_(1)  # NSPopoverBehaviorTransient: closes on click outside
        pop.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
        self._popover = pop
        self._popover_target = theme._Target.alloc().initWithCb_(self.toggle_settings)
        item.button().setTarget_(self._popover_target)
        item.button().setAction_("fire:")

    def toggle_settings(self):
        if self.window_is_visible():
            self._popover.performClose_(None)
        else:
            self.open_settings(None)

    def open_settings(self, _):
        if self._popover is None:
            return
        from AppKit import NSApplication, NSMinYEdge
        self._settings.refresh()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        btn = self._nsapp.nsstatusitem.button()
        self._popover.showRelativeToRect_ofView_preferredEdge_(
            btn.bounds(), btn, NSMinYEdge)

    def quit(self):
        self.stop_listening(None)
        rumps.quit_application()

    def open_button_actions(self, _=None):
        if self._button_actions is None:
            from .button_actions import ButtonActionsController
            self._button_actions = ButtonActionsController.alloc().initWithApp_(self)
        self._button_actions.show()

    def open_onboarding(self, _=None):
        if self._onboarding is None:
            from .onboarding import OnboardingController
            self._onboarding = OnboardingController.alloc().initWithApp_(self)
        self._onboarding.show()

    def complete_onboarding(self):
        self.config.onboarding_done = True
        self.config.save()

    # --- capture lifecycle ---
    def start_listening(self, _):
        if self.capture and self.capture.is_running:
            return
        try:
            self.capture = AudioCapture(
                self.config.device_name, self.config.sample_rate,
                self.config.block_size, on_block=self.engine.handle_block,
                on_status=self._on_audio_status)
            self.capture.start()
            self._status = "listening"
        except DeviceNotFound:
            self.capture = None
            self._status = "error: mic not found"
        except Exception as e:  # noqa: BLE001
            self.capture = None
            self._status = f"error: {str(e)[:30]}"

    def stop_listening(self, _):
        if self.capture:
            self.capture.stop()
            self.capture = None
        self._status = "stopped"

    def open_config(self, _):
        subprocess.run(["open", str(DEFAULT_PATH)])


def _request_missing_permissions():
    """Ask for Microphone/Accessibility if not yet granted. The requests are what
    make macOS list this app (e.g. a freshly built Tink Agent.app) in Privacy &
    Security; until then it can only be added by hand."""
    from . import setup_checks
    for name, needed, request in (
        ("microphone", lambda: setup_checks.mic_status() == "undetermined",
         setup_checks.request_mic),
        ("accessibility", lambda: not setup_checks.accessibility_trusted(),
         setup_checks.request_accessibility),
    ):
        try:
            if needed():
                request()
        except Exception as e:  # noqa: BLE001 — never block startup on this
            print(f"[perms] {name} request failed: {e}", flush=True)


def _set_accessory_policy():
    """Menu-bar only: no Dock icon or Cmd+Tab entry. Windows (setup, button
    actions) still open on demand."""
    try:
        from AppKit import NSApplication
        # NSApplicationActivationPolicyAccessory == 1
        NSApplication.sharedApplication().setActivationPolicy_(1)
    except Exception:  # noqa: BLE001
        pass


def _another_instance_running() -> bool:
    """True if another Tink Agent process is already running (e.g. the login
    LaunchAgent one when the app is also opened from Finder). Two instances
    would both listen and double every keystroke."""
    try:
        from AppKit import NSRunningApplication
        from Foundation import NSProcessInfo
        bundle_id = launchagent.LABEL
        me = NSProcessInfo.processInfo().processIdentifier()
        others = [a for a in NSRunningApplication
                  .runningApplicationsWithBundleIdentifier_(bundle_id)
                  if a.processIdentifier() != me]
        for other in others:
            other.activateWithOptions_(0)
        return bool(others)
    except Exception:  # noqa: BLE001 — never block startup on this check
        return False


LOG_PATH = Path.home() / "Library" / "Logs" / "TinkAgent.log"


def _log_to_file():
    """Send stdout/stderr to the log however we were launched. launchd already
    does this, but a copy opened from Finder would otherwise log nowhere."""
    if sys.stdout is not None and sys.stdout.isatty():
        return
    try:
        import os
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        os.close(fd)
    except OSError:
        pass


def main():
    _log_to_file()
    print(f"[main] starting (pid {__import__('os').getpid()})", flush=True)
    if _another_instance_running():
        print("[main] Tink Agent is already running; exiting", flush=True)
        return
    app = TinkAgentApp()
    _set_accessory_policy()
    app.run()
