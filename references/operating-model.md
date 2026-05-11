# Operating Model

## Lifecycle

Use this lifecycle for work that produces code, docs, assets, builds, videos, reports, or decisions:

1. `Backlog`: accepted as possible work, but not ready to start.
2. `In Progress`: owned work is active.
3. `Blocked`: owner cannot progress without a named blocker.
4. `In Review`: output has been submitted and is waiting for objective checks or human review.
5. `Done`: accepted completed work with an output and approved review.
6. `Verified`: completed work that has passed the required verification gate.
7. `Iceboxed`: intentionally paused or closed without completion.

Do not skip from `In Progress` to `Done` unless the same PR/MR includes an accessible output and an approved review record. The preferred path is `record-attempt` or `submit-output`, which moves work to `In Review`, followed by `review-task`.

## Verification Rule

If someone opens a PR/MR to mark an item `Done` but the output cannot be objectively verified, reject the PR/MR. Do not merge an invalid completed state just to preserve history.

The attempt still needs a Git footprint. Record one of these append-only outcomes against the task:

- `record-verification-failed`: output exists or was claimed, but an objective check failed.
- `withdraw-output`: assignee withdraws the current output from review.
- `supersede-output`: assignee replaces a prior output with a newer one.
- `cancel-review`: reviewer or manager cancels a review before approval or changes-requested.

If the output is accessible but the reviewer disagrees on quality, scope, or acceptance, record `changes_requested`. That keeps the review trail without corrupting canonical task state.

## Planning Structure

Use:

- `planning/roadmap.yaml` for Now/Next/Later direction.
- `planning/milestones/MILESTONE#.yaml` for releases, sprints, vertical slices, or major deliverables.
- Task fields `milestone`, `feature_area`, `release_target`, `estimate`, `risk`, and `reviewer` for day-to-day planning.

## Task Folder Structure

New tasks live in folders:

```text
tasks/
  TASK123/
    task.yaml
    notes.md
    outputs.md
    attachments/
      README.md
```

Use `task.yaml` for durable state. Use `notes.md` for local context. Use `outputs.md` for submitted artifacts and verification notes. Keep large files out of normal Git and register them in the asset manifest.

Task folders are the right place for task-local context and small references. The canonical attempt history remains append-only in `events/task-events.jsonl` and `reviews/task-reviews.jsonl` so a withdrawn or failed output remains searchable even if the current task output changes.

## Review Gates

Required merge checks should run:

```powershell
python scripts/git_pm.py validate --repo .
python scripts/git_pm.py audit-docs --repo .
python scripts/git_pm.py compile --repo .
```

`Done` and `Verified` require:

- Output link.
- Acceptance criteria.
- Approved review record.
- No unresolved objective validation error.

## Human And Agent Reads

Before starting work, a human or agent should read:

1. Project README.
2. `planning/roadmap.yaml`.
3. Relevant milestone.
4. Task folder.
5. Linked live docs.
6. Relevant implementation repo.
7. Recent events and reviews.

## Cadence

Daily: assignees pull latest, read assigned task folders, update blockers/status, and record attempts or handoffs.

Weekly: manager reviews roadmap, milestones, review queue, blocked tasks, stale `In Review` work, validation warnings, and live-doc drift.

Release/milestone: owner or manager runs validation, document audit, compile, website smoke check, and output review gates before marking work `Done` or `Verified`.
