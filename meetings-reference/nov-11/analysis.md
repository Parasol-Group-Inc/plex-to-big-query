# Meeting Emilio / Jennilyn, 2026-11-11: analysis

Sources here: `Emilio _ Jennilyn_transcript.txt` and `_summary.txt` (Otter), `gemini.md` (Gemini notes and
transcript), `whisper-transcript.txt` (a local Whisper run on the audio, used to settle names). The audio is
kept outside the repo (`~/plex-monitor/meetings/nov-11/` on Emilio's Mac). The full write-up, with minute
marks, is on the Reference tab of the "Plex ETL work log" Claude Doc.

## Agreed

- Google Cloud billing and project ownership move from Jennilyn to Parasol BizOps, by next week.
  - One billing per larger company: Kaya, On Demand, Ship Central, QSM, PCS.
  - PCS is separated because Hanya's scripts run every 10 min and cost more than Vox.
- Service accounts, not personal logins, run extraction, probes and publishing. Plex service users need a
  Plex case with a new email.
- One paid Google seat per company plus Parasol, so every project has two owners.
- Emilio:
  - backs up Jennilyn's VoxScorecardsLive views (done 11-11: `custom_views/`);
  - emails her everything under his name (drafted in Gmail);
  - adds her to GitHub;
  - tells Kelli about the Label Design process (drafted in Gmail).

## Not decided

- Label Design moving fully to the screens. Decide after 24 h of ODBC evidence (OPEN_ITEMS D38).
- Zoho Vault for shared credentials.
- Forcing expired-past-use-by containers back into on-hand.

## Checked afterwards

- **Her "expired" change** is in her own views, so the ETL does not revert it. Our valuation already counts
  Expired; `part_on_hand_inventory_report` does not.
- **The manual-data app:** the live code matched the repo v2 except wording and a lost byte-order-mark
  character. v2 was pasted and deployed on 11-11.
- **Ashley's question on customer notes:** the note shows on the customer profile only, not on any order
  screen (`docs/CUSTOMER_NOTES_BULK.md`, "Where the note shows").
- **Names:**
  - "Callie" and "Kelly" are Kelli (Label Design).
  - "Hanya" is behind the PCS scripts.
  - "SoHo Bolt" is Zoho Vault.
  - ODF is the company.
  - Emilio adds Jennilyn to GitHub, not the reverse.
