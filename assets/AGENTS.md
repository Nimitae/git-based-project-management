# Project Hub — Agent Instructions

This file is auto-read by AI agents (Hermes, Codex, Claude, OpenClaw, etc.) when their working directory is set to this Project Hub. Follow everything here before touching any files.

---

## 1. Read the Hub First

Before doing anything, orient yourself:

```bash
cat START_HERE_FOR_AGENTS.md
cat README.md
```

Then pull the latest state and check project health:

```bash
git pull --ff-only
python3 .project-hub/scripts/git_pm.py project-status --repo . --no-pull
python3 .project-hub/scripts/git_pm.py review-queue --repo . --no-pull
python3 .project-hub/scripts/git_pm.py blocked-tasks --repo . --no-pull
```

---

## 2. Always Pull Before Editing

**Always run `git pull --ff-only` before any read or write operation.** Project Hub state is shared — it may have changed since your session started. Pull at the start of every session, before creating or reviewing PRs/MRs, before writing any files, and again after any significant pause.

If the pull fails due to diverged branches, stop and report the state. Do not force-push or rebase shared branches without explicit instruction.

---

## 3. Use `git_pm.py` for ALL Structural Changes

All task, doc, event, and registry changes **must** go through `git_pm.py`. Never hand-craft task folders, doc stubs, registry entries, or event log lines directly.

The script lives at `.project-hub/scripts/git_pm.py` in this repo.

### Key commands

```bash
# Project health
python3 .project-hub/scripts/git_pm.py project-status --repo . --project-id PROJ1
python3 .project-hub/scripts/git_pm.py my-tasks --repo . --user "you@example.com"
python3 .project-hub/scripts/git_pm.py review-queue --repo .
python3 .project-hub/scripts/git_pm.py blocked-tasks --repo .
python3 .project-hub/scripts/git_pm.py stale-work --repo .

# Create
python3 .project-hub/scripts/git_pm.py create-task --repo . --project-id PROJ1 --title "..." --assigned-to "you@example.com" --expected-output "..."
python3 .project-hub/scripts/git_pm.py create-doc --repo . --project-id PROJ1 --doc-type project-note --title "..." --owner "you@example.com"

# Update
python3 .project-hub/scripts/git_pm.py update-task --repo . --task-id TASK-... --actor "you@example.com" --status "In Progress"
python3 .project-hub/scripts/git_pm.py add-event --repo . --task-id TASK-... --actor "you@example.com" --message "..."

# Output + review
python3 .project-hub/scripts/git_pm.py record-attempt --repo . --task-id TASK-... --actor "you@example.com" --output "..." --output-commit "..."
python3 .project-hub/scripts/git_pm.py review-task --repo . --task-id TASK-... --reviewer "you@example.com" --decision approved --notes "..."

# Validate (always before committing)
python3 .project-hub/scripts/git_pm.py validate --repo .
```

### Hard rules

- Do **not** create `TASK<N>`, `DOC<N>`, or timestamped folders by hand — IDs are allocated by the tool
- Do **not** edit `registry.yaml` directly
- Do **not** append to `events/task-events.jsonl` by hand
- Do **not** skip validation before committing

---

## 4. Commit and MR Discipline

Every durable change must be committed and pushed. The workflow is:

1. `git pull --ff-only` (always first)
2. Make changes using `git_pm.py`
3. `python3 .project-hub/scripts/git_pm.py validate --repo .` — fix any **new** errors (pre-existing errors are expected; do not regress them)
4. `git checkout -b <branch>` — never commit directly to master/main
5. `git add` only the files changed by the task
6. `git commit -m "<type>(<scope>): <summary>"` with a clear message
7. `git push -u origin <branch>`
8. Open a PR/MR targeting master/main

For lightweight operational updates (status changes, events, attempt records), a direct commit to a short-lived branch is fine. For structural changes (new tasks, docs, policy edits, scope changes), always open a PR/MR for review before merging.

---

## 5. Keep the Skill in Sync

The `git_pm.py` script and skill instructions bundled in this hub come from:

> **https://github.com/Nimitae/git-based-project-management**

To update to the latest version:

```bash
# Re-clone the skill source and copy the updated script + skill doc
git clone https://github.com/Nimitae/git-based-project-management.git /tmp/gbpm-latest
cp /tmp/gbpm-latest/scripts/git_pm.py .project-hub/scripts/git_pm.py
cp /tmp/gbpm-latest/SKILL.md .project-hub/skill/SKILL.md
cp /tmp/gbpm-latest/AGENTS.md AGENTS.md

# Commit the update
git checkout -b chore/sync-gbpm-skill
git add .project-hub/scripts/git_pm.py .project-hub/skill/SKILL.md AGENTS.md
git commit -m "chore: sync git_pm.py and SKILL.md to latest GBPM upstream"
git push -u origin chore/sync-gbpm-skill
# Then open a PR/MR to merge
```

Do this periodically, or whenever the skill source repo has new commits that fix bugs or add commands you need.

---

## 6. What Not to Do

- Do not commit tokens, credentials, or secrets to this repo
- Do not mutate `master`/`main` directly — always use a branch + PR/MR
- Do not merge PRs/MRs with new validation errors
- Do not mark tasks `Done` without an output, output commit (for code tasks), and an approved review record
- Do not create duplicate tasks — run `project-status` first to check existing work
- Do not rewrite completed task records, finalized meeting notes, or append-only event logs to match new terminology — add a decision doc instead

---

## 7. Full Skill Reference

The complete GBPM skill instructions (operating model, schemas, role workflows, safety rules) are at:

```
.project-hub/skill/SKILL.md
```

Read this for anything not covered above.
