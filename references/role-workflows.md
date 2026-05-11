# Role Workflows

## Owner/Admin

Allowed:

- Initialize the management repo.
- Configure provider permissions, protected branches, CI, and website deployment.
- Change schemas, templates, policies, and role rules.
- Merge structural pull requests or merge requests after validation passes.

## Manager/PM

Allowed:

- Create projects, tasks, and documents.
- Edit project state, planning docs, repo links, task definitions, dependencies, and asset manifests through PRs/MRs.
- Review validation reports and merge approved work if permitted.

Recommended commands:

```powershell
git_pm.py create-project --repo . --name "Arena Prototype" --owner "Samantha" --type game
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type game-design --title "Core Loop Design" --owner "Kai"
git_pm.py create-task --repo . --project-id PROJ1 --title "Implement loop prototype" --assigned-to "Kenneth" --expected-output "Pull Request"
git_pm.py validate --repo .
```

## Assignee

Allowed:

- Read latest project docs and task specs after pulling the management repo.
- Inspect only the implementation repos linked to assigned tasks or project state.
- Update assigned task status through website proposals, issues, or append-only events.
- Submit output links.
- Propose doc/spec changes in a PR/MR.

Not allowed by default:

- Directly mark a task `Verified`.
- Rewrite another user's task.
- Change output verification policy.
- Bypass PR/MR validation for durable changes.

## Reviewer

Allowed:

- Review outputs against `policies/output-requirements.yaml`.
- Append task review records.
- Move task status from `Done` to `Verified` or back to `In Progress/Revising`.

Required:

- Include concrete reasons for revise/fail decisions.
- Keep reviews append-only.

## Field Authority

Use PRs/MRs for:

- Project state.
- Task specs.
- Dependencies.
- Acceptance criteria.
- Policies/templates.
- Asset manifests.
- Durable docs such as proposals, designs, reports, and decisions.

Use task events or issues for:

- Quick status updates.
- Blockers.
- Handoffs.
- Output submission notes.

## Daily Role Examples

For concrete day-to-day examples for project managers, game designers, programmers, artists, 3D artists, modellers, backend engineers, frontend engineers, and reviewers, read `references/day-to-day-workflows.md`.
