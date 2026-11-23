"""Record the picking app demo videos on the DEPLOYED app (Plex TEST), through IAP (2026-11-23).

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
U = "https://picking-app-651304971296.us-central1.run.app"
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
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context("etl-manual/picking_live_profile", channel="chrome", headless=True,
            viewport={"width": 1400, "height": 860}, record_video_dir=OUT, record_video_size={"width": 1400, "height": 860})
    ctx.add_init_script(OVERLAY)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page(); pg.set_default_timeout(240000)
    pg.goto(U + f"/set/{SET}?days=7"); wait_lines(pg)        # warm the server and caches before recording starts
    pg.goto(U + "/?days=7"); pg.evaluate("() => sessionStorage.clear()")
    if WHICH == "1":
        title(pg, "Picking &amp; Staging app<br><span style='font-size:26px;font-weight:400;color:#9aa4ae'>1 of 3 · Find the pick list and read it<br>Plex TEST · " + time.strftime("%Y-%m-%d") + "</span>", 4)
        caption(pg, "The app runs on Google Cloud. Sign in with your company Google account; nothing to install.")
        caption(pg, "This page lists the job sets due in the next days, read from Plex. A job set is one blend job plus one Pre-Weigh job per ingredient: that is the pick list.")
        glide(pg, pg.locator("select[name=group]"), click=False)
        pg.select_option("select[name=group]", "Pre-Weigh"); time.sleep(0.8)
        caption(pg, "Filter to Pre-Weigh work and press Show.", 2.5)
        with pg.expect_navigation(): glide(pg, pg.locator("button", has_text="Show"))
        time.sleep(1)
        caption(pg, f"Open job set {SET}: a blend with 7 ingredients to weigh out.", 3)
        with pg.expect_navigation(): glide(pg, pg.locator(f"a[href^='/set/{SET}']").first)
        caption(pg, "The page opens at once. Each ingredient then fills in with its containers, read live from Plex as you watch (a few seconds each, never old data).", 0)
        wait_lines(pg); time.sleep(2.5)
        c = card(pg, PART); scroll_to(pg, c)
        glide(pg, c.locator("b").first, click=False)
        caption(pg, "Per ingredient: the job, its work center and due date, and the quantity needed (job quantity × BOM quantity).")
        glide(pg, c.locator("thead"), click=False)
        caption(pg, "Every container of that part in Plex: serial, pallet (LP), lot, best-by date, location, status and quantity.")
        glide(pg, c.locator(".role.pick").first, click=False)
        caption(pg, "'pick' = suggested: status OK, in a Warehouse location, first-expiring lot first, until the quantity needed is covered. Those boxes come ticked.")
        sp = c.locator(".role.spare").first
        if sp.count(): glide(pg, sp, click=False); caption(pg, "'spare' = OK but not needed. Tick it if you want it too.")
        caption(pg, "Other labels: 'staged' (already there), 'blocked' (Hold or other status), 'not-here' (retains, R and D...). Those are never ticked.")
        caption(pg, "Next video: move them all with one click.", 3)
    elif WHICH == "2":
        pg.goto(U + f"/set/{SET}?days=7"); wait_lines(pg)
        title(pg, "Picking &amp; Staging app<br><span style='font-size:26px;font-weight:400;color:#9aa4ae'>2 of 3 · Stage a whole ingredient in one click<br>Plex TEST · " + time.strftime("%Y-%m-%d") + "</span>", 4)
        c = card(pg, PART); scroll_to(pg, c)
        n = c.locator(".role.pick").count()
        caption(pg, f"Today, each container is moved on its own in Plex's Move Container screen: find it, enter the location, confirm. This ingredient alone is {n} containers.")
        for i in range(n): glide(pg, c.locator(".role.pick").nth(i), click=False, pause=0.25)
        caption(pg, f"Here the {n} suggested containers are already ticked. Pick the staging location...")
        glide(pg, c.locator("select[name=target]"), click=False, pause=1)
        caption(pg, "...and press 'Move to staging' once.", 2)
        b = c.locator("button", has_text="Move to staging"); glide(pg, b, click=False, pause=1)
        caption(pg, f"Moving {n} containers in Plex: each is re-read live first, moved through Plex's own Move Container request, then read back to confirm.", 1.5)
        t = time.time()
        with pg.expect_navigation(timeout=240000): pg.mouse.down(); pg.mouse.up()
        secs = time.time() - t; meta["moved_n"], meta["move_s"] = n, round(secs, 1)
        caption(pg, f"Done: {n} containers moved and confirmed in {secs:.0f} seconds, with one click.", 0)
        time.sleep(1.5); glide(pg, pg.locator(".flash").first, click=False, pause=0.5); time.sleep(4)
        caption(pg, "Each line says what Plex answered and where the container is now. The last line totals it.")
        wait_lines(pg)
        c = card(pg, PART); scroll_to(pg, c)
        st = c.locator(".role.staged")
        if st.count(): glide(pg, st.first, click=False)
        caption(pg, "The ingredient now shows them as 'staged', and its quantity needed is covered.")
        caption(pg, "A pallet (LP) moves as a whole when all its containers are ticked. A container moved alone leaves its pallet, and the app says so.")
        caption(pg, "Next video: what the app refuses to move, and the move log.", 3)
    else:
        pg.goto(U + f"/set/{SET}?days=7"); wait_lines(pg)
        title(pg, "Picking &amp; Staging app<br><span style='font-size:26px;font-weight:400;color:#9aa4ae'>3 of 3 · Safety rules and the move log<br>Plex TEST · " + time.strftime("%Y-%m-%d") + "</span>", 4)
        bl = pg.locator(".role.blocked").first
        if bl.count():
            scroll_to(pg, bl); glide(pg, bl, click=False)
            caption(pg, "Blocked: this container is not status OK (Hold, Quarantine...). It has no tick box. Plex itself would move a Hold container without asking; the app refuses.")
        nh = pg.locator(".role.not-here").first
        if nh.count():
            scroll_to(pg, nh); glide(pg, nh, click=False)
            caption(pg, "Not-here: this stock sits in a location we don't pick from (retains, R and D...), so it is never suggested.")
        caption(pg, "Before every move the app reads the container live again: only status OK, quantity above zero and not already there is moved.")
        caption(pg, "Moves run on Plex TEST for now. In production they stay off until the team turns them on.")
        with pg.expect_navigation(): glide(pg, pg.locator("header nav a", has_text="Move log"))
        caption(pg, "Plex records every move under the company user, so this log is the only record of who asked. Each row: when, who, set, job, container, from, to, Plex's answer, and where it is now.")
        caption(pg, "The same log is kept in BigQuery (PlexOps.picking_move_log) for reports.")
        caption(pg, "Questions for the team: which staging location per area, the PW and PS bins, Lot Hold, and who should use it first.", 4)
    caption(pg, "", 0.5)
    pg.close(); vid = pg.video.path(); ctx.close()
    print("VIDEO", vid); print("META", json.dumps(meta))
