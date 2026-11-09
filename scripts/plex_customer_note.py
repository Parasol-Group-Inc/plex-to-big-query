"""Read or set a customer's Note in Plex, through the Customer Details screen.

The REST Customers API cannot do this: on 2026-11-09 a PUT with `note` on a test-tenant
customer that had no note returned 200 and stamped the record modified, but the note
stayed empty. The screen writes the same field people edit by hand, so this drives it
with the same Playwright login the screen task uses (plex_web_export.login), one
customer at a time.

    python scripts/plex_customer_note.py 808258                          # read only
    python scripts/plex_customer_note.py 808258 --set "PLACEHOLDER"      # write if empty
    python scripts/plex_customer_note.py 808258 --set "..." --overwrite  # replace a note

Steps: open SalesAndCRM/customeraddresses for the customer, click the "Customer
Details" side tab, read textarea[name=Note]. With --set: refuse if the note is not
empty (unless --overwrite), type the text, click Apply, reload the screen and read it
back. Screenshots before and after go to etl-manual/customer_note/ (gitignored: they
show customer data). Shares the Plex web lock with the screen task and the export.

PRODUCTION. Needs PLEX_PORTAL_USERNAME / PLEX_PORTAL_PASSWORD (environment or .env).
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plex_web_export import LOCK, creds, login, run_lock  # noqa: E402

SCREEN = "https://vox.on.plex.com/SalesAndCRM/customeraddresses?__sk=3&__sak=23&CustomerNo={no}"
SHOTS = LOCK.parent / "customer_note"


def open_details(pg, customer_no):
    pg.goto(SCREEN.format(no=customer_no), wait_until="networkidle", timeout=90000)
    pg.locator("p.plex-sidetabs-menu-item-title", has_text="Customer Details").first.click()
    note = pg.locator('textarea[name="Note"]').first
    note.wait_for(state="visible", timeout=60000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    return note


def title(pg):
    try:
        return pg.locator("h1, .plex-page-title, .plex-form-title").first.inner_text(timeout=5000).strip()
    except Exception:  # noqa: BLE001 - only for the log line
        return "?"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("customer_no", help="Plex Customer_No, e.g. 808258 (in the screen's URL)")
    ap.add_argument("--set", dest="text", help="note text to write")
    ap.add_argument("--overwrite", action="store_true", help="replace a note that is not empty")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    args = ap.parse_args()

    user, password = creds()
    SHOTS.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.customer_no}_{dt.datetime.now():%Y%m%d_%H%M%S}"
    with run_lock(), sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            login(pg, user, password)
            note = open_details(pg, args.customer_no)
            before = note.input_value()
            print(f"customer {args.customer_no} ({title(pg)}): note now {before!r}")
            pg.screenshot(path=str(SHOTS / f"{stamp}_before.png"), full_page=True)
            if args.text is None:
                return 0
            if before.strip() and not args.overwrite:
                print("not written: the note is not empty (use --overwrite to replace it)")
                return 2
            note.fill(args.text)
            note.press("Tab")  # the screen's binding takes the value on change/blur
            pg.locator("button", has_text="Apply").first.click()
            pg.wait_for_load_state("networkidle", timeout=60000)
            pg.wait_for_timeout(2000)
            errors = pg.locator(".plex-error, .plex-banner-error, .validation-summary-errors").all_inner_texts()
            if any(e.strip() for e in errors):
                print("Plex showed an error:", " | ".join(e.strip() for e in errors if e.strip()))
            note = open_details(pg, args.customer_no)  # reload: read what Plex saved, not what we typed
            after = note.input_value()
            pg.screenshot(path=str(SHOTS / f"{stamp}_after.png"), full_page=True)
            ok = after == args.text
            print(f"after reload: {after!r} -> {'SAVED' if ok else 'NOT SAVED'}")
            print(f"screenshots: {SHOTS / (stamp + '_before.png')} and _after.png")
            return 0 if ok else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
