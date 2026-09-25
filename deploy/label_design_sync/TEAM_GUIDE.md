# Label Design queue — how to use it (team guide)

> **Being retired (2026-09-25).** This describes the Sheet-based flow, which the push service (`label_design_service/push.py`) replaces once it is scheduled in prod. It stays accurate for the Apps Script that is still live until then. Current status: [`label-design/STATUS.md`](../../label-design/STATUS.md).

This is the plain-English version. For the technical design, see
[README.md](./README.md) in this same folder.

## What this replaces

You used to: pull a report from NetSuite by hand, paste it into a sheet,
scan it for duplicates yourself, then copy the new ones over to Monday.com
one at a time.

Now: a computer job checks Plex for new Label Design orders automatically,
twice a day, and drops the new ones into a tab called **`MONDAY`** for you to
review. When you're happy with a batch, you press one button and it sends
everything on that tab to the Monday.com board and files it away.

## The two buttons

Open the spreadsheet, and at the top you'll see a menu called
**"Label Design Sync"** (next to File, Edit, View, etc. — it appears
automatically, you don't need to install anything). Click it to see:

| Button | What it does | When to use it |
|---|---|---|
| **1) Check for new orders** | Looks in Plex for anything new and adds it to the `MONDAY` tab. | You don't usually need this — it already runs by itself at **10am and 2pm every day**. Use it if you want to check "right now" instead of waiting for the next automatic run. |
| **2) Push to Monday & Archive** | Takes everything currently on the `MONDAY` tab and sends it to the Monday.com board. Once sent, those rows move off `MONDAY` and into the `historical` tab (the permanent record). | Press this **after you've reviewed a batch** — filled in things like Reason Code, Label, Bottle Material, Prop 65, LCR — and you're ready for the design team to see it on Monday.com. |

That's the whole workflow:

```
New Plex orders  →  land on "MONDAY" tab  →  you review/fill in a few columns  →  press "Push to Monday & Archive"  →  they show up on Monday.com and move to "historical"
```

## Important things to know

- **Pressing "Push to Monday & Archive" clears the `MONDAY` tab** (of the
  rows it successfully sent) — that's expected. It's not deleting your work;
  it's moving those rows into `historical`, which is the permanent archive.
- **It's safe to press it more than once.** If you're not sure whether the
  last click actually finished, just press it again — it will not create
  duplicate entries on Monday.com or duplicate rows in the archive. It
  simply picks up wherever it left off.
- **If you click "Push" while a check is still running (or vice versa),
  nothing bad happens** — the system makes them wait their turn instead of
  stepping on each other.
- **The `historical` tab is a read-only record from the system's point of
  view** — the *only* way a row gets added to it is by pressing "Push to
  Monday & Archive." Nothing else in this project ever writes to it, so you
  can trust it as the single source of truth for "what's already been sent."
- **You'll get an email after every button click (and every automatic run)**
  telling you what happened — how many new orders were found, how many were
  pushed, how many were archived, and any problems. If something's wrong,
  it'll say so clearly rather than failing silently.
- **Fill in the review columns on the `MONDAY` tab before pressing Push**,
  not after — Reason Code, Label, Bottle Material, Prop 65, and LCR. Whatever
  is in those cells at the moment you press the button is what gets sent to
  Monday.com and archived. If you press Push and then remember something you
  forgot to fill in, you'll need to update it on the Monday.com board
  directly (the row has already left the sheet).

## Do I need to create the buttons myself?

**No — nothing to build.** The "Label Design Sync" menu appears automatically
in the spreadsheet's menu bar every time it's opened; that's the two buttons.
There's no setup step for this and no button to draw or wire yourself.

### Optional: a bigger, clickable button on the sheet itself

If the team would prefer an actual on-sheet button (like a colored rectangle
you click, rather than using the menu), that's easy to add and doesn't
replace the menu — it's just a second way to trigger the same thing:

1. In the spreadsheet, go to **Insert → Drawing**.
2. Draw a simple shape or text box (e.g. a rectangle that says "Check for
   New Orders" or "Push to Monday & Archive"), then click **Save and Close**.
3. Click the new shape once to select it, then click the **⋮ (three dots)**
   in its top-right corner → **Assign script**.
4. Type in exactly one of these two names (no parentheses, no quotes):
   - `checkForNewOrdersManual` — for a "Check for new orders" button
   - `pushToMondayAndArchiveManual` — for a "Push to Monday & Archive" button
5. Click **OK**. The shape now runs that action whenever it's clicked, and
   you can resize/move/style it like any drawing, or duplicate it and repeat
   the steps for the second button.

If you ever do this and the button stops responding, the most likely cause
is the drawing got copied to a new sheet/tab without carrying its script
assignment along — just repeat steps 3–4 on the copy. The menu at the top
never has this problem, so it's the one to rely on if a drawing goes stale.

## Who to contact

If an email says there's a **problem** (not just "nothing new today," which
is normal), or if a button doesn't seem to do anything, reach out to Emilio
— the technical README in this folder has the full troubleshooting detail.
