# Monday Board Catalog — "Design & QA"

**Board:** Design & QA · **ID:** `18395121955` · **URL:** https://voxnutrition-company.monday.com/boards/18395121955

Technical reference — every column's real id, type, and (for status/dropdown
columns) the complete option list, pulled directly from the board via a
read-only GraphQL call on 2026-09-14. For the plain-language version of what
this board is *for*, see [`monday_board_guide.md`](monday_board_guide.md).

**Why this exists:** Monday's column ids are per-board and are **not** the
column titles — a column titled "Sales Order" might be `text_mkzkhws2` on this
board and something else entirely on a different one. `pushToMonday_()` in
[`deploy/label_design_sync/Code.gs`](../deploy/label_design_sync/Code.gs)
needs the real ids to write to the right place; this file is where they're
recorded so nobody has to re-query the board to find them again.

**Regenerating this:** a read-only query, no writes —

```graphql
query {
  boards (ids: [18395121955]) {
    name
    columns { id title type settings_str }
  }
}
```

or run `listMondayColumns()` from the Apps Script editor (see
[`deploy/label_design_sync/README.md`](../deploy/label_design_sync/README.md)),
which prints the same thing plus a ready-to-paste `MONDAY_COLUMNS` map.

## All 43 columns

| Title | id | Type |
|---|---|---|
| Label SKU | `name` | name *(the item's own title)* |
| Customer Name | `text_mkzmk341` | text |
| Edit Management | `color_mkzkg2wz` | status |
| Priority | `color_mkzvyt93` | status |
| Date | `date_mm07aq60` | date |
| Timeline | `timeline` | timeline |
| Designer | `person` | people |
| Design Status | `status7` | status |
| Description | `text_mkzhp1by` | text |
| Customer Label Files | `file_mkzhk3qf` | file |
| Global Vision Report | `file_mkzhk7c` | file |
| Design File | `file_mkzhm483` | file |
| Item | `text_mm07m2ht` | text |
| PDP or Prop 65 Letters | `file_mm0nmps` | file |
| Edit Requests | `long_text_mm5ft9x3` | long_text |
| Customer Requests | `text_mkzkt93` | text |
| Sales Order | `text_mkzkhws2` | text |
| WO Number | `text_mkzk1d9r` | text |
| Memo | `text_mkzkysh6` | text |
| Asset Status | `status` | status |
| Reason Code | `color_mkzk1b5m` | status |
| Design Total Days | `formula_mm0gw4c6` | formula |
| QA Lead | `multiple_person_mkzknv35` | people |
| QA Status | `status9` | status |
| QA Notes | `text_mkzkc7yr` | text |
| Label Disposition | `color_mkzk738g` | status |
| Customer Approval | `color_mkzk6gt5` | status |
| Customer Signoff | `file_mkzkedj8` | file |
| Email | `email_mkzk909j` | email |
| Phone | `numeric_mm07acsq` | numbers |
| Labels Inventory | `color_mkzketj9` | status |
| Files Released on Drive | `color_mkzkje5m` | status |
| Form: Customer Approval | `link_mkzkqp9a` | link |
| Create QA Form | `color_mm01v9gz` | status |
| LCR | `text_mkzkdqrw` | text |
| Bottle Material | `color_mkzvbses` | status |
| Label | `text_mkzze7wm` | text |
| Barcode | `text_mkzvhyaz` | text |
| RA Lead | `multiple_person_mkzk5zt0` | people |
| Aux. QA Reviewer | `multiple_person_mm4056f1` | people |
| Regulatory Status | `color_mkzkf80t` | status |
| PM | `multiple_person_mkzh7k0j` | people |
| PM Weekly Check-In | `color_mm5f5rwa` | status |
| PM Weekly Check-In | `long_text_mm5hp2gh` | long_text *(same title, different column — a free-text log next to the status)* |
| Last Date of Follow-Up | `date_mm5fertb` | date |
| Sales Rep | `color_mm076254` | status *(fixed name list — see below)* |
| Sales Rep | `multiple_person_mkzkg5mp` | people *(a second, separate column — see "Two Sales Rep columns" below)* |
| Date Assets Received | `date_mkzh6ges` | date |
| Design Date | `date_mkzk3swr` | date |
| QA Received Date | `date_mkzkt1wk` | date |
| QA Approved Date | `date_mkzkzrh2` | date |
| RA Trademark Sent Date | `date_mkzk6gpw` | date |
| RA Approved Date | `date_mkzknjre` | date |
| Customer Approval Date | `date_mkzkdkrp` | date |
| Customer Unresponsive Date | `date_mkzverp4` | date |
| QA Total Days | `formula_mm0gjpj8` | formula |
| Days Total | `formula_mm0gx5g4` | formula |
| Error # | `numeric_mm0gvcpr` | numbers |
| Subitems | `subtasks_mm0nfeab` | subtasks |
| Phone Number | `text_mm5snx24` | text *(a second, separate phone column — see below)* |
| Prop 65 | `text_mm5s3rdw` | text |

## Status / dropdown option lists

Option ids are the board's internal values (what the API reads/writes), not
display order.

### Edit Management (`color_mkzkg2wz`)
`[0]` Customer Manages Edit · `[2]` Vox Manages Edit · `[5]` *(blank)*

### Priority (`color_mkzvyt93`)
`[0]` RUSH · `[7]` Normal · `[10]` RUSH ⚠️

### Design Status (`status7`)
`[0]` Design in Process · `[1]` Sent to QA · `[2]` Waiting Label Files ·
`[3]` Design Today · `[4]` Customer Rejected · `[5]` Waiting on Customer ·
`[6]` Rejected by QA · `[7]` On Hold · `[8]` Design with Customer ·
`[9]` Unresponsive Customer · `[10]` Received by Design

### Asset Status (`status`)
`[0]` Assets Requested · `[1]` Assets Received · `[2]` No Assets on File ·
`[3]` New Design Assets Requested

### Reason Code (`color_mkzk1b5m`)
40+ options — by far the most granular field on the board:
`[0]` Customer initiated: Label review · `[1]` New label design (Vox design) ·
`[2]` New label review (Customer design) · `[3]` Vox initiated: Label edit/review ·
`[4]` 3D Rendering · `[5]` *(blank)* · `[6]` Master Template ·
`[7]` Customer initiated: Label edit · `[8]` New label Review (Customer Design) ·
`[9]` Vox initiated - Label edit/review · `[10]` Silver Onyx ·
`[11]` New label design - Vox | Standard Matt Lam. ·
`[12]` REWORK - New label review. · `[13]` 3D Rendering | Vox Initiated ·
`[14]` Pre-Approved Outsourced Labels. · `[15]` Pre-Approved Label ·
`[16]` Customer initiated: Label review & New label review (Customer design) ·
`[17]` Pre-Approved Standard · `[18]` Customer initiated Label Edit ·
`[19]` Vox Initiated - 3D Rendering · `[101]` Vox Initiated  - 3D Rendering ·
`[102]` Label Review · `[103]` Vox initiaded: Label edit/review ·
`[104]` Vox Initiated · `[105]` Customer Initiated: Label Edit ·
`[106]` Vox Initiated: Label Edit/Review · `[107]` Vox initiated - Label Review ·
`[108]` Vox Initiated: Label Edit/Review | Standard Label ·
`[109]` New Label Design · `[110]` Customer initiated: Label edit/review ·
`[151]` Label Edit · `[152]` Vox Initiated - Label Review/ Edit ·
`[153]` New label design (Customer design) ·
`[154]` RUSH - Vox initiated: Label edit/review

### QA Status (`status9`)
`[0]` Test Print Requested · `[1]` QA Approved · `[2]` QA Rejected ·
`[3]` QA Review · `[4]` QA Waiting for Customer · `[5]` *(blank)* ·
`[6]` QA Hold · `[12]` QA Received · `[14]` Customer Rejected

### Label Disposition (`color_mkzk738g`)
`[0]` Send Back · `[1]` Use as is · `[2]` Destroy · `[3]` No Labels in Stock

### Customer Approval (`color_mkzk6gt5`)
`[0]` Send back for Changes · `[1]` Approved · `[2]` Send back to design/Make changes

### Labels Inventory (`color_mkzketj9`)
`[0]` 1-100 · `[1]` None · `[2]` 100-250 · `[3]` 250-500 · `[4]` 500-1000 ·
`[6]` 1000-2500 · `[7]` 2500-5000 · `[8]` 5000+

### Files Released on Drive (`color_mkzkje5m`)
`[1]` Added to Drive

### Create QA Form (`color_mm01v9gz`)
`[0]` Re-Send QA Form · `[1]` Create QA Form

### Bottle Material (`color_mkzvbses`)
`[0]` PET · `[1]` HDPE · `[2]` Glass · `[3]` N/A · `[4]` Opt Out · `[6]` Opt In · `[7]` -

### Regulatory Status (`color_mkzkf80t`)
`[0]` Aquamin Trademark · `[1]` Sabinsa Trademark · `[2]` Organic ·
`[3]` RA Review · `[4]` RA Approved · `[5]` *(blank)* · `[6]` Pending Customer ·
`[7]` RA Rejected · `[8]` Customer Approved · `[9]` Customer Rejected ·
`[10]` Prop 65 Letter · `[11]` Waiting on testing · `[12]` Waiting on PDP form ·
`[13]` Caronositol Trademark · `[14]` Crea+Brain Trademark

### PM Weekly Check-In (`color_mm5f5rwa`)
`[0]` Waiting for RA Review · `[1]` Check · `[2]` Waiting on Customer ·
`[3]` Waiting on QA · `[4]` Waiting on Design · `[6]` Waiting on certs ·
`[7]` Waiting on Testing · `[8]` Waiting to be released ·
`[9]` Waiting on Prop 65 · `[10]` Waiting for RA

### Sales Rep — status column (`color_mm076254`)
`[0]` Ruben Espinosa · `[1]` Steve Kim · `[2]` Tyler Hall · `[3]` Janet Pacheco ·
`[4]` Tanner Wach · `[6]` Johnsie Mays · `[7]` Kami Butcher · `[8]` Zac Riggs ·
`[9]` Test · `[10]` Andres Martinez · `[11]` Zeljan Avdic · `[12]` Claudio Soto ·
`[13]` Camilo Montano · `[14]` Aishah Alqasim · `[15]` Emily Gray ·
`[16]` Landen Epperson · `[17]` Ashley Quintana · `[18]` Zeijan

## Two things that need a decision before `MONDAY_COLUMNS` is filled in

**Two "Sales Rep" columns.** One is a **status** field with the fixed name
list above (`color_mm076254`); the other is a real Monday **people** column
(`multiple_person_mkzkg5mp`), letting anyone assign an actual Monday user.
`label_design_report`'s `sales_rep_primary`/`sales_rep_secondary` are plain
text from Plex — they map cleanly onto the status column's option *labels*,
not onto the people column (which needs a Monday user id, not a name). Whoever
owns this board should say which one is the source of truth before the push
is wired up.

**Two phone columns** — `Phone` (`numeric_mm07acsq`, a numbers column) and
`Phone Number` (`text_mm5snx24`, plain text). `customer_phone` from the view
is a formatted string (`"864-616-8885"`), which only the text column can hold
without stripping the formatting.

**`Label SKU` is the item's own name/title** (`id: name`), not a separate
column — so whatever creates a Monday item should set its *name* to the SKU,
not to `customer_name — customer_part_no` as `pushToMonday_()` currently does.
