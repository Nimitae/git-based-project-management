# Attempt Workflows

Use attempt workflows when someone is trying to move work toward completion but the result may still fail objective checks or review.

## Core Rule

Do not merge a PR/MR that marks a task `Done` or `Verified` unless the output is objectively accessible and an approved review record exists.

Every attempt should still leave a Git footprint. The footprint lives in append-only files:

- `events/task-events.jsonl`
- `reviews/task-reviews.jsonl`

The current task file should show the latest usable state. Historical attempts should not be erased from event/review logs.

## Happy Path

```powershell
git_pm.py record-attempt --repo . --task-id TASK12 --actor "Bao" --output "https://gitlab.garena.com/group/backend/-/merge_requests/42" --message "FTUE event ingestion ready for staging verification."
git_pm.py review-task --repo . --task-id TASK12 --reviewer "Maya" --decision "approved" --notes "Events verified in staging and acceptance criteria met."
```

`record-attempt` moves the task to `In Review`. `approved` moves it to `Verified`.

## Objective Verification Failed

Use this when the claimed output cannot be accessed or objectively checked.

```powershell
git_pm.py record-verification-failed --repo . --task-id TASK12 --reviewer "Maya" --reason "The linked staging endpoint returns 404 and telemetry events cannot be observed."
```

Expected result:

- PR/MR that tried to mark `Done` is rejected.
- Task returns to `In Progress` / `Revising`.
- A `verification_failed` event and review row are appended.
- The failed attempt remains searchable in Git.

## Quality Or Scope Insufficient

Use `changes_requested` when the output exists and can be checked, but does not satisfy quality, acceptance, or scope.

```powershell
git_pm.py review-task --repo . --task-id TASK12 --reviewer "Maya" --decision "changes_requested" --notes "Events arrive, but payload is missing tutorial_step_id."
```

Expected result:

- PR/MR remains open or gets changes requested.
- Task returns to `In Progress` / `Revising`.
- The review record explains the requested changes.

## Output Withdrawn

Use this when the assignee or manager pulls the current output out of review.

```powershell
git_pm.py withdraw-output --repo . --task-id TASK12 --actor "Bao" --reason "Scope changed and this MR is no longer the right implementation."
```

Expected result:

- Task returns to `In Progress` / `Revising`.
- Current task `output` is cleared.
- The previous output remains in the `output_withdrawn` event.

## Output Superseded

Use this when a newer output replaces the old output.

```powershell
git_pm.py supersede-output --repo . --task-id TASK12 --actor "Bao" --new-output "https://gitlab.garena.com/group/backend/-/merge_requests/43" --reason "Rebased onto the new event schema."
```

Expected result:

- Task returns to `In Review`.
- Current task `output` points at the new output.
- The event records old and new output links when available.

## Review Cancelled

Use this when review stops before approval, rejection, or changes requested.

```powershell
git_pm.py cancel-review --repo . --task-id TASK12 --actor "Maya" --reason "Review cancelled because the output was withdrawn before checks started."
```

Expected result:

- Task returns to `In Progress` / `Revising`.
- A `cancelled` review row and `review_cancelled` event are appended.

## Reviewer Dashboard

The website review queue should be checked daily by the manager or reviewer. It surfaces:

- `In Review` tasks.
- Failed verification.
- Withdrawn outputs.
- Cancelled reviews.
- Review items older than three days.

