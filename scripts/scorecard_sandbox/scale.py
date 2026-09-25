"""
How big the simulated business is — every figure taken from Vox's own live
scorecard, not chosen. Sources are the navigator snapshot ("Data Last Updated
7/31/2026") in score-card-reference/vox_scorecard_navigator.html and the
Vox_Scorecard_Data_Mapping workbook in the same folder.

The simulation is shaped so that, month by month, the SANDBOX tiles land in the
same neighbourhood as those figures. It does not reproduce them — the goal is
a scorecard whose numbers are plausible enough to design against, where a
chart axis, a % to goal and a KPI tile all behave as they will at go-live.
"""

# ── Sales and revenue ──────────────────────────────────────────────────────
# Sales MTD $4,880,519 vs $4.8M goal (103%); Revenue MTD $4,109,322 vs $4.7M
# goal (88%), 94% into the month. Rep goals come from the real goals table,
# so per-rep sales are driven by each rep's actual goal (see sales.py).
REP_ATTAINMENT = (0.78, 1.18)       # monthly sales / goal, drawn per rep-month
UNASSIGNED_SHARE = 0.06             # share of sales on orders with no rep
# Booked -> shipped, days, as random.triangular(low, high, mode). Sized so the
# unshipped balance at any moment lands near the live WIP of $4.92M on ~$4.9M
# of monthly sales — i.e. roughly a month of bookings in flight.
SHIP_LAG_DAYS = (8, 60, 24)
# Shipments dated within this many days of today are packed and on the dock
# but not yet shipped — what "Total in Shipping" counts.
IN_SHIPPING_DAYS = 6
LINES_PER_ORDER = (1, 4)

# Order book at a point in time. WIP $4.92M; Total in Shipping $1,044,808;
# NS Pending SOs $821.62K; NS Quotes $63.04K.
WIP_TARGET = 4_920_000
IN_SHIPPING_TARGET = 1_044_808
PENDING_APPROVAL_TARGET = 821_620
QUOTES_TARGET = 63_040
DEPOSIT_REVIEW_ORDERS = 6           # not on the old scorecard; a handful

# ── Production, per work centre group, per month ───────────────────────────
# Encapsulation 106.65M caps vs 100.00M goal; Bottling 1.67M vs 1.50M;
# Labeling 892.17K vs 700.00K. The goals ARE the live scorecard's goals.
PRODUCTION_GOALS = {
    "Encapsulating": 100_000_000,
    "Bottling": 1_500_000,
    "Labeling": 700_000,
}
PRODUCTION_ATTAINMENT = (0.86, 1.14)
# FPY: Encapsulation 91.06%, Bottling 99.88%, Labeling 99.38%.
FPY = {"Encapsulating": 0.9106, "Bottling": 0.9988, "Labeling": 0.9938}
# Groups the old scorecard never showed still run, at a small scale, so the
# by-group tile has the long tail it will have in production.
MINOR_GROUPS = {"Blending": 2_500_000, "Pre-Weigh": 1_800_000, "Printing": 900_000}
# Open Caps 219.7M; Open Bottles 1.2M.
OPEN_CAPS_TARGET = 219_700_000
OPEN_BOTTLES_TARGET = 1_200_000

# ── Quality ────────────────────────────────────────────────────────────────
# 18 reworks and 19 deviations in the month; TAT 4–10.7 work days by stock type.
NC_PER_MONTH = (14, 22)
DEVIATIONS_PER_MONTH = (15, 21)
TAT_DAYS = (2, 18)

# ── Inventory ──────────────────────────────────────────────────────────────
# Out of stock: 6 on the tile. Cycle count accuracy 0.987.
OUT_OF_STOCK_PARTS = 6
CYCLE_ACCURACY = 0.987
CYCLE_COUNTS_PER_MONTH = (40, 70)

# ── Safety ─────────────────────────────────────────────────────────────────
# Last OSHA recordable 7/23/2026, 8 safe days on 7/31.
LAST_RECORDABLE = "2026-07-23"
