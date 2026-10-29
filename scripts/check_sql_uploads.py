#!/usr/bin/env python3
"""Every view SQL a report YAML names must have its Terraform upload (audit A4, 2026-10-29).

A `sql_file:` in reports/*.yaml or reports/test/*.yaml is read from GCS at run
time. The file only gets there through a google_storage_bucket_object in
terraform/main.tf. Twice a new view shipped without one: the YAML deployed, the
SQL never reached GCS, and the job ran PARTIAL every day until someone noticed
(bottling_job_open_with_orders_view.sql, 2026-10-26).

    python scripts/check_sql_uploads.py            # the working tree
    python scripts/check_sql_uploads.py --staged   # what is staged (pre-commit)

Exits 1 and lists each missing upload, else 0.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = re.compile(r"^\s*sql_file:\s*gs://[^/\s]+/(sql/\S+\.sql)\s*$", re.M)
UPLOAD = re.compile(r'^\s*name\s*=\s*"(sql/[^"]+\.sql)"', re.M)


def read(path, staged):
    if staged:
        return subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    return (ROOT / path).read_text(encoding="utf-8")


def missing(staged=False):
    if staged:
        out = subprocess.run(["git", "ls-files", "reports"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
        yamls = [p for p in out.splitlines() if re.match(r"^reports/(test/)?[^/]+\.yaml$", p)]
    else:
        yamls = sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                       for p in [*ROOT.glob("reports/*.yaml"), *ROOT.glob("reports/test/*.yaml")])
    uploaded = set(UPLOAD.findall(read("terraform/main.tf", staged)))
    return sorted({(y, s) for y in yamls for s in SQL_FILE.findall(read(y, staged)) if s not in uploaded})


def main():
    gaps = missing(staged="--staged" in sys.argv)
    for y, s in gaps:
        print(f"  {y}: {s} has no google_storage_bucket_object in terraform/main.tf")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
