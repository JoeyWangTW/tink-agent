"""First-run onboarding window: 'Set Up TINK' — themed via theme.py.

Every check/action delegates to setup_checks or TinkAgentApp. Main thread.
"""
from __future__ import annotations

import time
from pathlib import Path

import objc
import rumps
from AppKit import (
    NSApplication, NSFloatingWindowLevel, NSMakeRect, NSPopUpButton,
)
from Foundation import NSObject

from . import audio, setup_checks, theme

W, H = 460, 600
_REPO = Path(__file__).resolve().parent.parent

_CARD_SPECS = [
    ("1", "Check permissions", "Microphone and Accessibility for Tink Agent.", "grant"),
    ("2", "Connect the mic", "Ting or FX MIC: USB-C for files, line-out for audio.", None),
    ("3", "Load config", "Copy the tone config and samples onto the mic.", "copy"),
    ("4", "Verify", "Restart the mic, then press a button to confirm.", "arm"),
]
_CARD_BTN_TITLES = {0: "Grant…", 2: "Copy files to mic", 3: "I restarted it — listen"}


class OnboardingController(NSObject):
    def initWithApp_(self, app):
        self = objc.super(OnboardingController, self).init()
        if self is None:
            return None
        self.app = app
        self._timer = None
        self._armed_at = None
        self._build()
        return self

    # --- build ---
    @objc.python_method
    def _build(self):
        win, c = theme.window("Set Up TINK Agent", W, H)
        win.setDelegate_(self)
        win.setLevel_(NSFloatingWindowLevel)
        win.setHidesOnDeactivate_(False)
        self.window = win
        self.popup_device = None
        self._devices_shown = None
        self._build_setup_view()
        self._build_usage_view()
        win.setContentView_(self.setup_view)

    @objc.python_method
    def _build_setup_view(self):
        v = theme._BGView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        head = theme.label("Get your mic working", size=24, weight="bold",
                           color=theme.GREEN)
        head.setFrame_(NSMakeRect(24, 22, W - 48, 30)); v.addSubview_(head)
        sub = theme.label("Four quick steps. This takes about a minute.",
                          size=13, color=theme.SUBTLE)
        sub.setFrame_(NSMakeRect(24, 54, W - 48, 18)); v.addSubview_(sub)

        cw = W - 48
        steps_h = len(_CARD_SPECS) * 92 + 12
        card = theme.card(24, 84, cw, steps_h)
        body = card.contentView()
        self.cards = []
        for i, (num, title, sub_t, action) in enumerate(_CARD_SPECS):
            row = theme.StepRow.make(int(num), title, sub_t, 14, 6 + i * 92,
                                     cw - 28, last=(i == len(_CARD_SPECS) - 1))
            body.addSubview_(row)
            btn = None
            barea = row.body_area()
            if i == 0:
                btn = theme.plain_button(_CARD_BTN_TITLES[0], self._grant, 0, 0, 120, 28)
                barea.addSubview_(btn)
            elif i == 1:
                self.popup_device = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                    NSMakeRect(0, 0, cw - 60, 26), False)
                self._wire_device_popup()
                barea.addSubview_(self.popup_device)
            elif i == 2:
                btn = theme.plain_button(_CARD_BTN_TITLES[2], self._copy, 0, 0, 180, 28)
                barea.addSubview_(btn)
            elif i == 3:
                btn = theme.plain_button(_CARD_BTN_TITLES[3], self._arm, 0, 0, 200, 28)
                barea.addSubview_(btn)
            self.cards.append({"row": row, "btn": btn})
        v.addSubview_(card)

        self.btn_cancel = theme.plain_button("Cancel", self._cancel,
                                             W - 24 - 200, H - 46, 95, 30)
        self.btn_continue = theme.accent_button("Continue", self._continue,
                                                W - 24 - 100, H - 46, 100, 30)
        v.addSubview_(self.btn_cancel); v.addSubview_(self.btn_continue)
        self.setup_view = v

    @objc.python_method
    def _build_usage_view(self):
        v = theme._BGView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        head = theme.label("TINK is ready", size=24, weight="bold", color=theme.GREEN)
        head.setFrame_(NSMakeRect(24, 24, W - 48, 30)); v.addSubview_(head)
        steps = [
            ("Choose transcription software",
             "Open Settings and pick your engine (e.g. MacWhisper)."),
            ("Speak",
             "Squeeze and hold the handle (push-to-talk). Your words are typed "
             "into the focused app."),
            ("Accept or change the action",
             "Press the white button to accept. Use green to pick the slot, "
             "orange to switch the action bank."),
        ]
        y = 72
        for i, (t, s) in enumerate(steps):
            tl = theme.label(f"{i + 1}.  {t}", size=14.5, weight="semibold",
                             color=theme.GREEN)
            tl.setFrame_(NSMakeRect(24, y, W - 48, 20)); v.addSubview_(tl)
            sl = theme.label(s, size=12.5, color=theme.SUBTLE, wrap=True)
            sl.setFrame_(NSMakeRect(24, y + 22, W - 48, 40)); v.addSubview_(sl)
            y += 80
        v.addSubview_(theme.plain_button("Open Settings…", self._open_settings,
                                         24, H - 46, 150, 30))
        v.addSubview_(theme.accent_button("Done", self._done,
                                          W - 24 - 100, H - 46, 100, 30))
        self.usage_view = v

    @objc.python_method
    def _wire_device_popup(self):
        t = theme._Target.alloc().initWithCb_(
            lambda: self._device_cb(self.popup_device.titleOfSelectedItem()))
        self.popup_device.setTarget_(t)
        self.popup_device.setAction_("fire:")
        theme._retain(self.popup_device, t)

    # --- show / timer ---
    @objc.python_method
    def show(self):
        self._armed_at = None
        self.window.setContentView_(self.setup_view)
        if self._timer is None:
            self._timer = rumps.Timer(self._tick, 0.5)
        self._timer.start()
        self._rebuild_devices()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _stop_timer(self):
        if self._timer is not None:
            self._timer.stop()

    def windowWillClose_(self, notification):
        self._stop_timer()

    @objc.python_method
    def _rebuild_devices(self):
        if self.popup_device is None:
            return
        try:
            connected = audio.input_device_names()
        except Exception:  # noqa: BLE001
            connected = []
        if connected == self._devices_shown:
            return
        self._devices_shown = connected
        items, idx = audio.device_menu_items(self.app.config.device_name, connected)
        self.popup_device.removeAllItems()
        if items:
            self.popup_device.addItemsWithTitles_(items)
        if 0 <= idx < len(items):
            self.popup_device.selectItemAtIndex_(idx)

    @objc.python_method
    def _tick(self, _):
        c = self.app.config
        mic = setup_checks.mic_status()
        ax = setup_checks.accessibility_trusted()
        ok1 = (mic == "authorized") and ax
        self.cards[0]["row"].set_state("done" if ok1 else "active")
        self.cards[0]["row"].set_subtitle(
            "Microphone & accessibility granted." if ok1 else
            f"Microphone: {mic} · Accessibility: {'ok' if ax else 'not granted'}")
        if self.cards[0]["btn"] is not None:
            self.cards[0]["btn"].setHidden_(ok1)

        disk, model = setup_checks.find_device_disk()
        mounted = disk is not None
        audio_ok = setup_checks.audio_present(c)
        ok2 = mounted and audio_ok
        self.cards[1]["row"].set_state("done" if ok2 else ("active" if ok1 else "pending"))
        self.cards[1]["row"].set_subtitle(
            f"{model} connected (files + audio)." if ok2 else
            f"{model + ' disk ok' if mounted else 'plug in USB-C'} · "
            f"{'audio ok' if audio_ok else 'connect line-out adapter'}")
        self._rebuild_devices()

        files = mounted and setup_checks.files_match(_REPO, disk)
        self.cards[2]["row"].set_state("done" if files else ("active" if ok2 else "pending"))
        self.cards[2]["row"].set_subtitle(
            "Config + samples on TINK. Power-cycle the mic to load them."
            if files else "Copy the tone config and samples onto the mic.")
        if self.cards[2]["btn"] is not None:
            self.cards[2]["btn"].setHidden_(not (mounted and not files))

        heard = (self._armed_at is not None
                 and self.app._last_tone_at > self._armed_at)
        if heard:
            verify_sub = f"Heard slot {self.app._last_tone_slot} — TINK works!"
        elif self._armed_at is None:
            verify_sub = "Restart the mic, then click to listen."
        elif not audio_ok:
            verify_sub = "Audio adapter not detected — reconnect it (step 2)."
        else:
            verify_sub = "Listening… press a mic button (green, then white)."
        self.cards[3]["row"].set_state("done" if heard else ("active" if files else "pending"))
        self.cards[3]["row"].set_subtitle(verify_sub)
        if self.cards[3]["btn"] is not None:
            self.cards[3]["btn"].setHidden_(not (audio_ok and not heard))

        self.btn_continue.setEnabled_(ok1 and ok2 and files and heard)

    @objc.python_method
    def _grant(self):
        setup_checks.request_mic()
        setup_checks.request_accessibility()

    @objc.python_method
    def _copy(self):
        try:
            disk, _ = setup_checks.find_device_disk()
            if disk is None:
                raise FileNotFoundError("No TINGDISK or FX MIC DISK volume mounted.")
            setup_checks.copy_device_config(_REPO, disk)
        except Exception as e:  # noqa: BLE001
            rumps.alert("Couldn't copy to the mic", str(e))

    @objc.python_method
    def _arm(self):
        self.app.start_listening(None)
        self._armed_at = time.monotonic()

    @objc.python_method
    def _device_cb(self, title):
        if not title:
            return
        name = audio.device_name_from_title(title)
        if name is not None:
            self.app.set_device_name(name)

    @objc.python_method
    def _continue(self):
        self.window.setContentView_(self.usage_view)

    @objc.python_method
    def _cancel(self):
        self.window.orderOut_(None)

    @objc.python_method
    def _open_settings(self):
        self.app.open_settings(None)

    @objc.python_method
    def _done(self):
        self._stop_timer()
        self.app.complete_onboarding()
        self.window.orderOut_(None)
