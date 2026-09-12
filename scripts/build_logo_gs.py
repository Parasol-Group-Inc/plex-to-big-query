#!/usr/bin/env python3
"""Regenerate the email logo assets from the Vox brand file.

    python scripts/build_logo_gs.py

Produces two things from `assets/cropped-Vox-Nutrition-Logo-1.webp`:

  assets/vox-logo.png             attached inline by email_utils.py (SendGrid)
  deploy/label_design_sync/Logo.gs  the same bytes, base64, for Apps Script

Both consumers need the logo as an INLINE CID part rather than a URL. Gmail
strips `data:` URIs, and a hosted URL would mean making a bucket object
publicly readable. Apps Script additionally cannot read a file out of this
repo at all, which is why its copy is checked in as source.

PNG, not WebP: Outlook renders no WebP. 320px wide so it stays sharp on
retina displays, where the templates show it at 160px.

Requires Pillow (`pip install pillow`) — only to run this script, never at
pipeline runtime.
"""
import base64
import io
import textwrap
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "cropped-Vox-Nutrition-Logo-1.webp"
PNG = ROOT / "assets" / "vox-logo.png"
GS = ROOT / "deploy" / "label_design_sync" / "Logo.gs"

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


def build_gs() -> None:
    b64 = base64.b64encode(PNG.read_bytes()).decode("ascii")
    chunks = textwrap.wrap(b64, 96)
    literal = ",\n  ".join(f"'{chunk}'" for chunk in chunks)

    header = f'''/**
 * Vox Nutrition wordmark, for the HTML emails in Code.gs.
 * ========================================================
 *
 * GENERATED FILE — do not hand-edit. Regenerate with:
 *
 *   python scripts/build_logo_gs.py
 *
 * from assets/vox-logo.png (itself converted from the brand .webp).
 *
 * WHY THE BYTES LIVE HERE. Apps Script cannot read a file out of this repo,
 * so the logo has to arrive some other way. The alternatives were worse:
 *
 *   - A hosted https URL means making a bucket object publicly readable.
 *   - A `data:` URI in the <img> is stripped by Gmail.
 *   - A Drive file makes the script depend on one person's Drive surviving,
 *     and on every recipient's ability to read it.
 *
 * MailApp's `inlineImages` takes a Blob and emits a proper CID part, which
 * renders everywhere with no external fetch. This constant is that Blob's
 * bytes. PNG, not WebP: Outlook renders no WebP at all.
 *
 * Split across lines because a single {len(b64)}-character string literal is
 * unreadable in the Apps Script editor and diffs as one line.
 */

var VOX_LOGO_B64 = [
  {literal}
].join('');

/** The wordmark as an inline-image Blob, or null if anything is wrong with it. */
function voxLogoBlob_() {{
  try {{
    return Utilities.newBlob(
      Utilities.base64Decode(VOX_LOGO_B64), 'image/png', 'vox-logo.png');
  }} catch (e) {{
    // Never fatal. A missing logo must not stop a failure report reaching an
    // inbox; the <img> alt text names the company instead.
    Logger.log('Vox logo unavailable: %s', e);
    return null;
  }}
}}
'''
    io.open(GS, "w", encoding="utf-8", newline="\n").write(header)
    print(f"wrote {GS.relative_to(ROOT)} ({len(b64):,} base64 chars, {len(chunks)} lines)")


if __name__ == "__main__":
    build_png()
    build_gs()
