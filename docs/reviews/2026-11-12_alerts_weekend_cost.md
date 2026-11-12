# Review: alerts, weekend schedule and cost cuts (2026-11-12)

Two independent reviews of PRs #147 and #148 were run on 11-12:
- a Sonnet review at high effort, which read the diff, ran the tests and made read-only BigQuery checks;
- an Opus review at low effort, a fast high-level read.

Neither found a blocker. This page lists what they found and what was done with it.

| # | Finding | Severity | From | Done |
|---|---|---|---|---|
| 1 | The freeze test claimed the real 11-10 freeze would alert; at 4.5 h it is under the 6 h line | medium | Sonnet | The test was renamed, and a "4.5 h is quiet by design" case added. The limit is documented in ODBC_VS_SCREENS.md |
| 2 | An overnight refresh landing after 04:00 could mail a false alarm at the 04:xx load (one night of evidence only) | medium | Sonnet | `odbc_vs_plex` mails only on weekdays 06:00-18:00 MT; outside those hours it logs `pending:` |
| 3 | A dead Plex API silently turns `odbc_vs_plex` off | medium | both | It now reports that the check is blind: pending, then mailed. A short answer (under 100 orders) counts as unreadable |
| 4 | The measure covers sales orders only; production- or shipments-only lag is not seen by it | medium | both | Documented as a limit. Still covered by the screens' revenue and shipments comparison and by raw freshness |
| 5 | The stale email called the API on every prod run, even outside its window | medium | Sonnet | It now asks only inside weekdays 9-5 |
| 6 | Breaker-held "skipped" runs counted as an ODBC read | low | Sonnet | They are excluded (`detail` starting "Held") |
| 7 | "Two in a row" adds little when `as_of` does not move (weekends) | low | Sonnet | Accepted. The working-hours rule now covers weekends |
| 8 | With no test retries, one-off test failures stay failed; the message said "expect 15" | low | Sonnet | Accepted (the retries never actually fired; see OPERATIONS.md). The message now says 14 |
| 9 | If a plant works weekends, production reports can be up to ~19 h old on Saturday and Sunday | business | Sonnet | **Open question for Emilio and Jennilyn** |
| 10 | Doc drift: retry mentions in CHANGELOG, OPERATIONS.md and a Terraform comment | low | Sonnet | Fixed |
| 11 | Check whether `/sales/v1/orders` pages its results | low | Opus | Checked by the 11-11 survey: paging parameters are ignored, every order comes back (640). The short-answer guard covers a change |
| 12 | Verify the first weekend: two probes per job Saturday and Sunday, full Monday 04:xx | follow-up | Opus | On the monitoring list for 11-14 to 11-16 |

**Verified as solid by the reviews:**
- the dispatcher's `days` logic, including the Friday/Saturday midnight edges, DST and Monday's full run;
- the watchdog windows against the new crons and the Monitoring heartbeats;
- the Terraform plan shape: 12 destroys, 2 creates and about 14 in-place updates;
- the timezone handling;
- the cost arithmetic.

## Part 2: probe runs re-extract only changed tables (commit bc0f2aa)

A Sonnet review (read-only, with tests) and a Sonnet measurement from `probe_log`. No blockers.

| # | Finding | Severity | Done |
|---|---|---|---|
| 1 | Probe columns (COUNT plus MAX/SUM) can miss an edit that keeps those aggregates; before, a daily `Part_v_Part` change refreshed everything as a side effect | high (accepted trade-off) | Documented. Every weekday 04:xx full run refreshes everything (Monday after a weekend), and `PROBE_PER_TABLE=0` turns it off. The Flat_BOM probe was strengthened |
| 2 | `sum:Lead_Time_Days` is always 0 | medium | Replaced with `Part_Key` (MAX) and `sum:BOM_Level` |
| 3 | `raw_freshness` slack is thinner, since only full runs touch kept tables | medium | Weekend allowance 80 h → 84 h; a failed Monday full run still alerts that morning (a real signal) |
| 4 | Date-window filters could slide without the aggregates moving | medium | Rows leaving a window change COUNT, so the probe sees them; the 04:xx full run is the backstop |
| 5 | No test of the main loop with kept tables | low | Accepted; the paths were reviewed: kept tables are `ok`, not partial, not failed |
| 6 | The email header counts kept tables as OK with 0 rows | low | Accepted; they are listed as "unchanged, kept" |

**Measurement:**
- Probe runs that extracted changed on average 3.9 of 18 tables (part_routing), 14.2 of 29
  (sales_orders), 7.7 of 22 (part_lot) and 6.3 of 15 (work_orders).
- Savings: ~$0.10 a month as a lower bound, ~$1 a month apportioned by unchanged rows. The main gain
  is less Plex load and shorter runs.
- Flat_BOM was never the only changed table, and its content does not move on weekends.
