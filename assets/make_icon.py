"""Generate the menu-bar template icons for tink-agent.

A one-colour silhouette of the app icon's mic (angled handle, body, round grille,
side buttons, cable) drawn with AppKit. Black-on-transparent PNGs for a macOS
template image (rumps `template=True`), which the system recolours for light/dark
menu bars. The active (capturing) variant fills the grille.

Run: .venv/bin/python assets/make_icon.py
"""
from pathlib import Path

from AppKit import (
    NSBezierPath, NSBitmapImageRep, NSCalibratedRGBColorSpace, NSColor,
    NSGraphicsContext, NSMakeRect, NSBitmapImageFileTypePNG,
)

OUT = Path(__file__).parent / "tink_icon.png"
OUT_ACTIVE = Path(__file__).parent / "tink_icon_active.png"
SIZE = 44  # px (22 pt @2x)


def render(active: bool, path: Path):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
        None, SIZE, SIZE, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    ink = NSColor.blackColor()
    ink.setFill()
    ink.setStroke()

    def y(top):  # design in y-down px; AppKit is y-up
        return SIZE - top

    # angled handle (left, behind the body)
    h = NSBezierPath.bezierPath()
    h.moveToPoint_((14, y(6))); h.lineToPoint_((8.5, y(7.5)))
    h.lineToPoint_((11.5, y(27))); h.lineToPoint_((14, y(27))); h.closePath()
    h.fill()

    # side buttons (right)
    for top in (7, 14):
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(32, y(top + 4), 4, 4), 1, 1).fill()

    # body outline + divider between grille and lower half
    body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(14.25, y(35.75), 19.5, 32.5), 3.5, 3.5)
    body.setLineWidth_(2.5)
    body.stroke()
    NSBezierPath.fillRect_(NSMakeRect(15, y(21.25), 18, 1.5))

    # grille: ring (idle) or filled disc (capturing)
    grille = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(18.5, y(17.5), 11, 11))
    if active:
        grille.fill()
    else:
        grille.setLineWidth_(2.0)
        grille.stroke()

    # cable
    NSBezierPath.fillRect_(NSMakeRect(22.5, y(42), 3, 6.5))

    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None) \
        .writeToFile_atomically_(str(path), True)


def main():
    render(False, OUT)
    render(True, OUT_ACTIVE)
    print(f"wrote {OUT}")
    print(f"wrote {OUT_ACTIVE}")


if __name__ == "__main__":
    main()
