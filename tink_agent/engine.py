from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np


class Engine:
    def __init__(self, config, detector, voicegate, transcriber, router,
                 on_event=None, submit_fn=None, frontmost_fn=None, logger=None):
        self.config = config
        self.detector = detector
        self.voicegate = voicegate
        self.transcriber = transcriber
        self.router = router
        self.logger = logger
        self.enabled = config.enabled
        self._last_stt = float("-inf")  # monotonic time of the last STT run
        self._warming = False
        self._on_event = on_event or (lambda kind, payload: None)
        # Optional safety guard: when config.target_app is set, actions/typing
        # only fire if the frontmost app's name or bundle id contains it.
        # frontmost_fn() -> str is injectable for tests; defaults to NSWorkspace.
        self._frontmost_fn = frontmost_fn or _default_frontmost
        if submit_fn is not None:
            self._submit = submit_fn
        else:
            self._pool = ThreadPoolExecutor(max_workers=1)
            self._submit = lambda fn: self._pool.submit(fn)

    @property
    def is_capturing(self) -> bool:
        """True while an utterance is open (used by the menu bar indicator)."""
        return bool(getattr(self.voicegate, "active", False))

    def _front(self) -> str:
        try:
            return self._frontmost_fn() or ""
        except Exception:  # noqa: BLE001 — never let the guard crash the path
            return ""

    def _target_ok(self, front: str) -> bool:
        targets = [t.strip().lower()
                   for t in (self.config.target_apps or []) if t and t.strip()]
        if not targets:
            return True
        f = front.lower()
        return any(t in f for t in targets)

    def handle_block(self, block):
        if not self.enabled:
            return
        slot = self.detector.process(block)
        if slot is not None:
            front = self._front()
            if self._target_ok(front):
                action = self.router.fire_slot(slot)
                self._on_event("tone", slot)
                self._on_event("action", action)
                if self.logger:
                    self.logger.action(slot, action, front)
            else:
                self._on_event("blocked", slot)
                if self.logger:
                    self.logger.blocked(f"slot{slot}", front)
        was_open = self.is_capturing
        utterance = self.voicegate.process(block, self.detector.tone_active)
        if self.is_capturing and not was_open:
            # Speech just started: if the model may have gone cold, page it back
            # in now, while the user is still talking.
            self.keep_warm(self.config.stt_onset_warm_s, during_speech=True)
        if utterance is not None:
            self._submit(lambda u=utterance: self._handle_utterance(u))

    def keep_warm(self, idle_s, now=None, during_speech=False) -> bool:
        """Queue a throwaway transcription if the STT engine has sat idle for
        idle_s, so its model stays resident instead of being paged out (a cold
        model can take 5-20 s to answer). Returns True if one was queued."""
        now = time.monotonic() if now is None else now
        if (not idle_s or not self.enabled or self._warming
                or not getattr(self.transcriber, "needs_warm", True)
                or (self.is_capturing and not during_speech)
                or now - self._last_stt < idle_s):
            return False
        self._warming = True
        self._last_stt = now
        self._submit(self._warm)
        return True

    def _warm(self):
        try:
            rng = np.random.default_rng()
            hiss = (rng.standard_normal(self.config.sample_rate // 2) * 10).astype(np.int16)
            t0 = time.monotonic()
            self.transcriber.transcribe(hiss, self.config.sample_rate)
            print(f"[warm] {time.monotonic() - t0:.2f}s", flush=True)
        except Exception:  # noqa: BLE001 — warming is best effort
            pass
        finally:
            self._warming = False

    def _handle_utterance(self, utterance):
        self._last_stt = t0 = time.monotonic()
        text = self.transcriber.transcribe(utterance, self.config.sample_rate)
        print(f"[stt] {len(utterance) / self.config.sample_rate:.1f}s audio -> "
              f"{time.monotonic() - t0:.2f}s", flush=True)
        if not text:
            if self.transcriber.last_error:
                self._on_event("error", self.transcriber.last_error)
            return
        front = self._front()
        if not self._target_ok(front):
            self._on_event("blocked", text)
            if self.logger:
                self.logger.blocked(text, front)
            return
        # Trailing space so consecutive utterances don't run together.
        self.router.type_text(text + " ")
        self._on_event("transcript", text)
        if self.logger:
            self.logger.transcript(text, front)


def _default_frontmost() -> str:
    """Frontmost app identity (name + bundle id) via AppKit, or "" if unavailable."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return ""
        return f"{app.localizedName() or ''} {app.bundleIdentifier() or ''}"
    except Exception:  # noqa: BLE001
        return ""
