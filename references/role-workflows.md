# Role Workflows

## Owner/Admin

Allowed:

- Initialize the management repo.
- Configure provider permissions, protected branches, CI, and website deployment.
- Change schemas, templates, policies, and role rules.
- Propose and approve feature proposals before execution tasks are created.
- Merge structural pull requests or merge requests after validation passes.
- Reject PRs/MRs that try to mark work complete when objective output verification fails.

## Manager/PM

Allowed:

- Create projects, tasks, and documents.
- Convert accepted feature proposals into milestones, tasks, docs, and repo-linked work.
- Create roadmaps and milestones.
- Edit project state, planning docs, repo links, task definitions, dependencies, asset manifests, and live notes through PRs/MRs.
- Review validation and document-audit reports, then merge approved work if permitted.

Recommended commands:

```powershell
git_pm.py create-project --repo . --name "Arena Prototype" --owner "Samantha" --type game
git_pm.py create-milestone --repo . --project-id PROJ1 --title "FTUE Vertical Slice" --owner "Samantha"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type game-design --title "Core Loop Design" --owner "Kai"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type meeting-notes --title "Kickoff Notes" --owner "Samantha"
git_pm.py create-task --repo . --project-id PROJ1 --title "Implement loop prototype" --assigned-to "Kenneth" --expected-output "Pull Request"
git_pm.py validate --repo .
git_pm.py audit-docs --repo .
```

## Assignee

Allowed:

- Read latest project docs and task specs after pulling the management repo.
- Read the roadmap, current milestone, and task folder before changing work.
- Inspect only the implementation repos linked to assigned tasks or project state.
- Update assigned task status through website proposals, controller commands, or append-only events.
- Submit output links.
- Record every completion attempt, withdrawal, supersession, or cancelled review through the attempt commands.
- Propose doc/spec changes in a PR/MR.
- Add project notes, meeting-note follow-ups, or task events when new context appears.

Not allowed by default:

- Directly mark a task `Verified`.
- Mark work `Done` without accessible output and an approved review.
- Rewrite another user's task.
- Change output verification policy.
- Bypass PR/MR validation for durable changes.

## Reviewer

Allowed:

- Review outputs against `policies/output-requirements.yaml`.
- Append task review records.
- Move task status from `In Review` to `Verified` or back to `In Progress/Revising`.

Required:

- Include concrete reasons for revise/fail decisions.
- Keep reviews append-only.
- Reject objective verification failures instead of merging invalid `Done` state, then record `verification_failed` so the attempt is visible.

## Field Authority

Use PRs/MRs for:

- Project state.
- Roadmaps and milestones.
- Task specs.
- Dependencies.
- Acceptance criteria.
- Policies/templates.
- Asset manifests.
- Durable docs such as proposals, designs, reports, and decisions.
- Meeting notes, project notes, weekly updates, risk logs, and retrospectives.

Use task events and attempt/review commands for:

- Quick status updates.
- Blockers.
- Handoffs.
- Output submission notes.
- Failed objective verification.
- Withdrawn or superseded outputs.
- Cancelled reviews.

## Live Versus Historical Records

Live files should track the current project truth and should be reviewed regularly for inconsistencies. This includes root and project READMEs, `registry.yaml`, `project.yaml`, active specs, current notes, risk logs, policies, and live asset manifests.

Historical files should preserve what was true when the work happened. This includes completed or verified task folders, append-only task events, review records, finalized meeting notes, archived reports, and docs marked `final`, `archived`, or `historical`.

If terminology changes, such as `heroes` becoming `champions`, update the live files and add a decision or project note explaining the change. Do not edit an old completed task such as `Create hero Athena` unless the owner/admin explicitly approves a historical correction.

## Daily Role Examples

For concrete day-to-day examples for project managers, game designers, programmers, artists, 3D artists, modellers, backend engineers, frontend engineers, and reviewers, read `references/day-to-day-workflows.md`.
