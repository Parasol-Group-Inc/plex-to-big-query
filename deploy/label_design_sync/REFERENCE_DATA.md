# Reference data and enrichment settings

> **Being retired (2026-09-25).** This describes the Sheet-based flow, which the push service (`label_design_service/push.py`) replaces once it is scheduled in prod. It stays accurate for the Apps Script that is still live until then. Current status: [`label-design/STATUS.md`](../../label-design/STATUS.md).

This file documents the config-driven enrichment layer added to the Label Design queue.

## Script properties

These values are optional and should be set in Apps Script project properties when the business rules are ready to be activated.

- `REASON_CODE_MAP_JSON` — JSON object mapping normalized reason phrases to Monday reason code values
- `PART_ATTRIBUTE_MAP_JSON` — JSON object mapping part number to an attribute object
- `AUTO_GENERATE_LCR` — `true` or `false`, controls whether a generated LCR value is added during push

Example:

```json
{
  "HOLD": "HOLD",
  "HOLDING": "HOLD",
  "REWORK": "REWORK",
  "TRIM": "TRIM"
}
```

For part attributes:

```json
{
  "ABC123": {
    "prop_65": "YES",
    "label": "VITAMIN",
    "bottle_material": "HDPE",
    "reason_code": "HOLD"
  }
}
```

## Behavior

The enrichment layer runs during the Monday push path, not during the initial check step.

- If the job note contains a recognizable reason phrase, the row will normalize to the configured Monday-friendly code.
- If the part number has a matching attribute entry, the row can prefill fields such as `prop_65`, `label`, or `bottle_material` when those columns are blank.
- If `AUTO_GENERATE_LCR` is enabled and the row has no LCR value yet, a deterministic 14-character alphanumeric string is generated for the row.

## Safety rules

- The enrichment is intentionally config-driven and disabled by default unless script properties are set.
- It never overwrites a team-entered value on the sheet when a review value is already provided.
- It keeps the current review flow intact: the data is still reviewed by a person before it reaches Monday.

## Recommended governance

- keep the reason-code catalog as a controlled list owned by the business
- keep the part attribute table keyed by `customer_part_no` or equivalent canonical part key
- treat LCR generation as a uniqueness-controlled operational rule, not a free-form value generator
