"""Move containers (or whole LPs) in Plex from the command line, verified, with an undo file.

    python deploy/picking_app/move_cli.py --to "Pre-Weigh Staging" 84F47G-0003 LP-087265
    python deploy/picking_app/move_cli.py --undo etl-manual/picking_undo_20261120_1830.json

TEST by default (PLEX_ENV=test). --prod moves in production and asks you to type PROD.
Each serial is read live from the API first and moved only when status OK (unless --any-status);
an LP is moved as a whole pallet. After the move the API is read again. An undo file records
where every moved container was, so --undo puts them back.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import picking  # noqa: E402
from plex_api import PlexApi  # noqa: E402
from plex_web import PlexWeb  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "etl-manual"


def lp_members(api: PlexApi, lp: str, hint_part: str | None = None) -> list[dict]:
    """Containers on an LP. The API ignores ?masterUnitNo=, so this pulls the full list once."""
    return [c for c in api.get("/inventory/v1/inventory-tracking/containers") or [] if c.get("masterUnitNo") == lp]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("serials", nargs="*")
    ap.add_argument("--to", dest="target")
    ap.add_argument("--undo", help="undo file written by an earlier run")
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--any-status", action="store_true", help="also move Hold / Quarantine / ... containers")
    a = ap.parse_args()
    env = "prod" if a.prod else os.environ.get("PLEX_ENV", "test")
    if env == "prod" and input("Moving containers in PRODUCTION. Type PROD to go on: ").strip() != "PROD":
        return 2
    api, web = PlexApi(env), PlexWeb(env)

    plan = []           # (serial_or_lp, target, [(serial, from_location)])
    if a.undo:
        for serial, frm in json.loads(Path(a.undo).read_text())["moved"]:
            plan.append((serial, frm, [(serial, None)]))
    else:
        if not (a.target and a.serials):
            ap.error("give --to and at least one serial or LP (or --undo)")
        for s in a.serials:
            if s.upper().startswith("LP-"):
                members = lp_members(api, s)
                if not members:
                    print(f"{s}: no containers on this LP; skipped"); continue
                plan.append((s, a.target, [(m["serialNo"], m["location"]) for m in members]))
            else:
                live = api.container(s)
                why = picking.check_movable(live, a.target, allow_status={(live or {}).get("containerStatus")}
                                            if a.any_status else picking.MOVABLE_STATUSES)
                if why:
                    print(f"{s}: not moved: {why}"); continue
                plan.append((s, a.target, [(s, live["location"])]))

    moved = []
    for what, target, members in plan:
        ok, msg = web.move(what, target)
        print(f"{what} -> {target}: {'OK' if ok else 'FAILED'}: {msg}")
        for serial, frm in members:
            now = (api.container(serial) or {}).get("location")
            print(f"   {serial}: now at {now}{'' if now == target else '  <-- NOT at target'}")
            if ok and frm and frm != target:
                moved.append((serial, frm))
    if moved and not a.undo:
        OUT.mkdir(exist_ok=True)
        f = OUT / f"picking_undo_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
        f.write_text(json.dumps({"env": env, "moved": moved}, indent=1))
        print(f"undo file: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
