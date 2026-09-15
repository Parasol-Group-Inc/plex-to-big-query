"""Tests for reason_code.parse_job_note.

    python label_design_service/test_reason_code.py

Plain assert-based checks with a printed PASS/FAIL summary, matching the
style of deploy/label_design_sync/test_logic.js elsewhere in this repo —
no test framework dependency, safe to run any time, touches nothing external.

Run this after any change to REASON_CODE_MAP or the separator-stripping rule.
"""
from reason_code import parse_job_note, REASON_CODE_MAP

fail = 0


def check(job_note, expected_code, expected_memo, label):
    global fail
    code, memo = parse_job_note(job_note)
    ok = code == expected_code and memo == expected_memo
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        print(f"          got      code={code!r} memo={memo!r}")
        print(f"          expected code={expected_code!r} memo={expected_memo!r}")
        fail += 1


print("=== Recognized codes, with a separator ===")
check("1 - Customer wants a different font", 105,
      "Customer wants a different font", 'digit 1, " - " separator')
check("3: New design requested", 1,
      "New design requested", 'digit 3, ": " separator')
check("6.Rush job, please expedite", 4,
      "Rush job, please expedite", 'digit 6, "." separator, no space')

print("\n=== Recognized codes, no separator ===")
check("1Customer wants font change", 105,
      "Customer wants font change", "digit 1, no separator at all")

print("\n=== Recognized code, nothing after it ===")
check("6", 4, "", "bare digit 6, empty memo")
check("2   ", 0, "", "digit 2 followed only by trailing whitespace")

print("\n=== Not a recognized code — whole note preserved ===")
check("Label Design - White Bopp", None, "Label Design - White Bopp",
      "real 2026-09-15 note, no leading digit at all")
check("0 - invalid code", None, "0 - invalid code",
      "digit 0 is not in the map — must NOT be silently treated as a code")
check("9 - also invalid", None, "9 - also invalid",
      "digit 9 is not in the map either")

print("\n=== Empty / missing ===")
check("", None, "", "empty string")
check(None, None, "", "None (NULL Job_Note from BigQuery)")
check("   ", None, "", "whitespace-only note")

print("\n=== Real example, confirmed by Emilio 2026-09-15 ===")
check("3 Update to current V code. Standard Label.", 1,
      "Update to current V code. Standard Label.",
      "real Job Note -> New label design (Vox design), memo intact incl. its own periods")

print("\n=== Whitespace around the whole note ===")
check("  2   Trailing/leading whitespace test  ", 0,
      "Trailing/leading whitespace test", "outer whitespace trimmed first")

print("\n=== Every mapped code resolves to the right Monday index ===")
for digit, expected_index in REASON_CODE_MAP.items():
    code, _ = parse_job_note(f"{digit} - test")
    ok = code == expected_index
    print(("  PASS  " if ok else "  FAIL  ") +
          f"code {digit} -> index {expected_index}")
    if not ok:
        fail += 1

print("\n" + ("FAILURES: " + str(fail) if fail else "ALL CHECKS PASSED"))
exit(1 if fail else 0)
