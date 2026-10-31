from __future__ import annotations

# Catalog of selectable per-slot actions: the single source of truth shared by
# the router (what an id does, below) and the Button Actions UI (label + glyph).
# `type:<text>` ids type the literal text then press Enter (submit).
ACTION_CATALOG = [
    {"id": "enter",         "label": "Enter",                  "glyph": "⏎"},
    {"id": "escape",        "label": "Escape",                 "glyph": "⎋"},
    {"id": "esc_esc",       "label": "Double Esc (clear)",     "glyph": "⎋⎋"},
    {"id": "ctrl_c",        "label": "Ctrl + C (interrupt)",   "glyph": "⌃C"},
    {"id": "ctrl_d",        "label": "Ctrl + D",               "glyph": "⌃D"},
    {"id": "tab",           "label": "Tab",                    "glyph": "⇥"},
    {"id": "shift_tab",     "label": "Shift + Tab (mode)",     "glyph": "⇤"},
    {"id": "shift_enter",   "label": "Shift + Enter (newline)","glyph": "⇧⏎"},
    {"id": "up",            "label": "Arrow Up",               "glyph": "↑"},
    {"id": "down",          "label": "Arrow Down",             "glyph": "↓"},
    {"id": "left",          "label": "Arrow Left",             "glyph": "←"},
    {"id": "right",         "label": "Arrow Right",            "glyph": "→"},
    {"id": "space",         "label": "Space",                  "glyph": "␣"},
    {"id": "backspace",     "label": "Backspace",              "glyph": "⌫"},
    {"id": "cmd_v",         "label": "Paste",                  "glyph": "⌘V"},
    {"id": "key_1",         "label": 'Type "1"',     "glyph": "1"},
    {"id": "key_2",         "label": 'Type "2"',     "glyph": "2"},
    {"id": "key_3",         "label": 'Type "3"',     "glyph": "3"},
    {"id": "type:yes",      "label": 'Send "yes"',       "glyph": "y"},
    {"id": "type:continue", "label": 'Send "continue"',  "glyph": "»"},
    {"id": "type:/clear",   "label": "Send /clear",            "glyph": "/"},
    {"id": "type:/compact", "label": "Send /compact",          "glyph": "/"},
    {"id": "noop",          "label": "No action",              "glyph": "–"},
]

_CATALOG_BY_ID = {a["id"]: a for a in ACTION_CATALOG}


def action_label(action_id: str) -> str:
    a = _CATALOG_BY_ID.get(action_id)
    if a:
        return a["label"]
    if action_id.startswith(KEYS_PREFIX):
        try:
            return f"Shortcut {format_keys(action_id[len(KEYS_PREFIX):])}"
        except ValueError:
            pass
    return action_id or "No action"


# --- custom shortcuts --------------------------------------------------------
# `keys:<spec>` ids press an arbitrary shortcut. <spec> is one or more chords
# separated by spaces; each chord is `+`-joined modifiers then one key, e.g.
#   keys:cmd+shift+k      keys:esc esc      keys:ctrl+a k      keys:cmd+,
KEYS_PREFIX = "keys:"

# alias -> canonical modifier (also the pynput Key attribute name)
_MODIFIERS = {
    "cmd": "cmd", "command": "cmd", "meta": "cmd", "super": "cmd",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "opt": "alt", "option": "alt",
    "shift": "shift",
}
_MOD_ORDER = ("ctrl", "alt", "shift", "cmd")  # macOS display order ⌃⌥⇧⌘
_MOD_GLYPH = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}

# alias -> canonical named key (also the pynput Key attribute name)
_NAMED_KEYS = {
    "enter": "enter", "return": "enter", "esc": "esc", "escape": "esc",
    "tab": "tab", "space": "space", "backspace": "backspace",
    "delete": "delete", "del": "delete", "forwarddelete": "delete",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
    "plus": "+",
    **{f"f{i}": f"f{i}" for i in range(1, 21)},
}
_KEY_GLYPH = {
    "enter": "⏎", "esc": "⎋", "tab": "⇥", "space": "␣", "backspace": "⌫",
    "delete": "⌦", "up": "↑", "down": "↓", "left": "←", "right": "→",
    "home": "↖", "end": "↘", "page_up": "⇞", "page_down": "⇟",
}


def parse_keys(spec: str) -> list[tuple[tuple[str, ...], str]]:
    """Parse a shortcut spec into [(modifiers, key), ...]. Raises ValueError."""
    chords = []
    for chord in spec.split():
        parts = chord.split("+")
        if chord.endswith("+"):          # `cmd++` / lone `+` means the plus key
            parts = [p for p in parts if p] + ["+"]
        *mods, key = parts
        canon_mods = []
        for m in mods:
            canon = _MODIFIERS.get(m.lower())
            if canon is None:
                raise ValueError(f"unknown modifier {m!r} in {chord!r}")
            if canon not in canon_mods:
                canon_mods.append(canon)
        named = _NAMED_KEYS.get(key.lower())
        if named is not None:
            key = named
        elif len(key) == 1:
            key = key.lower()
        else:
            raise ValueError(f"unknown key {key!r} in {chord!r}")
        chords.append((tuple(m for m in _MOD_ORDER if m in canon_mods), key))
    if not chords:
        raise ValueError("empty shortcut")
    return chords


def format_keys(spec: str) -> str:
    """Human glyph form, e.g. 'cmd+shift+k esc' -> '⇧⌘K ⎋'. Raises ValueError."""
    out = []
    for mods, key in parse_keys(spec):
        glyph = _KEY_GLYPH.get(key) or (key.upper() if len(key) <= 3 else key)
        out.append("".join(_MOD_GLYPH[m] for m in mods) + glyph)
    return " ".join(out)


# macOS virtual key codes (ANSI layout) -> spec key name, for the shortcut recorder.
_KEYCODES = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v",
    11: "b", 12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1",
    19: "2", 20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7",
    27: "-", 28: "8", 29: "0", 30: "]", 31: "o", 32: "u", 33: "[", 34: "i",
    35: "p", 36: "enter", 37: "l", 38: "j", 39: "'", 40: "k", 41: ";", 42: "\\",
    43: ",", 44: "/", 45: "n", 46: "m", 47: ".", 48: "tab", 49: "space", 50: "`",
    51: "backspace", 53: "esc", 76: "enter",
    122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6", 98: "f7",
    100: "f8", 101: "f9", 109: "f10", 103: "f11", 111: "f12", 105: "f13",
    107: "f14", 113: "f15", 106: "f16", 64: "f17", 79: "f18", 80: "f19", 90: "f20",
    115: "home", 116: "pageup", 117: "delete", 119: "end", 121: "pagedown",
    123: "left", 124: "right", 125: "down", 126: "up",
}
# NSEventModifierFlag bits
_FLAG_MODS = ((1 << 18, "ctrl"), (1 << 19, "alt"), (1 << 17, "shift"), (1 << 20, "cmd"))


def spec_from_keycode(keycode: int, flags: int) -> str | None:
    """Recorder: one key-down event -> chord spec ('shift+cmd+k'), or None if the
    key code isn't one we can replay."""
    key = _KEYCODES.get(int(keycode))
    if key is None:
        return None
    mods = [name for bit, name in _FLAG_MODS if int(flags) & bit]
    return "+".join([*mods, key])


def normalize_keys(spec: str) -> str:
    """Canonical spec text, e.g. 'Command+Shift+K' -> 'shift+cmd+k'."""
    return " ".join("+".join([*mods, "plus" if key == "+" else key])
                    for mods, key in parse_keys(spec))


class ActionRouter:
    def __init__(self, slot_actions, keyboard=None, dispatch=None):
        self.slot_actions = dict(slot_actions)
        self._kb = keyboard  # injected (tests) or lazy pynput controller
        # All pynput calls must run on the main thread: on macOS pynput queries
        # the keyboard layout via HIToolbox TSM, which traps (SIGTRAP via
        # libdispatch) when invoked off the main thread under a running NSApp.
        # fire_slot runs on the audio callback thread and type_text on the
        # transcription worker thread, so the menu bar injects a main-thread
        # dispatcher. Default = run inline (tests / non-GUI).
        self._dispatch = dispatch or (lambda fn: fn())
        self.last_error: str | None = None

    @property
    def kb(self):
        if self._kb is None:
            from pynput import keyboard
            ctrl = keyboard.Controller()
            ctrl.Key = keyboard.Key  # attach enum for uniform access
            self._kb = ctrl
        return self._kb

    def fire_slot(self, slot: int) -> str:
        action = self.slot_actions.get(slot)
        if action is None:
            return "unmapped"
        if action == "noop":
            return "noop"
        # Defer the actual keystroke to the main thread; return the action id
        # now so the caller can emit events / log without waiting.
        self._dispatch(lambda a=action: self._run(self._perform, a))
        return action

    def _run(self, fn, arg) -> None:
        """Execute a keyboard side-effect (on the main thread), trapping errors
        (e.g. missing Accessibility) so they never crash the calling thread."""
        try:
            fn(arg)
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)

    def _perform(self, action: str) -> None:
        kb = self.kb
        Key = kb.Key
        if action == "enter":
            kb.press(Key.enter); kb.release(Key.enter)
        elif action == "escape":
            kb.press(Key.esc); kb.release(Key.esc)
        elif action == "ctrl_c":
            with kb.pressed(Key.ctrl):
                kb.press("c"); kb.release("c")
        elif action == "tab":
            kb.press(Key.tab); kb.release(Key.tab)
        elif action == "shift_tab":
            with kb.pressed(Key.shift):
                kb.press(Key.tab); kb.release(Key.tab)
        elif action == "up":
            kb.press(Key.up); kb.release(Key.up)
        elif action == "down":
            kb.press(Key.down); kb.release(Key.down)
        elif action == "esc_esc":
            kb.press(Key.esc); kb.release(Key.esc)
            kb.press(Key.esc); kb.release(Key.esc)
        elif action == "ctrl_d":
            with kb.pressed(Key.ctrl):
                kb.press("d"); kb.release("d")
        elif action == "shift_enter":
            with kb.pressed(Key.shift):
                kb.press(Key.enter); kb.release(Key.enter)
        elif action == "left":
            kb.press(Key.left); kb.release(Key.left)
        elif action == "right":
            kb.press(Key.right); kb.release(Key.right)
        elif action == "space":
            kb.press(Key.space); kb.release(Key.space)
        elif action == "backspace":
            kb.press(Key.backspace); kb.release(Key.backspace)
        elif action == "cmd_v":
            with kb.pressed(Key.cmd):
                kb.press("v"); kb.release("v")
        elif action in ("key_1", "key_2", "key_3"):
            ch = action[-1]
            kb.press(ch); kb.release(ch)
        elif action.startswith("type:"):
            self._do_type(action[len("type:"):])
            kb.press(Key.enter); kb.release(Key.enter)
        elif action.startswith(KEYS_PREFIX):
            self._do_keys(action[len(KEYS_PREFIX):])

    def _do_keys(self, spec: str) -> None:
        kb = self.kb
        Key = kb.Key
        for mods, key in parse_keys(spec):
            k = getattr(Key, key) if len(key) > 1 else key
            held = [getattr(Key, m) for m in mods]
            for m in held:
                kb.press(m)
            try:
                kb.press(k); kb.release(k)
            finally:
                for m in reversed(held):
                    kb.release(m)

    def type_text(self, text: str) -> None:
        if not text:
            return
        self._dispatch(lambda t=text: self._run(self._do_type, t))

    def _do_type(self, text: str) -> None:
        self.kb.type(text)
