"""Render the Tink Agent app icon (1024 px PNG) from the Map a Button device art.

Run: .venv/bin/python packaging/app/make_app_icon.py OUT.png
build_app.sh turns the PNG into AppIcon.icns.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from AppKit import (  # noqa: E402
    NSApplication, NSBitmapImageRep, NSBezierPath, NSGraphicsContext,
    NSMakeRect, NSCalibratedRGBColorSpace, NSBitmapImageFileTypePNG,
    NSAffineTransform,
)
from tink_agent import theme  # noqa: E402
from tink_agent.button_actions import DeviceView  # noqa: E402

SIZE = 1024
# macOS Big Sur+ icon grid: 824 px rounded square centred in the 1024 canvas.
TILE, RADIUS = 824, 185


def render(out_path):
    NSApplication.sharedApplication()
    theme.register_fonts()
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
        None, SIZE, SIZE, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    o = (SIZE - TILE) / 2.0
    tile = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(o, o, TILE, TILE), RADIUS, RADIUS)
    theme.color("#EFEBDF").setFill()
    tile.fill()
    tile.addClip()

    # DeviceView is flipped (y-down); draw it into the tile through a flip, in a
    # context marked flipped so its text isn't mirrored.
    view = DeviceView.alloc().initWithFrame_(NSMakeRect(0, 0, TILE, TILE))
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithCGContext_flipped_(ctx.CGContext(), True))
    tf = NSAffineTransform.transform()
    tf.translateXBy_yBy_(o, o + TILE)
    tf.scaleXBy_yBy_(1.0, -1.0)
    tf.concat()
    view.set_selection_(0, -1)  # no lit slot LED
    view.drawRect_(view.bounds())

    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None) \
        .writeToFile_atomically_(str(out_path), True)


if __name__ == "__main__":
    render(sys.argv[1])
