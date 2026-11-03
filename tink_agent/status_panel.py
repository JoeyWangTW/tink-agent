"""Borderless panel that drops down from the menu-bar icon.

Used instead of NSPopover: no arrow, and it closes on any click outside it
(in another app or another of our windows) or on Esc. Main thread only.
"""
from __future__ import annotations

import objc
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSColor, NSEvent, NSMakeRect, NSPanel,
    NSScreen, NSStatusWindowLevel, NSWindowStyleMaskBorderless,
)

_MOUSE_DOWN = (1 << 1) | (1 << 3) | (1 << 25)  # left | right | other mouse down
_KEY_DOWN = 1 << 10
_ESC = 53
GAP = 4       # px between the menu bar and the panel
RADIUS = 12.0


class _KeyPanel(NSPanel):
    """Borderless windows refuse key status by default; the popups need it."""

    def canBecomeKeyWindow(self):
        return True


class StatusPanel:
    def __init__(self, status_item, view):
        self.item = status_item
        size = view.frame().size
        panel = _KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, size.width, size.height),
            NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setHidesOnDeactivate_(False)
        view.setWantsLayer_(True)
        view.layer().setCornerRadius_(RADIUS)
        view.layer().setMasksToBounds_(True)
        panel.setContentView_(view)
        self.panel = panel
        self._monitors = []

    def is_visible(self) -> bool:
        return bool(self.panel.isVisible())

    def toggle(self):
        self.close() if self.is_visible() else self.show()

    def show(self):
        self._place()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)
        self._watch_outside_clicks()

    def close(self):
        for m in self._monitors:
            NSEvent.removeMonitor_(m)
        self._monitors = []
        self.panel.orderOut_(None)

    @objc.python_method
    def _place(self):
        """Top edge just under the icon; centered on it, kept on screen."""
        btn = self.item.button()
        icon = btn.window().frame()
        screen = btn.window().screen() or NSScreen.mainScreen()
        vis = screen.visibleFrame()
        size = self.panel.frame().size
        x = icon.origin.x + icon.size.width / 2 - size.width / 2
        x = max(vis.origin.x + GAP,
                min(x, vis.origin.x + vis.size.width - size.width - GAP))
        y = icon.origin.y - GAP - size.height
        self.panel.setFrameOrigin_((x, y))

    @objc.python_method
    def _watch_outside_clicks(self):
        if self._monitors:
            return
        icon_window = self.item.button().window()

        def local(event):
            w = event.window()
            if event.type() == 10 and event.keyCode() == _ESC:  # NSEventTypeKeyDown
                self.close()
                return None
            # A click in another of our windows closes the panel. A click on the
            # icon is left to the icon's own toggle.
            # A popup's menu is its own window; picking from it is not "outside".
            if (w is not None and w != self.panel and w != icon_window
                    and "Menu" not in w.className()):
                self.close()
            return event

        self._monitors = [
            NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                _MOUSE_DOWN, lambda e: self.close()),
            NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                _MOUSE_DOWN | _KEY_DOWN, local),
        ]
