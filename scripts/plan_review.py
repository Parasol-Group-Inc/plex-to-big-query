#!/usr/bin/env python3
"""
Read a saved Terraform plan and say what it REALLY changes.

    terraform show -json deploy.tfplan > plan.json
    python scripts/plan_review.py plan.json      # exit 0 ok, 2 = needs a human look

For every GCS config/SQL object in the plan, the live object is downloaded and
compared with its local `source` with line endings normalised. A plan full of
CRLF-vs-LF re-uploads (2026-09-24: 8 of 30 "changes") is how a real change —
like a rolled-back view — hides in plain sight. Also reports which project each
change belongs to, and refuses silently-dangerous shapes (destroys, replaces).
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".githooks"))
from hooks import project  # noqa: E402  — one definition of which file is whose

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def gcs_bytes(bucket, name):
    r = subprocess.run(f'gcloud storage cat "gs://{bucket}/{name}"', shell=True, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def norm(b):
    return b.replace(b"\r\n", b"\n").rstrip(b"\n")


def main(path):
    plan = json.load(open(path, encoding="utf-8"))
    content, eol, other, danger = [], [], [], []
    for rc in plan.get("resource_changes", []):
        actions = rc["change"]["actions"]
        if actions in (["no-op"], ["read"]):
            continue
        addr = rc["address"]
        if "delete" in actions:
            danger.append(f"{'/'.join(actions)}  {addr}")
        is_object = rc["type"] == "google_storage_bucket_object"
        if is_object and (actions == ["update"] or "create" in actions):
            after = rc["change"]["after"] or {}
            src = after.get("source") or ""
            rel = os.path.relpath(os.path.abspath(os.path.join(ROOT, "terraform", src)), ROOT).replace("\\", "/") \
                if src else "?"
            live = gcs_bytes(after.get("bucket", ""), after.get("name", "")) if "update" in actions else None
            local = open(os.path.join(ROOT, rel), "rb").read() if os.path.exists(os.path.join(ROOT, rel)) else b""
            tag = f"[{project(rel)}]"
            if live is not None and norm(live) == norm(local):
                eol.append(f"{tag:15} {rel}")
            else:
                content.append(f"{tag:15} {rel}{'  (new)' if 'create' in actions else ''}")
        elif "delete" not in actions:
            other.append(f"{'/'.join(actions):8} {addr}")

    print(f"\n=== PLAN REVIEW: {len(content)} content change(s), {len(eol)} line-ending-only, "
          f"{len(other)} other resource change(s), {len(danger)} destroy/replace ===")
    for title, rows in (("CONTENT CHANGES — these are what this deploy does", content),
                        ("OTHER RESOURCES", other),
                        ("DESTROY / REPLACE — read every one", danger),
                        ("line-ending only (same content; harmless re-upload)", eol)):
        if rows:
            print(f"\n{title}:")
            for r in sorted(rows):
                print("  " + r)
    projects = sorted({re.match(r"\[(.*?)\]", r).group(1) for r in content})
    print(f"\nprojects touched by content changes: {', '.join(projects) or 'none'}")
    return 2 if danger else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
