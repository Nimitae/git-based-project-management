---
name: git-based-project-management
description: Build, install, initialize, operate, validate, and deploy a Git-first project management/wiki system for small teams on GitHub or GitLab. Use when Codex needs to set up or manage Git-backed project docs, project/EW/task specs, agent-searchable Markdown/YAML state, GitHub pull requests or GitLab merge requests from website/human edits, role-specific owner/manager/assignee/reviewer workflows, a Docker/Node.js website backed by Git, validation for IDs/dependencies/assets/reviews, or migration from spreadsheet/document project management to Git.
---

# Git-Based Project Management

## Operating Model

Treat Git as the operating system:

- Git repository: canonical source of truth for initiatives, projects, workstreams/experiments, task specs, assets manifests, policies, review logs, and durable decisions.
- GitHub PRs or GitLab MRs: approval path for structural changes, project/EW doc edits, task spec changes, and policy/template changes.
- GitHub/GitLab Issues or event files: lightweight task discussion and execution updates.
- Website: human interface that reads Git-derived data and turns edits into PRs/MRs instead of mutating canonical state directly.
- Agents: use deterministic scripts first; use LLM judgment only to draft, summarize, review quality, or propose changes.

Keep implementation codebases in their own GitHub/GitLab repos. This Project OS stores links, intent, tasks, reviews, and source-of-truth project metadata.

## Roles

- Owner/Admin: initialize the repo, configure provider permissions, deploy the website, approve schema/policy changes.
- Manager/PM: create projects/EWs/tasks, review PR/MR diffs, run validation, publish the website, inspect blockers and workload.
- Assignee: read assigned tasks, project/EW docs, dependencies, and submit status/output updates through the website, Issues, or task events.
- Reviewer: verify task outputs against `policies/output-requirements.yaml`, append review records, and move tasks through review states.
- Agent installer: run `doctor --interactive`, collect required credentials/access, and report missing permissions without storing long-lived secrets unless explicitly approved.

Read `references/role-workflows.md` when deciding which fields a role may change.

## Core Commands

Use `scripts/project_os.py` for deterministic work:

```powershell
& "<python>" "...\git-based-project-management\scripts\project_os.py" doctor --interactive
& "<python>" "...\git-based-project-management\scripts\project_os.py" init --repo ".\project-os" --name "New Project OS" --owner "Terence" --provider github --github-repo "owner/project-os"
& "<python>" "...\git-based-project-management\scripts\project_os.py" validate --repo ".\project-os"
& "<python>" "...\git-based-project-management\scripts\project_os.py" compile --repo ".\project-os"
& "<python>" "...\git-based-project-management\scripts\project_os.py" website --repo ".\project-os" --port 8787
```

Use the Node.js website runtime for the deployable human UI:

```powershell
cd "...\git-based-project-management\assets\website"
$env:PROJECT_OS_REPO = "C:\path\to\project-os"
npm start
```

Use Docker for container deployment:

```powershell
docker build -t project-os-website "...\git-based-project-management\assets\website"
docker run --rm -p 8787:8787 -e PROJECT_OS_REPO=/data/project-os -v "C:\path\to\project-os:/data/project-os" project-os-website
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
   - GitHub repo path such as `owner/project-os`, or GitLab project path such as `group/project-os`.
   - Token with repo/API write permission if the website or agent must create PRs/MRs.
   - Local Project OS repo path.
   - User role and permission intent.
2. Run `init` for a new Project OS repo, or clone an existing repo.
3. Run `validate`.
4. Run `website` locally for review, then deploy the Node.js website runtime with Docker or the team's preferred runner.
5. Commit the Project OS repo and push it to GitHub/GitLab.

Never commit tokens. Prefer environment variables:

- `PROJECT_OS_PROVIDER`: `github` or `gitlab`.
- `PROJECT_OS_GITHUB_REPO`: `owner/repo`.
- `PROJECT_OS_GITHUB_TOKEN`: token for GitHub PR creation.
- `PROJECT_OS_GITHUB_API_URL`: defaults to `https://api.github.com`.
- `PROJECT_OS_GITLAB_URL`
- `PROJECT_OS_GITLAB_PROJECT`
- `PROJECT_OS_GITLAB_TOKEN`
- `PROJECT_OS_REPO`

## Daily Workflow

Use Git-local files for project intent:

1. Pull latest Git state.
2. Read task specs and Markdown docs from the local repo.
3. Use the website/API or controller to propose changes as PRs/MRs.
4. Use direct task events or Issues for lightweight execution updates.
5. Run `validate` before merging.

Use PRs/MRs for durable changes:

- Project/EW objective, scope, acceptance criteria, or decision changes.
- Task creation/deletion/spec changes.
- Dependency changes.
- Asset manifest changes.
- Review policy/template changes.

Use task events/issues for operational updates:

- Started, blocked, submitted output, handoff note, quick status update.

## References

- `references/architecture.md`: canonical data model, Git/website/PR/MR boundaries, and migration notes.
- `references/schemas.md`: repository layout and file schemas.
- `references/role-workflows.md`: owner/manager/assignee/reviewer/agent rules.
- `references/git-provider-setup.md`: GitHub/GitLab tokens, repository permissions, PR/MR creation, and deployment guidance.
- `references/website.md`: website behavior, API endpoints, proposal flow, and deployment options.

## Safety Rules

- Do not trust hand-copied IDs. Allocate IDs through the controller or website backend and validate every PR/MR.
- Do not let the website mutate the default branch directly. It must create a branch and PR/MR, or produce a local proposal in dry-run mode.
- Do not store binary-heavy assets directly in normal Git. Use Git LFS, Releases/Packages, object storage, or external product repos, and register them in `assets/assets.yaml`.
- Do not treat generated website data as canonical. Rebuild it from Markdown/YAML.
- Do not bypass validation when merging structural changes.
