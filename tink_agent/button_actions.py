"""Native (AppKit) 'Map a Button' window — themed via theme.py.

Lets the user assign each of the 8 Tink slots (2 banks x 4 buttons) an action
from ACTION_CATALOG. Delegates persistence to TinkAgentApp.set_slot_action.
Main thread only. Implements the imported `Tink Button Actions.dc.html` design.
"""
from __future__ import annotations

import objc
from AppKit import (
    NSApplication, NSMakeRect, NSBezierPath, NSGraphicsContext, NSAffineTransform,
    NSMutableParagraphStyle, NSTextTab, NSTextAlignmentLeft,
    NSMutableAttributedString, NSFontAttributeName, NSForegroundColorAttributeName,
    NSParagraphStyleAttributeName, NSTextField, NSEvent, NSEventMaskKeyDown,
)
from Foundation import NSObject

from . import theme
from .actions import ACTION_CATALOG, KEYS_PREFIX, format_keys, normalize_keys, \
    spec_from_keycode

W, H = 600, 458
M = 18
DEVICE_W = 286


def slot_number(mode_index: int, slot_index: int) -> int:
    """Global slot id 1-8. Bank A (mode 0) -> 1-4, Bank B (mode 1) -> 5-8."""
    return mode_index * 4 + slot_index + 1


# Popup index of the "Custom shortcut…" item (appended after the catalog).
CUSTOM_INDEX = len(ACTION_CATALOG)
_HINT = "Press Record, then the shortcut. Type a sequence like: esc esc"


def catalog_index_of(action_id: str) -> int:
    if action_id.startswith(KEYS_PREFIX):
        return CUSTOM_INDEX
    for i, a in enumerate(ACTION_CATALOG):
        if a["id"] == action_id:
            return i
    return next(i for i, a in enumerate(ACTION_CATALOG) if a["id"] == "noop")


def _menu_title(glyph, label):
    """Attributed popup title: glyph column + a tab stop so every label starts at
    the same x regardless of glyph width (muted glyph, green label)."""
    full = f"{glyph}\t{label}"
    para = NSMutableParagraphStyle.alloc().init()
    tab = NSTextTab.alloc().initWithTextAlignment_location_options_(
        NSTextAlignmentLeft, 34.0, {})
    para.setTabStops_([tab])
    para.setDefaultTabInterval_(34.0)
    s = NSMutableAttributedString.alloc().initWithString_(full)
    rng_all = (0, len(full))
    s.addAttribute_value_range_(NSFontAttributeName, theme.font(13, "medium"), rng_all)
    s.addAttribute_value_range_(NSParagraphStyleAttributeName, para, rng_all)
    glen = len(glyph) + 1  # glyph + tab character
    s.addAttribute_value_range_(NSForegroundColorAttributeName, theme.MUTED, (0, glen))
    s.addAttribute_value_range_(
        NSForegroundColorAttributeName, theme.GREEN, (glen, len(label)))
    return s


class DeviceView(theme.Flipped):
    """Draws a stylized Tink device; lights the LED for the selected bank+slot."""

    def initWithFrame_(self, frame):
        self = objc.super(DeviceView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._mode_index = 0
        self._slot_index = 0
        return self

    @objc.python_method
    def set_selection_(self, mode_index, slot_index):
        self._mode_index = mode_index
        self._slot_index = slot_index
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        # Faithful reproduction of the `Tink Button Actions.dc.html` SVG
        # (viewBox 420x600). The view isFlipped (y-down), matching SVG coords, so
        # we draw directly in SVG units under a fit-and-center transform.
        ctx = NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        b = self.bounds()
        VBW, VBH, pad = 420.0, 600.0, 10.0
        s = min((b.size.width - 2 * pad) / VBW, (b.size.height - 2 * pad) / VBH)
        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_((b.size.width - VBW * s) / 2.0,
                             (b.size.height - VBH * s) / 2.0)
        tf.scaleBy_(s)
        tf.concat()

        dgreen = theme.color("#0F3A28")
        tan = theme.color("#D9D0B7")
        cream = theme.color("#EFEBDF")
        gaccent = theme.color("#14543A")
        orange = theme.ORANGE
        grille = theme.color("#231F20")
        led_white = theme.color("#FDFCF9")

        def rrect(x, y, w, h, r):
            return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, w, h), r, r)

        def q(path, cx, cy, ex, ey):  # quadratic segment via cubic control points
            p = path.currentPoint()
            path.curveToPoint_controlPoint1_controlPoint2_(
                (ex, ey),
                (p.x + 2.0 / 3 * (cx - p.x), p.y + 2.0 / 3 * (cy - p.y)),
                (ex + 2.0 / 3 * (cx - ex), ey + 2.0 / 3 * (cy - ey)))

        def disc(cx, cy, r, col):
            col.setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - r, cy - r, 2 * r, 2 * r)).fill()

        # --- angled handle (left) ---
        h = NSBezierPath.bezierPath()
        h.moveToPoint_((50, 80)); q(h, 50, 70, 60, 70)
        h.lineToPoint_((110, 70)); h.lineToPoint_((110, 362))
        h.lineToPoint_((85, 362)); h.closePath()
        dgreen.setFill(); h.fill()

        # --- side accent buttons (behind body; only the right tab shows) ---
        orange.setFill(); rrect(316, 66, 41, 42, 8).fill()
        gaccent.setFill(); rrect(316, 158, 41, 42, 8).fill()
        wbtn = rrect(316, 318, 41, 42, 8)
        cream.setFill(); wbtn.fill()
        dgreen.setStroke(); wbtn.setLineWidth_(3.0); wbtn.stroke()

        # --- lower body (cream) ---
        lo = NSBezierPath.bezierPath()
        lo.moveToPoint_((85, 249)); lo.lineToPoint_((335, 249))
        lo.lineToPoint_((335, 415)); q(lo, 335, 429, 321, 429)
        lo.lineToPoint_((99, 429)); q(lo, 85, 429, 85, 415)
        lo.closePath()
        cream.setFill(); lo.fill()
        dgreen.setStroke(); lo.setLineWidth_(3.5); lo.stroke()

        # --- upper body (tan) ---
        up = NSBezierPath.bezierPath()
        up.moveToPoint_((85, 249)); up.lineToPoint_((85, 44))
        q(up, 85, 30, 99, 30); up.lineToPoint_((321, 30))
        q(up, 335, 30, 335, 44); up.lineToPoint_((335, 249))
        up.closePath()
        tan.setFill(); up.fill()

        # --- grille (clipped to upper body): thin horizontal bars, with a denser
        #     band inside the circular mic cut-out ---
        ctx.saveGraphicsState()
        up.addClip()
        grille.setFill()
        k = 0
        while 4.5 + 13 * k <= 249:
            NSBezierPath.fillRect_(NSMakeRect(85, 4.5 + 13 * k, 250, 4.5)); k += 1
        ctx.saveGraphicsState()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(133, 65, 148, 148)).addClip()
        k = 0
        while 1.5 + 13 * k <= 249:
            NSBezierPath.fillRect_(NSMakeRect(133, 1.5 + 13 * k, 148, 10)); k += 1
        ctx.restoreGraphicsState()
        # LED backings (tan discs erase the grille), then the LEDs themselves
        mode_ys = (66, 80, 94, 108)
        slot_ys = (158, 172, 186, 200)
        for cy in mode_ys + slot_ys:
            disc(299, cy, 7.5, tan)
        for i, cy in enumerate(mode_ys):           # Bank A: none; Bank B: 1st orange
            disc(299, cy, 5, orange if (self._mode_index == 1 and i == 0) else grille)
        for i, cy in enumerate(slot_ys):           # selected slot lights white
            disc(299, cy, 5, led_white if i == self._slot_index else grille)
        ctx.restoreGraphicsState()

        # body outline on top of the grille
        dgreen.setStroke(); up.setLineWidth_(3.5); up.stroke()

        # --- wordmark ---
        theme._attr_title("TINK", theme.font(46, "bold"), orange).drawAtPoint_((120, 300))
        theme._attr_title("AGENT", theme.font(15, "semibold"), gaccent).drawAtPoint_(
            (122, 352))

        # --- cable ---
        orange.setFill()
        for cy in (431, 440, 449, 458, 467, 476, 485):
            rrect(196, cy, 28, 6, 3).fill()
        gaccent.setFill(); NSBezierPath.fillRect_(NSMakeRect(204, 493, 11, 107))

        ctx.restoreGraphicsState()


class ButtonActionsController(NSObject):
    def initWithApp_(self, app):
        self = objc.super(ButtonActionsController, self).init()
        if self is None:
            return None
        self.app = app
        self._mode_index = 0
        self._slot_index = 0
        self._monitor = None
        self._build()
        return self

    @objc.python_method
    def _build(self):
        win, c = theme.window("Map a Button", W, H)
        self.window = win

        # left: device card
        dcard = theme.card(M, M, DEVICE_W, H - 2 * M)
        self.device = DeviceView.alloc().initWithFrame_(
            NSMakeRect(0, 0, DEVICE_W, H - 2 * M))
        dcard.contentView().addSubview_(self.device)
        c.addSubview_(dcard)

        # right column
        rx = M + DEVICE_W + 16
        rw = W - rx - M
        y = M + 4

        mh = theme.section_header("Orange button · Mode")
        mh.setFrame_(NSMakeRect(rx, y, rw, 16)); c.addSubview_(mh); y += 22
        self.seg_mode = theme.segmented(
            ["Bank A", "Bank B"], 0, self._on_mode, rx, y, rw, 26)
        c.addSubview_(self.seg_mode); y += 40

        sh = theme.section_header("Green button · Slot")
        sh.setFrame_(NSMakeRect(rx, y, rw, 16)); c.addSubview_(sh); y += 22
        self.seg_slot = theme.segmented(
            ["1", "2", "3", "4"], 0, self._on_slot, rx, y, rw, 26)
        c.addSubview_(self.seg_slot); y += 44

        # detail card
        ch = 200
        card = theme.card(rx, y, rw, ch)
        body = card.contentView()
        self.hdr = theme.label("Slot 1", size=17, weight="bold", color=theme.GREEN)
        self.hdr.setFrame_(NSMakeRect(14, 12, rw - 28, 22)); body.addSubview_(self.hdr)
        self.cap = theme.label("", size=12, color=theme.SUBTLE)
        self.cap.setFrame_(NSMakeRect(14, 36, rw - 28, 16)); body.addSubview_(self.cap)
        wl = theme.label("WHITE BUTTON FIRES", size=10.5, weight="semibold",
                         color=theme.MUTED)
        wl.setFrame_(NSMakeRect(14, 64, rw - 28, 14)); body.addSubview_(wl)
        _, self.popup = theme.popup_row("", rw, 84, h=40)
        # popup_row puts the popup at x=130; widen/relocate it to fill the card.
        self.popup.setFrame_(NSMakeRect(14, 92, rw - 28, 26))
        self.popup.removeAllItems()
        for a in ACTION_CATALOG:
            self.popup.addItemWithTitle_(a["id"])   # unique base title (ids are unique)
            self.popup.lastItem().setAttributedTitle_(_menu_title(a["glyph"], a["label"]))
        self.popup.addItemWithTitle_("__custom__")
        self.popup.lastItem().setAttributedTitle_(_menu_title("⌨", "Custom shortcut…"))
        self._wire_popup()
        body.addSubview_(self.popup)

        # custom shortcut: editable spec field + Record button + hint/error line
        bw = 84
        self.keys_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(14, 130, rw - 28 - bw - 8, 24))
        self.keys_field.setFont_(theme.font(13, "medium"))
        self.keys_field.setPlaceholderString_("e.g. cmd+shift+k")
        kt = theme._Target.alloc().initWithCb_(self._commit_field)
        self.keys_field.setTarget_(kt)
        self.keys_field.setAction_("fire:")
        theme._retain(self.keys_field, kt)
        body.addSubview_(self.keys_field)
        self.btn_record = theme.plain_button(
            "Record", self._toggle_record, rw - 14 - bw, 128, bw, 28)
        body.addSubview_(self.btn_record)
        self.keys_hint = theme.label(_HINT, size=11, color=theme.SUBTLE)
        self.keys_hint.setFrame_(NSMakeRect(14, 162, rw - 28, 30))
        body.addSubview_(self.keys_hint)
        c.addSubview_(card); y += ch + 10

        self.btn_reset = theme.plain_button(
            "Restore defaults", self._reset, rx, y + 6, rw, 28)
        c.addSubview_(self.btn_reset)

    @objc.python_method
    def _wire_popup(self):
        t = theme._Target.alloc().initWithCb_(
            lambda: self._apply_action_index(int(self.popup.indexOfSelectedItem())))
        self.popup.setTarget_(t)
        self.popup.setAction_("fire:")
        theme._retain(self.popup, t)

    # --- callbacks ---
    @objc.python_method
    def _on_mode(self, index):
        self._mode_index = index
        self._update_detail()

    @objc.python_method
    def _on_slot(self, index):
        self._slot_index = index
        self._update_detail()

    @objc.python_method
    def _reset(self):
        self.app.restore_default_slot_actions()
        self._update_detail()

    @objc.python_method
    def _slot(self):
        return slot_number(self._mode_index, self._slot_index)

    @objc.python_method
    def _apply_action_index(self, catalog_index):
        self._stop_record()
        if catalog_index == CUSTOM_INDEX:
            self._set_custom_visible(True)
            current = self.app.config.slot_actions.get(self._slot(), "")
            if not current.startswith(KEYS_PREFIX):
                self._start_record()  # fresh custom slot: go straight to capture
            return
        self.app.set_slot_action(self._slot(), ACTION_CATALOG[catalog_index]["id"])
        self._set_custom_visible(False)

    # --- custom shortcut ---
    @objc.python_method
    def _set_custom_visible(self, on):
        if not hasattr(self, "keys_field"):  # controller built without its window
            return
        for v in (self.keys_field, self.btn_record, self.keys_hint):
            v.setHidden_(not on)

    @objc.python_method
    def _set_hint(self, text, error=False):
        self.keys_hint.setStringValue_(text)
        self.keys_hint.setTextColor_(theme.ORANGE if error else theme.SUBTLE)

    @objc.python_method
    def _save_spec(self, spec):
        """Validate + persist a spec; returns True on success."""
        try:
            spec = normalize_keys(spec)
            shown = format_keys(spec)
        except ValueError as e:
            self._set_hint(str(e), error=True)
            return False
        self.app.set_slot_action(self._slot(), KEYS_PREFIX + spec)
        self.keys_field.setStringValue_(spec)
        self._set_hint(f"Saved: {shown}")
        return True

    @objc.python_method
    def _commit_field(self):
        self._stop_record()
        self._save_spec(str(self.keys_field.stringValue()))

    @objc.python_method
    def _toggle_record(self):
        if self._monitor is None:
            self._start_record()
        else:
            self._stop_record()

    @objc.python_method
    def _start_record(self):
        if self._monitor is not None:
            return
        theme.set_plain_title(self.btn_record, "Stop")
        self._set_hint("Recording… press the shortcut now")
        self.window.makeFirstResponder_(None)  # keep keys out of the text field

        def on_key(event):
            spec = spec_from_keycode(event.keyCode(), event.modifierFlags())
            if spec is None:
                self._set_hint("That key can't be replayed — try another", error=True)
                return None
            self._stop_record()
            self._save_spec(spec)
            return None  # swallow: don't let the shortcut act on this window

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, on_key)

    @objc.python_method
    def _stop_record(self):
        if getattr(self, "_monitor", None) is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
            theme.set_plain_title(self.btn_record, "Record")

    @objc.python_method
    def _update_detail(self):
        n = slot_number(self._mode_index, self._slot_index)
        hz = self.app.config.tones.get(n, "—")
        self.hdr.setStringValue_(f"Slot {n}  ·  {hz} Hz")
        self.cap.setStringValue_(
            "Bank B · tone pitched +10.5%" if self._mode_index == 1
            else "Bank A · base tone")
        current = self.app.config.slot_actions.get(n, "noop")
        self._stop_record()
        self.popup.selectItemAtIndex_(catalog_index_of(current))
        custom = current.startswith(KEYS_PREFIX)
        self._set_custom_visible(custom)
        self.keys_field.setStringValue_(current[len(KEYS_PREFIX):] if custom else "")
        self._set_hint(_HINT)
        self.device.set_selection_(self._mode_index, self._slot_index)

    # --- show ---
    @objc.python_method
    def show(self):
        self._update_detail()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
