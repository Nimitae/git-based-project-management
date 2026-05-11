---
name: git-based-project-management
description: Build, install, initialize, operate, validate, and deploy a Git-first project management/wiki system for small teams on GitHub or GitLab. Use when Codex needs to set up or manage Git-backed project docs, task specs, game/software project state, agent-searchable Markdown/YAML records, GitHub pull requests or GitLab merge requests from website/human edits, role-specific owner/manager/assignee/reviewer workflows, a Docker/Node.js website backed by Git, validation for IDs/dependencies/assets/reviews, or collaboration across multiple linked implementation repositories.
---

# Git-Based Project Management

## Operating Model

Treat Git as the operating system:

- Git repository: canonical source of truth for projects, task specs, project documents, asset manifests, policies, review logs, and durable decisions.
- GitHub PRs or GitLab MRs: approval path for project state changes, document edits, task spec changes, and policy/template changes.
- Event/review files: lightweight task discussion, output attempts, failed verification, withdrawals, supersessions, and review cancellation.
- Website: human interface that reads Git-derived data and turns edits into PRs/MRs instead of mutating canonical state directly.
- Agents: use deterministic scripts first; use LLM judgment only to draft, summarize, review quality, or propose changes.

Keep implementation codebases in their own GitHub/GitLab repos. This management repo stores links, intent, tasks, reviews, and source-of-truth project metadata.

## Roles

- Owner/Admin: initialize the repo, configure provider permissions, deploy the website, approve schema/policy changes.
- Manager/PM: create projects, documents, and tasks; review PR/MR diffs; run validation; publish the website; inspect blockers and workload.
- Assignee: read assigned tasks, project docs, dependencies, and submit status/output updates through the website, controller commands, or task events.
- Reviewer: verify task outputs against `policies/output-requirements.yaml`, append review records, and move tasks through review states.
- Agent installer: run `doctor --interactive`, collect required credentials/access, and report missing permissions without storing long-lived secrets unless explicitly approved.

Task lifecycle is `Backlog` -> `In Progress`/`Blocked` -> `In Review` -> `Done`/`Verified`. Prefer `submit-output` to move work into `In Review`; do not directly mark work `Done` or `Verified` unless output and approved review records are present.

Read `references/role-workflows.md` when deciding which fields a role may change.

## Common User Intents

When a user asks what they need to do today, pull latest Git state and run:

```powershell
git_pm.py my-tasks --repo . --user "Bao"
```

Then read the listed task folders, linked docs, recent events, and relevant implementation repos.

When an owner proposes a new feature, create a reviewable feature proposal before creating execution tasks:

```powershell
git_pm.py propose-feature --repo . --project-id PROJ1 --title "FTUE Data Tracking" --owner "Maya" --problem "Tutorial drop-off is not measurable" --value "Team can diagnose onboarding friction" --scope "Client events, backend ingest, validation dashboard" --task-breakdown "Design event spec; implement client events; add backend ingest; verify staging data"
```

When a manager asks for project health, run:

```powershell
git_pm.py project-status --repo . --project-id PROJ1
git_pm.py review-queue --repo .
git_pm.py blocked-tasks --repo .
git_pm.py stale-work --repo .
```

When a reviewer asks what needs review, start with `review-queue`, then inspect each task output before approval.

## Core Commands

Use `scripts/git_pm.py` for deterministic work:

```powershell
& "<python>" "...\git-based-project-management\scripts\git_pm.py" doctor --interactive
& "<python>" "...\git-based-project-management\scripts\git_pm.py" init --repo ".\project-hub" --name "New Project Hub" --owner "Terence" --provider github --github-repo "owner/project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" validate --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" audit-docs --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" compile --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" my-tasks --repo ".\project-hub" --user "Bao"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" project-status --repo ".\project-hub" --project-id PROJ1
& "<python>" "...\git-based-project-management\scripts\git_pm.py" review-queue --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" create-milestone --repo ".\project-hub" --project-id PROJ1 --title "FTUE Vertical Slice" --owner "Maya"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" propose-feature --repo ".\project-hub" --project-id PROJ1 --title "FTUE Data Tracking" --owner "Maya"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" record-attempt --repo ".\project-hub" --task-id TASK3 --actor "Paul" --output "https://gitlab.garena.com/group/game/-/merge_requests/42" --message "FTUE tracking implementation ready for review."
& "<python>" "...\git-based-project-management\scripts\git_pm.py" website --repo ".\project-hub" --port 8787
& "<python>" "...\git-based-project-management\scripts\git_pm.py" demo --repo ".\demo-game-hub" --name "Demo Game Hub" --owner "Maya"
```

Use the Node.js website runtime for the deployable human UI:

```powershell
cd "...\git-based-project-management\assets\website"
$env:GPM_REPO = "C:\path\to\project-hub"
npm start
```

Use Docker for container deployment:

```powershell
docker build -t project-hub-website "...\git-based-project-management\assets\website"
docker run --rm -p 8787:8787 -e GPM_REPO=/data/project-hub -v "C:\path\to\project-hub:/data/project-hub" project-hub-website
```

Use the bundled smoke tests before handing a setup to another agent:

```powershell
& "<python>" "...\git-based-project-management\scripts\smoke_test.py"
& "<python>" "...\git-based-project-management\scripts\node_website_smoke_test.py"
```

## Setup Workflow

1. Run `doctor --interactive` to probe for:
   - Git executable.
   - Provider: `github` or `gitlab`.
   - GitHub repo path such as `owner/project-hub`, or GitLab project path such as `group/project-hub`.
   - Token with repo/API write permission if the website or agent must create PRs/MRs.
   - Local Project Hub repo path.
   - User role and permission intent.
2. Run `init` for a new management repo, or clone an existing repo.
3. Run `validate`.
4. Run `website` locally for review, then deploy the Node.js website runtime with Docker or the team's preferred runner.
5. Commit the Project Hub repo and push it to GitHub/GitLab.

Never commit tokens. Prefer environment variables:

- `GPM_PROVIDER`: `github` or `gitlab`.
- `GPM_GITHUB_REPO`: `owner/repo`.
- `GPM_GITHUB_TOKEN`: token for GitHub PR creation.
- `GPM_GITHUB_API_URL`: defaults to `https://api.github.com`.
- `GPM_GITLAB_URL`
- `GPM_GITLAB_PROJECT`
- `GPM_GITLAB_TOKEN`
- `GPM_REPO`

## Daily Workflow

Use Git-local files for project intent:

1. Pull latest Git state.
2. Read `START_HERE_FOR_AGENTS.md`, project README, roadmap, milestone, task folder, and Markdown docs from the local repo.
3. Use the website/API or controller to propose changes as PRs/MRs.
4. Use direct task events and attempt/review commands for lightweight execution updates.
5. Run `validate`, `audit-docs`, and `compile` before merging.

Use PRs/MRs for durable changes:

- Project objective, scope, acceptance criteria, or decision changes.
- Feature proposals and accepted feature scope.
- Task creation/deletion/spec changes.
- Dependency changes.
- Asset manifest changes.
- Review policy/template changes.
- Live document terminology or scope changes.

Use task events and attempt/review commands for operational updates:

- Started, blocked, submitted output, output attempt, verification failed, output withdrawn, output superseded, review cancelled, handoff note, quick status update.

Use documents for durable artifacts beyond tasks:

```powershell
git_pm.py propose-feature --repo . --project-id PROJ1 --title "FTUE Data Tracking" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type meeting-notes --title "Sprint Planning 2026-05-11" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type project-note --title "FTUE Analytics Notes" --owner "Bao"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type risk-log --title "Release Risk Log" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type decision --title "Rename Heroes To Champions" --owner "Maya"
```

Use controller commands for normal day-to-day updates:

```powershell
git_pm.py update-task --repo . --task-id TASK3 --actor "Paul" --status "In Progress" --user-update "Prototype branch is running locally."
git_pm.py submit-output --repo . --task-id TASK3 --actor "Paul" --output "https://github.com/org/game-client/pull/42" --message "Ready for review."
git_pm.py record-attempt --repo . --task-id TASK3 --actor "Paul" --output "https://github.com/org/game-client/pull/42" --message "Ready for objective verification."
git_pm.py record-verification-failed --repo . --task-id TASK3 --reviewer "Maya" --reason "PR link is inaccessible to the reviewer account."
git_pm.py supersede-output --repo . --task-id TASK3 --actor "Paul" --new-output "https://github.com/org/game-client/pull/43" --reason "Replaced inaccessible PR with the correct branch."
git_pm.py withdraw-output --repo . --task-id TASK3 --actor "Paul" --reason "Output is obsolete after scope changed."
git_pm.py cancel-review --repo . --task-id TASK3 --actor "Maya" --reason "Review cancelled because the output was withdrawn."
git_pm.py review-task --repo . --task-id TASK3 --reviewer "Maya" --decision "approved" --notes "Accepted."
git_pm.py register-asset --repo . --project-id PROJ1 --title "HUD mockup v2" --asset-type "mockup" --source-url "https://example.com/mockup" --used-by "PROJ1,TASK4" --owner "Fern"
```

New tasks live in folders: `task.yaml`, `notes.md`, `outputs.md`, and `attachments/README.md`. Use the task folder for task-local context and link large artifacts through the asset manifest.

If a PR/MR marks a task `Done` but the output cannot be objectively verified, reject the PR/MR and record `record-verification-failed` against the task in a follow-up proposal or review branch. If the output is accessible but quality/scope is insufficient, record `changes_requested` through `review-task`.

Run `audit-docs` regularly, especially before planning reviews or release reviews. It checks validation, expected master files, live docs, terminology drift, and blocked task details. Configure terminology checks in `policies/terminology.yaml`; use narrow `allowed_occurrences` for exact historical references that should remain unchanged.

Treat live docs and historical records differently. Update live docs when terminology changes, such as renaming `heroes` to `champions`. Do not rewrite completed task records, finalized meeting notes, archived reports, append-only events, or reviews just to match new terminology. Instead, create a `decision` or `project-note` that explains the change.

## References

- `references/architecture.md`: canonical data model, Git/website/PR/MR boundaries, and collaboration rules.
- `references/operating-model.md`: lifecycle, verification rule, planning structure, and task-folder model.
- `references/schemas.md`: repository layout and file schemas.
- `references/wiki-guidelines.md`: required wiki page shapes, document sections, asset registration, and task-linking rules.
- `references/day-to-day-workflows.md`: role-specific workflows for PMs, game designers, programmers, artists, 3D artists, modellers, backend engineers, frontend engineers, and reviewers.
- `references/agent-entrypoints.md`: exact behavior for common day-to-day user prompts.
- `references/role-workflows.md`: owner/manager/assignee/reviewer/agent rules.
- `references/git-provider-setup.md`: GitHub/GitLab tokens, repository permissions, PR/MR creation, and deployment guidance.
- `references/website.md`: website behavior, API endpoints, proposal flow, and deployment options.
- `references/attempt-workflows.md`: output attempts, failed verification, withdrawals, supersessions, and cancellation.
- `references/team-cadence.md`: daily/weekly/release operating rhythm for a six-person team.

## Safety Rules

- Do not trust hand-copied IDs. Allocate IDs through the controller or website backend and validate every PR/MR.
- Do not use Git Issues as task state for this workflow. Use Git files, event/review logs, and PRs/MRs.
- Do not let the website mutate the default branch directly. It must create a branch and PR/MR, or produce a local proposal in dry-run mode.
- Do not store binary-heavy assets directly in normal Git. Use Git LFS, Releases/Packages, object storage, or external product repos, and register them in `assets/assets.yaml`.
- Do not treat generated website data as canonical. Rebuild it from Markdown/YAML.
- Do not bypass validation when merging structural changes.
- Do not rewrite completed tasks, finalized docs, append-only events, or reviews to match current terminology. Preserve them and add a live decision/project note instead.
- Do not merge invalid completed state. Failed objective verification should block the PR/MR instead of producing a false `Done` record.
