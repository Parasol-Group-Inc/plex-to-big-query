#!/usr/bin/env python3
"""
Git hooks for plex-to-big-query — the commit and push locks.

Installed by `scripts/install_hooks.sh` (sets core.hooksPath=.githooks, which
covers every worktree of the repo). Each check exists because the failure it
blocks actually happened; the incident is named next to it.

Every block has a deliberate override — an environment variable set for that
one command, e.g. `ALLOW_MAIN_COMMIT=1 git commit ...`. Nothing is ever
bypassed silently: the override is printed, and `--no-verify` is the only way
around it without a trace, which CONTRIBUTING.md forbids.
"""

import os
import re
import subprocess
import sys


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


# ── which project a path belongs to ────────────────────────────────────────
# Anything not listed is SHARED (the ETL engine, reports/sql used by both,
# terraform, CHANGELOG, docs) and may be committed from any branch.
LABEL_DESIGN = re.compile(
    r"^(label-design/|label_design_service/|deploy/label_design_sync/|deploy/label_design_trigger/"
    r"|reports/(test/)?label_design\.yaml$|reports/sql/label_design_view\.sql$"
    r"|docs/reports/label_design_report\.md$|scripts/(copy_monday_board|label_design_test_data)\.py$"
    r"|meetings-reference/label-design/)")
SCORECARD = re.compile(
    r"^(score-card-reference/|deploy/manual_data_app/|scripts/board/|docs/SCORECARD_DATA_LOAD\.md$"
    r"|scripts/scorecard_sandbox/|docs/SCORECARD_SANDBOX_FINDINGS\.md$)")

# Branch each worktree folder is FOR. A `git switch` inside a project folder
# is how today's second session ended up committing on the wrong branch.
FOLDER_BRANCH = {
    "plex-to-big-query": "main",
    "ptbq-scorecard": "dev-scorecard",
    "ptbq-sandbox": "dev-sandbox",
    "ptbq-label-design": "dev-label-design",
    "ptbq-dev": "dev",
}
PROJECT_OF_BRANCH = {"dev-label-design": "label-design", "dev-scorecard": "scorecard",
                     "dev-sandbox": "scorecard"}


def project(path):
    if LABEL_DESIGN.match(path):
        return "label-design"
    if SCORECARD.match(path):
        return "scorecard"
    return "shared"


def blocked(msg, override):
    if os.environ.get(override) == "1":
        print(f"[hooks] OVERRIDE {override}=1 — allowing: {msg}", file=sys.stderr)
        return False
    print(f"\n[hooks] BLOCKED: {msg}\n        Deliberate override for this one command: {override}=1 git ...\n",
          file=sys.stderr)
    return True


# ── pre-commit ─────────────────────────────────────────────────────────────
def pre_commit():
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    top = git("rev-parse", "--show-toplevel")
    folder = os.path.basename(top.rstrip("/\\"))
    merging = os.path.exists(os.path.join(git("rev-parse", "--git-dir"), "MERGE_HEAD"))
    staged = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMRD").splitlines() if p]
    failed = False

    # 1. The folder is bound to a branch.
    expected = FOLDER_BRANCH.get(folder)
    if expected and branch != expected:
        failed |= blocked(f"folder '{folder}' is for branch '{expected}', but '{branch}' is checked out here. "
                          f"Switch back (git switch {expected}) or work in that branch's own folder.",
                          "ALLOW_WRONG_FOLDER")

    # 2. main takes merges only. (2026-09-24: deploy docs were committed straight
    #    onto main; every change should arrive through a dev branch.)
    if branch == "main" and not merging:
        failed |= blocked("direct commit on main. Commit on a dev* branch and merge it into main.",
                          "ALLOW_MAIN_COMMIT")

    # 3. A dev branch only carries its own project's files. (2026-09-24: a whole
    #    day of Label Design work sat uncommitted in the dev-scorecard tree.)
    if not merging:
        own = PROJECT_OF_BRANCH.get(branch)
        foreign = sorted({p for p in staged if project(p) not in ("shared", own)}) if own else []
        if foreign:
            failed |= blocked(f"'{branch}' is a {own} branch, but these staged files belong to another project:\n"
                              + "\n".join(f"          {p}  ({project(p)})" for p in foreign),
                              "ALLOW_CROSS_PROJECT")
        kinds = {project(p) for p in staged} - {"shared"}
        if not own and len(kinds) > 1:
            failed |= blocked(f"one commit mixes projects {sorted(kinds)} — commit each on its own branch.",
                              "ALLOW_CROSS_PROJECT")

    # 4. Anything that deploys gets a CHANGELOG entry in the same commit
    #    (CLAUDE.md "Convention").
    deploys = [p for p in staged if p.startswith(("reports/", "terraform/")) and not p.endswith(".md")]
    if deploys and "CHANGELOG.md" not in staged and not merging:
        failed |= blocked("these files deploy but CHANGELOG.md is not staged:\n"
                          + "\n".join(f"          {p}" for p in deploys[:8]), "ALLOW_NO_CHANGELOG")

    # 5. Prod and test YAML list the same extractions. (2026-09-09: the test
    #    config lagged, the job logged 22 extractions instead of 24, exited 0.)
    for p in staged:
        m = re.match(r"^reports/(test/)?([A-Za-z0-9_]+)\.yaml$", p)
        if not m:
            continue
        name = m.group(2)
        counts = []
        for q in (f"reports/{name}.yaml", f"reports/test/{name}.yaml"):
            blob = git("show", f":{q}")          # the STAGED version
            counts.append(len(re.findall(r"^\s*-\s*plex_view:", blob, re.M)))
        if counts[0] != counts[1]:
            failed |= blocked(f"{name}: prod YAML has {counts[0]} plex_view entries, test YAML has {counts[1]}. "
                              "Both files are hand-maintained; change them together.", "ALLOW_YAML_MISMATCH")
            break

    return 1 if failed else 0


# ── pre-push ───────────────────────────────────────────────────────────────
def pre_push(lines):
    failed = False
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if remote_ref != "refs/heads/main" or set(local_sha) == {"0"}:
            continue
        # Only main itself goes to main — a dev branch gets there by merge.
        if local_ref != "refs/heads/main":
            failed |= blocked(f"pushing {local_ref} into main. Merge it into main locally (or via a PR), "
                              "then push main.", "ALLOW_MAIN_PUSH")
        # Never rewrite main's history.
        if set(remote_sha) != {"0"} and subprocess.run(
                ["git", "merge-base", "--is-ancestor", remote_sha, local_sha]).returncode != 0:
            failed |= blocked("non-fast-forward push to main (would rewrite what prod was deployed from).",
                              "ALLOW_MAIN_PUSH")
    return 1 if failed else 0


if __name__ == "__main__":
    hook = sys.argv[1]
    if hook == "pre-commit":
        sys.exit(pre_commit())
    if hook == "pre-push":
        sys.exit(pre_push(sys.stdin.read().splitlines()))
    sys.exit(0)
