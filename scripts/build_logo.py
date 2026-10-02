#!/usr/bin/env python3
"""Regenerate the email logo asset from the Vox brand file.

    python scripts/build_logo.py

Produces `assets/vox-logo.png` from
`assets/cropped-Vox-Nutrition-Logo-1.webp`, attached inline by
`email_utils.py` (SendGrid).

It needs to be an INLINE CID part rather than a URL: Gmail strips `data:`
URIs, and a hosted URL would mean making a bucket object publicly readable.

PNG, not WebP: Outlook renders no WebP. 320px wide so it stays sharp on
retina displays, where the templates show it at 160px.

Until 2026-10-02 this script also wrote `deploy/label_design_sync/Logo.gs`,
the same bytes as base64, because Apps Script cannot read a file out of this
repo. That script is archived (`deploy/archive/label_design_sync/`), so the
frozen Logo.gs there is the last generated copy and nothing regenerates it.

Requires Pillow (`pip install pillow`) — only to run this script, never at
pipeline runtime.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "cropped-Vox-Nutrition-Logo-1.webp"
PNG = ROOT / "assets" / "vox-logo.png"

WIDTH = 320  # 2x the 160px the email templates render it at


def build_png() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    height = round(image.height * WIDTH / image.width)
    image = image.resize((WIDTH, height), Image.LANCZOS)

    # Flattened onto white rather than left transparent: the Vox email header
    # is white, and several clients render a transparent PNG against a dark
    # background in dark mode, which would put a navy wordmark on navy.
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    canvas.convert("RGB").save(PNG, "PNG", optimize=True)
    print(f"wrote {PNG.relative_to(ROOT)} ({WIDTH}x{height}, {PNG.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_png()
