#!/usr/bin/env python3
"""
Terraform deploy guard — run by Terraform itself on every plan and apply
(`data "external" "deploy_guard"` in terraform/main.tf), so it cannot be
forgotten the way a pre-flight script can.

WHY: `terraform apply` deploys whatever is on disk, from any branch. On
2026-09-22 an apply from dev-scorecard silently rolled back a Label Design fix
that branch never had, and nobody noticed for two days (CLAUDE.md, "Known
friction"). Prod must only ever be what `main` says, and `main` on GitHub must
be the record of it.

Refuses unless ALL hold:
  1. running from the PRIMARY worktree (C:\\F\\Parasol\\plex-to-big-query) —
     the ptbq-* project folders are for editing, never deploying;
  2. on branch `main`;
  3. the working tree is clean (an uncommitted edit would deploy unrecorded);
  4. HEAD == origin/main (what deploys is what GitHub shows).

Override for a deliberate one-off, e.g. a read-only plan from a dev branch to
see drift:  TF_GUARD_OVERRIDE="<reason>" terraform plan ...   — the reason is
echoed into the plan output. Never use it to apply.

Protocol: Terraform's external data source reads one JSON object from stdout
on success; on failure it shows stderr and aborts the plan.
"""

import json
import os
import subprocess
import sys


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def main():
    json.load(sys.stdin)  # Terraform sends the query object; nothing needed from it.
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("rev-parse", "HEAD")
    origin = git("rev-parse", "refs/remotes/origin/main")
    git_dir = os.path.normcase(os.path.abspath(git("rev-parse", "--git-dir")))
    common = os.path.normcase(os.path.abspath(git("rev-parse", "--git-common-dir")))
    dirty = git("status", "--porcelain")

    problems = []
    if git_dir != common:
        problems.append(f"this is a linked worktree ({git('rev-parse', '--show-toplevel')}). "
                        "Deploy only from the primary folder, C:\\F\\Parasol\\plex-to-big-query.")
    if branch != "main":
        problems.append(f"branch is '{branch}', not 'main'.")
    if dirty:
        problems.append("working tree is not clean:\n    " + "\n    ".join(dirty.splitlines()[:10]))
    if branch == "main" and head != origin:
        problems.append(f"local main {head[:8]} != origin/main {origin[:8]} — push (or pull) first, "
                        "so GitHub's main is the record of what is deployed.")

    override = os.environ.get("TF_GUARD_OVERRIDE", "").strip()
    if problems and not override:
        sys.stderr.write("\nDEPLOY GUARD: refusing to plan/apply.\n  - " + "\n  - ".join(problems) +
                         "\n\nUse scripts/deploy.sh from the main folder. Read-only plan from elsewhere:"
                         "\n  TF_GUARD_OVERRIDE=\"why\" terraform plan -var-file=terraform.tfvars\n")
        sys.exit(1)

    json.dump({"branch": branch, "commit": head[:12],
               "override": override if problems else "",
               "problems": " | ".join(problems) if problems else ""}, sys.stdout)


if __name__ == "__main__":
    main()
