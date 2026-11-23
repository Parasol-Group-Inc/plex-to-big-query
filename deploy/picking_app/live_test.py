"""Live tests of the DEPLOYED picking app (Plex TEST) through IAP, in a real Chrome (2026-11-23).

    python deploy/picking_app/live_test.py --login          # opens Chrome; sign in with your company Google account
    python deploy/picking_app/live_test.py                  # read-only tests (T1-T5, T7)
    python deploy/picking_app/live_test.py --move           # also T6: moves ONE container and puts it back

The Chrome profile (the IAP sign-in cookie) is kept in etl-manual/picking_live_profile/ (gitignored),
screenshots and results.json in etl-manual/picking_live_test/<timestamp>/.
Refuses to move unless the app reports env "test". The container is put back from this machine
with the Plex web session (plex_web.PlexWeb("test").move), so the put-back is in Plex's history
but not in the app's move log. Needs: pip install playwright; Google Chrome installed.
docs/PICKING_STAGING_APP.md, "Live audit and tests".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "scripts")]
U = "https://picking-app-651304971296.us-central1.run.app"
PROFILE = REPO / "etl-manual" / "picking_live_profile"

FIND_PICK = """() => {
  for (const card of document.querySelectorAll('.card[id^=line-]')) {
    for (const tr of card.querySelectorAll('tbody tr')) {
      const tds = tr.querySelectorAll('td'); const cb = tr.querySelector('input[name=serial]');
      if (cb && tds[2].innerText.trim() === '' && tds[6].innerText.trim() === 'OK' && tr.querySelector('.role.pick'))
        return {card: card.id, serial: cb.value, location: tds[5].innerText.trim(), qty: tds[7].innerText.trim(),
                target: card.querySelector('select[name=target]').value};
    }
  } return null; }"""


def browser(p, headless: bool):
    return p.chromium.launch_persistent_context(str(PROFILE), channel="chrome", headless=headless,
                                                viewport={"width": 1280, "height": 900},
                                                ignore_default_args=["--enable-automation"])


def login(p) -> None:
    ctx = browser(p, headless=False)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto(U + "/health", timeout=60000)
    t = time.time()
    while time.time() - t < 900:
        if pg.url.startswith(U) and '"ok"' in (pg.content() or ""):
            print("signed in"); break
        time.sleep(2)
    else:
        print("not signed in within 15 min")
    ctx.close()


def time_set(pg, set_no: str, extra: str = "") -> dict:
    statuses = []
    on = lambda r: statuses.append(r.status) if "/line/" in r.url else None
    pg.on("response", on)
    t = time.time()
    pg.goto(f"{U}/set/{set_no}?days=7{extra}", timeout=180000)
    opened = time.time() - t
    n = pg.locator(".card[id^=line-]").count()
    first = None
    while time.time() - t < 240:
        left = pg.locator(".line-loading").count()
        if first is None and left < n:
            first = time.time() - t
        if left == 0 or pg.locator(".line-loading .msg a").count() == left:
            break
        time.sleep(0.1)
    pg.remove_listener("response", on)
    return {"set": set_no, "ingredients": n, "open_s": round(opened, 2), "first_s": round(first or time.time() - t, 2),
            "all_s": round(time.time() - t, 2), "failed": pg.locator(".line-loading .msg a").count(),
            "progress": pg.inner_text("#progress") if pg.locator("#progress").count() else None,
            "line_statuses": sorted(set(statuses))}


def run(p, do_move: bool, big: str, small: str | None) -> dict:
    out = REPO / "etl-manual" / "picking_live_test" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {}

    def log(k, v):
        res[k] = v
        print(k, json.dumps(v, default=str)[:400], flush=True)

    ctx = browser(p, headless=True)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    t = time.time(); pg.goto(U + "/health", timeout=180000)
    if not pg.url.startswith(U):
        sys.exit("not signed in: run with --login first")
    health = json.loads(pg.inner_text("body"))
    log("T1_health", {"s": round(time.time() - t, 2), "body": health})
    t = time.time(); pg.goto(U + "/?days=7", timeout=180000)
    log("T2_index", {"s": round(time.time() - t, 2), "sets": pg.locator("table tbody tr").count()})
    pg.screenshot(path=str(out / "t2_index.png"))
    if not small:
        import re
        small = next((x for x in re.findall(r"/set/(\d+)", pg.content()) if x != big), None)
    log("T3_big_fresh", time_set(pg, big, "&refresh=1")); pg.screenshot(path=str(out / "t3_done.png"))
    log("T3_big_cached", time_set(pg, big))
    if small:
        log("T4_small_fresh", time_set(pg, small, "&refresh=1"))
    t = time.time(); pg.goto(f"{U}/set/{big}?days=7&all=1", timeout=240000)
    log("T5_all1", {"s": round(time.time() - t, 2), "loaders": pg.locator(".line-loading").count(),
                    "cards": pg.locator(".card[id^=line-]").count()})
    picked = None
    if do_move:
        if health.get("env") != "test":
            sys.exit(f"refusing to move: the app reports env {health.get('env')!r}")
        pg.goto(f"{U}/set/{big}?days=7", timeout=180000)
        pg.wait_for_function("document.querySelectorAll('.line-loading').length === 0", timeout=240000)
        picked = pg.evaluate(FIND_PICK)
        log("T6_chosen", picked)
        if picked:
            pg.evaluate("([cid, s]) => document.querySelectorAll('#' + cid + ' input[name=serial]')"
                        ".forEach(c => c.checked = (c.value === s))", [picked["card"], picked["serial"]])
            t = time.time()
            pg.locator("#" + picked["card"] + " button", has_text="Review move").click()   # review dialog (11-23)
            pg.wait_for_selector("dialog#review[open]", timeout=180000)
            log("T6_review", {"title": pg.inner_text("#rv-title"), "rows": pg.locator("#rv-body tbody tr").count()})
            with pg.expect_navigation(timeout=180000):
                pg.click("#rv-approve")
            log("T6_move", {"s": round(time.time() - t, 2), "flashes": pg.locator(".flash").all_inner_texts()})
            pg.screenshot(path=str(out / "t6_after.png"))
            from plex_web import PlexWeb
            ok, msg = PlexWeb("test").move(picked["serial"], picked["location"])
            log("T6_put_back", {"to": picked["location"], "ok": ok, "message": msg})
    t = time.time(); pg.goto(U + "/log", timeout=120000)
    log("T7_log", {"s": round(time.time() - t, 2), "rows": pg.locator("tbody tr").count(),
                   "has_moved_serial": bool(picked) and picked["serial"] in pg.content()})
    pg.screenshot(path=str(out / "t7_log.png"))
    ctx.close()
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print("results:", out)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--move", action="store_true", help="also move one container in Plex TEST and put it back")
    ap.add_argument("--big", default="600", help="a large job set (default 600, 26 ingredients in TEST)")
    ap.add_argument("--small", help="a small job set (default: the first other one listed)")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        login(p) if a.login else run(p, a.move, a.big, a.small)
