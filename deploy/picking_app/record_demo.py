"""Record the picking app demo videos on the DEPLOYED app (Plex TEST), through IAP (2026-11-23).

Second take (2026-11-23 evening): targets from Plex history, the review dialog, undo from the Move log.
PICKING_URL=http://127.0.0.1:8088 records a local server on Plex TEST (same code, no IAP); otherwise the
deployed app with the signed-in Chrome profile. Video 3 also moves one container "as the floor" (plex_web)
to show what undo refuses. Every container moved is put back at the end.

    python deploy/picking_app/live_test.py --login                      # once: sign in (Chrome profile)
    python deploy/picking_app/record_demo.py <out_dir> 1|2|3            # one video per run (.webm)

Video 2 MOVES the suggested containers of one ingredient in Plex TEST. Put them back afterwards from
the move log's from_location (docs/PICKING_STAGING_APP.md, "Demo videos"). Captions are timed by word
count. Trim the warm-up before the title card and encode with ffmpeg (same section).
SET / PART below must be a job set with several suggested containers of one ingredient on that day.
"""
import sys, time, json
from playwright.sync_api import sync_playwright
OUT, WHICH = sys.argv[1], sys.argv[2]
U = __import__("os").environ.get("PICKING_URL", "https://picking-app-651304971296.us-central1.run.app")
SET, PART = "756", "12743-01VOXNU-1"
OVERLAY = r"""
(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id='__cur';
    c.style.cssText='position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;background:rgba(31,111,235,.35);border:2px solid #1f6feb;pointer-events:none;transform:translate(-50%,-50%);left:-50px;top:-50px;transition:left .05s,top .05s';
    document.body.appendChild(c);
    const cap = document.createElement('div'); cap.id='__cap';
    cap.style.cssText='position:fixed;z-index:99998;left:50%;bottom:22px;transform:translateX(-50%);max-width:88%;background:rgba(20,24,30,.93);color:#fff;font:600 20px/1.4 system-ui,sans-serif;padding:12px 22px;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.3);pointer-events:none;display:none;text-align:center';
    document.body.appendChild(cap);
    const tag = document.createElement('div'); tag.id='__tag';
    tag.style.cssText='position:fixed;z-index:99998;right:14px;top:58px;background:#f5a623;color:#000;font:700 13px system-ui;padding:4px 10px;border-radius:6px;pointer-events:none';
    tag.textContent = sessionStorage.getItem('__tagtext') || ''; if (tag.textContent) document.body.appendChild(tag);
    const t = sessionStorage.getItem('__captext'); if (t) { cap.textContent = t; cap.style.display='block'; }
    document.addEventListener('mousemove', e => { c.style.left=e.clientX+'px'; c.style.top=e.clientY+'px'; sessionStorage.setItem('__xy', e.clientX+','+e.clientY); }, true);
    const xy = (sessionStorage.getItem('__xy')||'').split(','); if (xy.length==2) { c.style.left=xy[0]+'px'; c.style.top=xy[1]+'px'; }
    document.addEventListener('mousedown', e => { const r=document.createElement('div');
      r.style.cssText=`position:fixed;z-index:99999;left:${e.clientX}px;top:${e.clientY}px;width:10px;height:10px;border-radius:50%;border:3px solid #f5a623;transform:translate(-50%,-50%);pointer-events:none;transition:all .6s ease-out;opacity:1`;
      document.body.appendChild(r); requestAnimationFrame(()=>{r.style.width='60px';r.style.height='60px';r.style.opacity='0'}); setTimeout(()=>r.remove(),700); }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
"""
TITLE = """(t) => { document.body.insertAdjacentHTML('beforeend', `<div id="__title" style="position:fixed;inset:0;z-index:100000;background:#111418;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;font:600 40px/1.3 system-ui;text-align:center;padding:40px">${t}</div>`); }"""
def title(pg, html, hold):
    pg.wait_for_load_state("load"); pg.evaluate(TITLE, html); time.sleep(hold); pg.evaluate("() => document.getElementById('__title')?.remove()")
def caption(pg, text, hold=None):
    pg.wait_for_load_state("load")
    pg.evaluate("t => { sessionStorage.setItem('__captext', t); const c=document.getElementById('__cap'); if(c){c.textContent=t; c.style.display=t?'block':'none';} }", text)
    time.sleep(hold if hold is not None else 1.6 + len(text.split()) / 3.2)
def glide(pg, loc, click=True, pause=0.6):
    loc.scroll_into_view_if_needed(); time.sleep(0.4)
    b = loc.bounding_box(); x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    pg.mouse.move(x, y, steps=25); time.sleep(pause)
    if click: pg.mouse.down(); pg.mouse.up()
def scroll_to(pg, loc):
    pg.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'start'})", loc.element_handle()); time.sleep(1.3)
    pg.evaluate("() => window.scrollBy({top:-70, behavior:'smooth'})"); time.sleep(0.6)
def card(pg, part):
    return pg.locator(".card[id^=line-]", has=pg.locator("b", has_text=part)).first
def wait_lines(pg):
    pg.wait_for_function("document.querySelectorAll('.line-loading').length === 0", timeout=240000)

meta = {}
LOCAL = U.startswith("http://127.0.0.1")
with sync_playwright() as p:
    if LOCAL:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1400, "height": 860}, bypass_csp=True, record_video_dir=OUT, record_video_size={"width": 1400, "height": 860})
    else:
        ctx = p.chromium.launch_persistent_context("etl-manual/picking_live_profile", channel="chrome", headless=True, bypass_csp=True,
                viewport={"width": 1400, "height": 860}, record_video_dir=OUT, record_video_size={"width": 1400, "height": 860})
    ctx.add_init_script(OVERLAY)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page(); pg.set_default_timeout(240000)
    pg.goto(U + f"/set/{SET}?days=7"); wait_lines(pg)        # warm the server and caches before the title card
    pg.goto(U + "/?days=7"); pg.evaluate("() => sessionStorage.clear()")
    sub = lambda n, t: (f"Picking &amp; Staging app<br><span style='font-size:26px;font-weight:400;color:#9aa4ae'>{n} of 3 · {t}<br>Plex TEST · "
                        + time.strftime("%Y-%m-%d") + "</span>")
    if WHICH == "1":
        pg.goto(U + "/set/544?days=14"); wait_lines(pg)               # warm set 544 too
        pg.goto(U + "/?days=14"); pg.evaluate("() => sessionStorage.clear()")
        title(pg, sub(1, "The pick list: allocations, real targets, no double counting"), 4)
        caption(pg, "Job sets due in the next two weeks, read from Plex. A job set is one blend job plus one Pre-Weigh job per ingredient: that is the pick list.")
        caption(pg, "Open job set 544.", 2)
        with pg.expect_navigation(): glide(pg, pg.locator("a[href^='/set/544']").first)
        caption(pg, "The page opens at once; each ingredient fills in with its containers, read live from Plex.", 0)
        wait_lines(pg); time.sleep(2)
        c = card(pg, "12231-01VOXNU-1"); scroll_to(pg, c)
        glide(pg, c.locator("b").first, click=False)
        caption(pg, "The floor stages per job through Plex job allocations. Job 2305's containers are already allocated to it, and already in PW - B8.")
        st = c.locator(".role.staged")
        if st.count(): glide(pg, st.first, click=False)
        caption(pg, "So they count as 'there': nothing to move. The target defaults to PW - B8, the bin where this job's containers already are.")
        c2 = card(pg, "12159-01VOXNU-1"); scroll_to(pg, c2)
        pk = c2.locator(".role.pick")
        if pk.count(): glide(pg, pk.first, click=False)
        caption(pg, "Job 2308: some of its allocated containers are still in the warehouse. Those are suggested first ('pick'), then first-expiring OK stock.")
        sel = c2.locator("select[name=target]"); glide(pg, sel, click=False, pause=1)
        caption(pg, "Targets come from Plex's history: where material used at this work center was moved before use, most used first. The PW bins for Pre-Weigh.")
        pg.goto(U + "/set/757?days=7"); wait_lines(pg); time.sleep(1)
        c3 = card(pg, PART); scroll_to(pg, c3)
        rs = c3.locator(".role.reserved")
        if rs.count(): glide(pg, rs.first, click=False)
        caption(pg, "Job set 757 needs the same ingredient as 756, from the same bin. The containers set 756 will use show as 'reserved', so no stock is counted twice.")
        caption(pg, "Containers allocated to another job are 'reserved' too, and anything not status OK is 'blocked'.")
        caption(pg, "Next: review and approve a move.", 3)
    elif WHICH == "2":
        pg.goto(U + f"/set/{SET}?days=7"); wait_lines(pg)
        title(pg, sub(2, "Review, then approve, every move"), 4)
        c = card(pg, PART); scroll_to(pg, c)
        spare = c.locator("tr", has=pg.locator(".role.spare")).locator("input[name=serial]")
        caption(pg, "For this demo we take two extra containers from the warehouse to PW - B9.")
        for i in range(2): glide(pg, spare.nth(i), pause=0.4)
        meta["serials"] = [spare.nth(i).get_attribute("value") for i in range(2)]
        b = c.locator("button", has_text="Review move"); glide(pg, b, click=False, pause=0.8)
        caption(pg, "'Review move' does not move anything yet. It reads the ticked containers live from Plex...", 2)
        pg.mouse.down(); pg.mouse.up(); pg.wait_for_selector("dialog#review[open]"); time.sleep(1)
        caption(pg, "...and lists exactly what would happen: each container, its lot and quantity, from where to where, as a container or a whole pallet.")
        glide(pg, pg.locator("#rv-body tbody tr").first, click=False)
        caption(pg, "A pallet goes as one only if exactly these containers are on it right now. A container that would leave its pallet, or may not move, is flagged here.")
        glide(pg, pg.locator("#rv-cancel"), click=False)
        caption(pg, "Cancel: nothing moves (and the cancel is logged). Approve (only by whoever opened the review): each container is read live again; anything that changed stays.")
        glide(pg, pg.locator("#rv-approve"), click=False, pause=0.8)
        t = time.time()
        with pg.expect_navigation(timeout=240000): pg.mouse.down(); pg.mouse.up()
        meta["move_s"] = round(time.time() - t, 1)
        caption(pg, f"Done in {meta['move_s']:.0f} seconds: Plex confirmed each move and the app read the new location back.", 0)
        time.sleep(1); glide(pg, pg.locator(".flash").first, click=False, pause=0.5); time.sleep(4)
        caption(pg, "Each line: Plex's answer and where the container is now. Every move is logged the moment Plex answers. The batch can be undone from the Move log for 30 minutes, if nothing touches it.")
        caption(pg, "Next: the Move log, and why undo has a limit.", 3)
    else:
        import json as _j, sys as _s
        _s.path[:0] = ["deploy/picking_app", "scripts"]
        from plex_web import PlexWeb
        serials = _j.loads(open(OUT + "/../serials.json").read())
        PlexWeb("test").move(serials[1], "PW - B10")            # "the floor" moves one of them on
        pg.goto(U + "/log")
        title(pg, sub(3, "Undo from the Move log, and its limit"), 4)
        caption(pg, "The Move log: one row per approved move, who did it and when. Plex records every move under the company user, so this is the only record of who asked.")
        caption(pg, "Meanwhile on the floor, one of the two containers was moved on to PW - B10.", 3.5)
        bt = pg.locator(".undo-btn").first; glide(pg, bt, click=False)
        caption(pg, "Undo is offered for 30 minutes after a move. 'Undo…' reads Plex first: nothing moves yet.", 2.5)
        pg.mouse.down(); pg.mouse.up(); pg.wait_for_selector("dialog#undo[open]"); time.sleep(1)
        blocked = pg.locator("#un-body > .card", has=pg.locator(".role.blocked")).first
        glide(pg, blocked, click=False)
        caption(pg, "This one was touched after our move, so it is NOT put back. Instead the app shows what Plex recorded since: when, what, where, quantity, and who.")
        caption(pg, "Why: in Plex's history, a third to a half of containers moved to the Bottling and Labeling lines change again within an hour. Undoing that would undo the floor's work.")
        ok = pg.locator("#un-body > .card", has=pg.locator(".role.pick")).first
        glide(pg, ok, click=False)
        caption(pg, "This one is exactly as we left it, with no activity since, so it can go back.")
        glide(pg, pg.locator("#un-go"), click=False, pause=0.8)
        with pg.expect_navigation(timeout=240000): pg.mouse.down(); pg.mouse.up()
        caption(pg, "Put back and confirmed. The other stays where the floor put it. After 30 minutes the button becomes 'Activity': the history, no undo.", 0)
        time.sleep(1); glide(pg, pg.locator(".flash").first, click=False, pause=0.5); time.sleep(5)
        caption(pg, "Every step is logged: the review, the cancel, the move with Plex's exact request and answer, the undo check, the undo.")
        caption(pg, "Moves stay off in production until the team confirms the targets and we do one supervised move together.", 4)
    caption(pg, "", 0.5)
    pg.close(); vid = pg.video.path(); ctx.close()
    print("VIDEO", vid); print("META", json.dumps(meta))
