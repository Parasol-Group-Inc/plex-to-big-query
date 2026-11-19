#!/usr/bin/env python3
"""The "Pending" tab of the Plex Data Hub (2026-11-19): everything waiting on someone, with buttons.

Unlike the other tabs, its content is not in the page. Items live in the artifact's shared database
(the `db` capability, collection `pending`), so a viewer can mark one done, waiting or not needed and
add notes (collection `pending_notes`), and Claude reads both back with ArtifactData to act on them.
The page only holds the code. The items Claude seeded are kept in docs/hub/pending_seed.json for the
record; Claude writes them to the database after a publish, never the page.

The hub must be published with capabilities
    {"db": {"rules": [{"path": "pending", "read": "view", "write": "interact"},
                      {"path": "pending_notes", "read": "view", "write": "interact"}]},
     "user": {"scopes": ["profile"]}}
(a redeploy that omits `capabilities` keeps them). Outside claude.ai, or signed out, the tab says so.

Item document (`pending/<id>`): title, kind (merge|send|decide|access|run|check), owner, status
(open|waiting|done|dropped), origin {date, source, ref}, context, action, links [{label, url}], order,
status_by (user id), status_at (ISO). Note document (`pending_notes/<auto>`): item, text, by, at.
"""
from __future__ import annotations

import re
import sys

START, END = "<!--pending-tab-start-->", "<!--pending-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "pending", "Pending"

CAPABILITIES = {"db": {"rules": [{"path": "pending", "read": "view", "write": "interact"},
                                 {"path": "pending_notes", "read": "view", "write": "interact"}]},
                "user": {"scopes": ["profile"]}}

CSS = """
<style>
#s-pending .pd-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:4px 0 14px}
#s-pending .pd-top .sp{flex:1}
#s-pending .pd-f button{border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:4px 12px;cursor:pointer;font:inherit;font-size:13px;color:var(--ink);min-height:32px}
#s-pending .pd-f button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
#s-pending .pd-msg{padding:14px 16px;border:1px dashed var(--line);border-radius:8px;color:var(--muted);background:var(--surface)}
#s-pending .pd-card{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:14px 16px;margin:0 0 12px}
#s-pending .pd-card[data-status=waiting]{border-left-color:var(--warn)}
#s-pending .pd-card[data-status=done]{border-left-color:var(--ok);opacity:.8}
#s-pending .pd-card[data-status=dropped]{border-left-color:var(--line);opacity:.7}
#s-pending .pd-h{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
#s-pending .pd-h h3{margin:0;font-size:15.5px;flex:1 1 280px}
#s-pending .pd-meta{font-size:12.5px;color:var(--muted);margin:6px 0 0}
#s-pending .pd-sec{margin:10px 0 0;font-size:14px;line-height:1.5}
#s-pending .pd-sec b{display:block;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:2px}
#s-pending .pd-act{white-space:pre-wrap;word-break:break-word;background:var(--code-bg);border-radius:6px;padding:8px 10px;font-family:var(--f-mono);font-size:12.5px}
#s-pending .pd-btns{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}
#s-pending .pd-btns .btn{min-height:32px}
#s-pending .pd-btns .btn.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
#s-pending .pd-notes{margin:10px 0 0;border-top:1px solid var(--line);padding-top:8px}
#s-pending .pd-note{font-size:13px;margin:4px 0}
#s-pending .pd-note span{color:var(--muted);font-size:12px}
#s-pending .pd-add{display:flex;gap:6px;margin-top:6px}
#s-pending .pd-add textarea{flex:1;min-height:36px;font:inherit;font-size:13px;border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--surface);color:var(--ink);resize:vertical}
#s-pending .pill.st-open{background:var(--accent-soft);color:var(--accent)}
#s-pending .pill.st-waiting{background:var(--warn-soft);color:var(--warn)}
#s-pending .pill.st-done{background:var(--ok-soft);color:var(--ok)}
#s-pending .pill.st-dropped{background:var(--code-bg);color:var(--muted)}
</style>
"""

JS = r"""
<script>
(() => {
  const root = document.getElementById("pd-root"), list = document.getElementById("pd-list");
  const KIND = {merge: "Merge", send: "Send", decide: "Decide", access: "Access", run: "Run", check: "Check"};
  const ST = {open: "Open", waiting: "Waiting", done: "Done", dropped: "Not needed"};
  let items = [], notes = [], filt = "active", owner = "", db = null, user = null, myId = null, names = {};
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const when = iso => { try { return new Date(iso).toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"}); } catch (e) { return ""; } };
  const msg = t => { list.innerHTML = `<div class="pd-msg">${esc(t)}</div>`; };
  const nm = id => id === "claude" ? "Claude" : (names[id] || "Someone");
  async function resolve(ids) {
    ids = [...new Set(ids.filter(i => i && i !== "claude" && !(i in names)))];
    if (!ids.length || !user) return;
    try { const ps = await user.profiles(ids); for (const i of ids) names[i] = (ps[i] && ps[i].name) || "Someone"; } catch (e) {}
  }
  function render() {
    const owners = [...new Set(items.map(i => i.owner).filter(Boolean))].sort();
    document.getElementById("pd-owner").innerHTML = `<option value="">Everyone</option>` + owners.map(o => `<option${o === owner ? " selected" : ""}>${esc(o)}</option>`).join("");
    const keep = i => (filt === "active" ? ["open", "waiting"].includes(i.status || "open") : filt === "closed" ? ["done", "dropped"].includes(i.status) : true) && (!owner || i.owner === owner);
    const shown = items.filter(keep).sort((a, b) => (a.order || 999) - (b.order || 999));
    const open = items.filter(i => ["open", "waiting"].includes(i.status || "open")).length;
    document.getElementById("pd-count").textContent = `${open} open of ${items.length}`;
    if (!shown.length) { msg(items.length ? "Nothing here with these filters." : "No items yet. Claude adds them to this list."); return; }
    list.innerHTML = shown.map(i => {
      const st = i.status || "open", o = i.origin || {};
      const ns = notes.filter(n => n.item === i.id).sort((a, b) => String(a.at).localeCompare(String(b.at)));
      const links = (i.links || []).filter(l => /^https:\/\//.test(l.url || "")).map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label || l.url)}</a>`).join(" · ");
      const btn = (s, label) => `<button type="button" class="btn${st === s ? " on" : ""}" data-act="status" data-s="${s}" data-id="${esc(i.id)}" aria-pressed="${st === s}">${label}</button>`;
      return `<div class="pd-card" data-status="${st}">
        <div class="pd-h"><h3>${esc(i.title)}</h3><span class="pill st-${st}">${ST[st] || st}</span><span class="tag">${esc(KIND[i.kind] || i.kind || "")}</span><span class="tag">${esc(i.owner || "")}</span></div>
        <p class="pd-meta">Origin: ${esc(o.date || "")}${o.source ? " · " + esc(o.source) : ""}${o.ref ? " · " + esc(o.ref) : ""}${i.status_at ? ` · ${ST[st]} ${when(i.status_at)} by ${esc(nm(i.status_by))}` : ""}</p>
        ${i.context ? `<div class="pd-sec"><b>Context</b>${esc(i.context)}</div>` : ""}
        ${i.action ? `<div class="pd-sec"><b>What to do</b><div class="pd-act">${esc(i.action)}</div></div>` : ""}
        ${links ? `<div class="pd-sec">${links}</div>` : ""}
        <div class="pd-btns">${btn("done", "Done")}${btn("waiting", "Waiting on someone")}${btn("dropped", "Not needed")}${st !== "open" ? btn("open", "Reopen") : ""}${i.action ? `<button type="button" class="btn" data-act="copy" data-id="${esc(i.id)}">Copy</button>` : ""}</div>
        <div class="pd-notes">${ns.map(n => `<p class="pd-note">${esc(n.text)} <span>· ${esc(nm(n.by))}, ${when(n.at)}</span></p>`).join("")}
          <div class="pd-add"><textarea aria-label="Note for ${esc(i.title)}" placeholder="Add a note (Claude reads these)"></textarea><button type="button" class="btn" data-act="note" data-id="${esc(i.id)}">Add note</button></div></div>
      </div>`;
    }).join("");
  }
  list.addEventListener("click", async e => {
    const b = e.target.closest("button[data-act]"); if (!b || !db) return;
    const id = b.dataset.id, it = items.find(x => x.id === id); if (!it) return;
    b.disabled = true;
    try {
      if (b.dataset.act === "status") {
        await db.collection("pending").doc(id).update({status: b.dataset.s, status_by: myId || "", status_at: new Date().toISOString()});
      } else if (b.dataset.act === "note") {
        const ta = b.parentElement.querySelector("textarea"), text = ta.value.trim();
        if (text) { await db.collection("pending_notes").add({item: id, text: text.slice(0, 2000), by: myId || "", at: new Date().toISOString()}); ta.value = ""; }
      } else if (b.dataset.act === "copy") {
        await navigator.clipboard.writeText(it.action); b.textContent = "Copied";
        setTimeout(() => { b.textContent = "Copy"; }, 1500);
      }
    } catch (err) {
      alert(err && err.code === "permission_denied" ? "You can view this list but not change it." : "Could not save: " + ((err && err.message) || err));
    } finally { b.disabled = false; }
  });
  document.getElementById("pd-filter").addEventListener("click", e => {
    const b = e.target.closest("button[data-f]"); if (!b) return;
    filt = b.dataset.f;
    document.querySelectorAll("#pd-filter button").forEach(x => x.setAttribute("aria-pressed", x === b));
    render();
  });
  document.getElementById("pd-owner").addEventListener("change", e => { owner = e.target.value; render(); });
  msg("Loading…");
  (async () => {
    const timer = setTimeout(() => { if (!items.length) msg("The list did not load. Open the hub in claude.ai, signed in, to see it."); }, 10000);
    db = window.claude && window.claude.use ? await window.claude.use("db") : null;
    if (!db) { clearTimeout(timer); msg("This list lives in the hub's shared data. Open the hub in claude.ai, signed in, to see and update it."); return; }
    user = await window.claude.use("user");
    try { myId = user ? await user.id() : null; } catch (e) {}
    db.collection("pending").onSnapshot(async s => {
      clearTimeout(timer);
      items = s.docs.map(d => Object.assign({id: d.id}, d.data()));
      await resolve(items.map(i => i.status_by)); render();
    }, err => { clearTimeout(timer); msg("Could not read the list: " + ((err && err.message) || err)); });
    db.collection("pending_notes").onSnapshot(async s => {
      notes = s.docs.map(d => Object.assign({id: d.id}, d.data()));
      await resolve(notes.map(n => n.by)); render();
    }, () => {});
  })();
})();
</script>
"""


def render_tab() -> str:
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref" id="pd-root">{CSS}
<div class="block"><h2>Pending: what is waiting, on whom, and why</h2>
<p class="lede">Every open item from the work log, OPEN_ITEMS and our conversations, with where it came from and what to do.
Mark one Done, Waiting or Not needed, or leave a note: Claude reads these and picks up from them.</p>
<div class="pd-top"><div class="pd-f" id="pd-filter" role="group" aria-label="Show">
<button type="button" data-f="active" aria-pressed="true">Open</button><button type="button" data-f="closed" aria-pressed="false">Closed</button><button type="button" data-f="all" aria-pressed="false">All</button></div>
<label>Owner <select id="pd-owner" class="btn"></select></label><span class="sp"></span><span class="tag" id="pd-count"></span></div>
<div id="pd-list"></div></div>
{JS}</div></section>{END}"""


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(f', ["{KEY}", "{LABEL}", ""]', "").replace(f'  if (k === "{KEY}") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + f', ["{KEY}", "{LABEL}", ""]')
    page = page.replace(STATS, f'  if (k === "{KEY}") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    return inject(live, render_tab())


if __name__ == "__main__":
    sys.exit(__doc__)
