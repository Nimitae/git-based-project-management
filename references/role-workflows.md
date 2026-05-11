# Role Workflows

## Owner/Admin

Allowed:

- Initialize the repo.
- Configure GitLab project, tokens, protected branches, CI, and website hosting.
- Change schemas, templates, policies, and role rules.
- Merge structural MRs after validation passes.

Required:

- Run `doctor --interactive` during installation.
- Confirm token scopes and branch protection before enabling website MR creation.

## Manager/PM

Allowed:

- Create initiatives, projects, EWs, and tasks.
- Edit project/EW docs through MRs.
- Change task owner, expected output, deadline, dependencies, and acceptance criteria through MRs.
- Review validation reports and merge approved work if permitted.

Recommended commands:

```powershell
project_os.py create-project --repo . --name "Game Prototype" --owner "Samantha"
project_os.py create-ew --repo . --project-id PROJ1 --name "Core Loop Prototype" --owner "Kenneth"
project_os.py create-task --repo . --ew-id EW1 --title "Implement loop prototype" --assigned-to "Kenneth" --expected-output "Merge Request"
project_os.py validate --repo .
```

## Assignee

Allowed:

- Read local Git docs after pulling latest state.
- Update assigned task status via website proposal, GitLab Issue, or append-only task event.
- Submit output links.
- Propose doc/spec changes in an MR.

Not allowed by default:

- Directly mark a task `Verified`.
- Rewrite another user's task.
- Change output verification policy.
- Bypass MR validation for structural changes.

## Reviewer

Allowed:

- Review outputs against `policies/output-requirements.yaml`.
- Append task review records.
- Move task status from `Done` to `Verified` or back to `In Progress/Revising`.

Required:

- Include concrete reasons for revise/fail decisions.
- Keep reviews append-only.

## Agent Installer

Responsibilities:

- Probe permissions and report missing pieces.
- Avoid storing tokens unless the owner explicitly authorizes it.
- Confirm GitLab API connectivity before promising MR creation.
- Run `smoke_test.py` on the skill and `validate` on the initialized repo.

## Field Authority

Use MRs for:

- Project/EW/task specs.
- Dependencies.
- Acceptance criteria.
- Policies/templates.
- Asset manifests.

Use task events or issues for:

- Quick status updates.
- Blockers.
- Handoffs.
- Output submission notes.

Use reviews for:

- Pass/revise/fail decisions.
- Verification notes.
