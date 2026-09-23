# The Migration Board generator

The shared status page lives at
**https://claude.ai/code/artifact/89e5211a-10c8-4a59-bf3d-c92f188c47a9** and is
built from these two files rather than hand-edited.

```bash
python scripts/board/build_board.py     # writes migration_board.html next to it
```

Then publish that file **to the same URL**. Jennilyn and others hold that link;
publishing a new artifact instead of updating this one leaves them on a stale
page with no way to tell.

## Which file to edit

| | |
|---|---|
| `board_data.py` | All the content — tiles, glossary, open decisions, forms, hand-maintained tables, the recent-changes list. **This is the one you want.** |
| `build_board.py` | Layout, palette, behaviour. Only touch it to change how the page looks. |

The split exists because the content changes weekly and the design does not.

## The conventions worth keeping

**Retire answered questions, don't archive them.** Emilio's rule: *"there is no
value in having questions that are not a problem any more."* When a decision is
made, delete it from `FLAGS` and, if it changed something, add a line to
`RECENT` instead.

**Never frame something as a blocker without checking it still is.** The
Monday.com item sat as a red conflict callout until it turned out the blend was
by design.

**Say what is real and what is not.** Every tile carries a `kind` — `real` for
Vox's own data, `injected` for rows put there by
`scripts/scorecard_test_data.py` to prove the wiring. A test figure presented
as a business figure is worse than a blank tile.

**Plain English first.** The page is written for someone who has never opened
BigQuery. Each tile leads with the question it answers, not the view that
answers it, and every term that has ever needed explaining is in the glossary
with a "why it matters here" line.

## One job each

This page is **status**. Understanding — how each tile is built and what might
be wrong about it — lives in the Scorecard Field Manual
(`https://claude.ai/code/artifact/2e629322-e24f-4402-87bd-77217143011a`). They
were merged from two boards that tracked the same work from different angles,
which meant a question could be answered in one and still look open in the
other. Keep them separate.
