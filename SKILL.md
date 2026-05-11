---
name: git-based-project-management
description: Build, install, initialize, operate, validate, and deploy a Git-first project management/wiki system for small teams on GitHub or GitLab. Use when Codex needs to set up or manage Git-backed project docs, task specs, game/software project state, agent-searchable Markdown/YAML records, GitHub pull requests or GitLab merge requests from website/human edits, role-specific owner/manager/assignee/reviewer workflows, a Docker/Node.js website backed by Git, validation for IDs/dependencies/assets/reviews, or collaboration across multiple linked implementation repositories.
---

# Git-Based Project Management

## Operating Model

Treat Git as the operating system:

- Git repository: canonical source of truth for projects, task specs, project documents, asset manifests, policies, review logs, and durable decisions.
- GitHub PRs or GitLab MRs: approval path for project state changes, document edits, task spec changes, and policy/template changes.
- GitHub/GitLab Issues or event files: lightweight task discussion and execution updates.
- Website: human interface that reads Git-derived data and turns edits into PRs/MRs instead of mutating canonical state directly.
- Agents: use deterministic scripts first; use LLM judgment only to draft, summarize, review quality, or propose changes.

Keep implementation codebases in their own GitHub/GitLab repos. This management repo stores links, intent, tasks, reviews, and source-of-truth project metadata.

## Roles

- Owner/Admin: initialize the repo, configure provider permissions, deploy the website, approve schema/policy changes.
- Manager/PM: create projects, documents, and tasks; review PR/MR diffs; run validation; publish the website; inspect blockers and workload.
- Assignee: read assigned tasks, project docs, dependencies, and submit status/output updates through the website, Issues, or task events.
- Reviewer: verify task outputs against `policies/output-requirements.yaml`, append review records, and move tasks through review states.
- Agent installer: run `doctor --interactive`, collect required credentials/access, and report missing permissions without storing long-lived secrets unless explicitly approved.

Read `references/role-workflows.md` when deciding which fields a role may change.

## Core Commands

Use `scripts/git_pm.py` for deterministic work:

```powershell
& "<python>" "...\git-based-project-management\scripts\git_pm.py" doctor --interactive
& "<python>" "...\git-based-project-management\scripts\git_pm.py" init --repo ".\project-hub" --name "New Project Hub" --owner "Terence" --provider github --github-repo "owner/project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" validate --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" compile --repo ".\project-hub"
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
2. Read task specs and Markdown docs from the local repo.
3. Use the website/API or controller to propose changes as PRs/MRs.
4. Use direct task events or Issues for lightweight execution updates.
5. Run `validate` before merging.

Use PRs/MRs for durable changes:

- Project objective, scope, acceptance criteria, or decision changes.
- Task creation/deletion/spec changes.
- Dependency changes.
- Asset manifest changes.
- Review policy/template changes.

Use task events/issues for operational updates:

- Started, blocked, submitted output, handoff note, quick status update.

Use controller commands for normal day-to-day updates:

```powershell
git_pm.py update-task --repo . --task-id TASK3 --actor "Paul" --status "In Progress" --user-update "Prototype branch is running locally."
git_pm.py submit-output --repo . --task-id TASK3 --actor "Paul" --output "https://github.com/org/game-client/pull/42" --message "Ready for review."
git_pm.py review-task --repo . --task-id TASK3 --reviewer "Maya" --decision "approved" --notes "Accepted."
git_pm.py register-asset --repo . --project-id PROJ1 --title "HUD mockup v2" --asset-type "mockup" --source-url "https://example.com/mockup" --used-by "PROJ1,TASK4" --owner "Fern"
```

## References

- `references/architecture.md`: canonical data model, Git/website/PR/MR boundaries, and collaboration rules.
- `references/schemas.md`: repository layout and file schemas.
- `references/wiki-guidelines.md`: required wiki page shapes, document sections, asset registration, and task-linking rules.
- `references/day-to-day-workflows.md`: role-specific workflows for PMs, game designers, programmers, artists, 3D artists, modellers, backend engineers, frontend engineers, and reviewers.
- `references/role-workflows.md`: owner/manager/assignee/reviewer/agent rules.
- `references/git-provider-setup.md`: GitHub/GitLab tokens, repository permissions, PR/MR creation, and deployment guidance.
- `references/website.md`: website behavior, API endpoints, proposal flow, and deployment options.

## Safety Rules

- Do not trust hand-copied IDs. Allocate IDs through the controller or website backend and validate every PR/MR.
- Do not let the website mutate the default branch directly. It must create a branch and PR/MR, or produce a local proposal in dry-run mode.
- Do not store binary-heavy assets directly in normal Git. Use Git LFS, Releases/Packages, object storage, or external product repos, and register them in `assets/assets.yaml`.
- Do not treat generated website data as canonical. Rebuild it from Markdown/YAML.
- Do not bypass validation when merging structural changes.
