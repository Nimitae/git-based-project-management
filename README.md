# Git-Based Project Management

A Codex skill and deployable website for running small-team project management directly from Git.

The system treats a Git repository as the source of truth for project state, task specs, project documents, asset manifests, review logs, and durable decisions. Human edits go through a website or agent workflow that produces GitHub pull requests or GitLab merge requests instead of mutating the default branch directly.

## What This Provides

- A Codex skill in `SKILL.md` for installing, initializing, operating, and validating a Git-backed project workspace.
- A deterministic controller script at `scripts/git_pm.py`.
- A Node.js website runtime in `assets/website` that can run locally or in Docker.
- Markdown and JSON-subset YAML schemas that are easy for humans and agents to search.
- A project structure suited for software and game development: roadmap, milestones, task folders, proposals, game design docs, technical specs, playtest reports, QA reports, release notes, videos, and asset manifests.

## Repository Layout

```text
SKILL.md
agents/
assets/
  website/
references/
scripts/
```

When the skill initializes a team workspace, it creates a separate project-management repository with this kind of layout:

```text
registry.yaml
START_HERE_FOR_AGENTS.md
projects/
  PROJ1-sample-game/
    README.md
    project.yaml
    planning/
      roadmap.yaml
      milestones/
    tasks/
      TASK1/
        task.yaml
        notes.md
        outputs.md
        attachments/
    docs/
    assets/
templates/
events/
reviews/
policies/
```

Implementation code, game builds, websites, tools, and services can stay in their own GitHub or GitLab repositories. The management repo stores links, task intent, decisions, reviews, and project state. Each project should list its implementation repos in `project.yaml`; implementation tasks point to those repos with `target_repo` and record `output_commit` so reviewers can confirm the exact commit exists.

Task actors should usually be real staff identified by email. Keep staff in `registry.yaml` under `people`; use a role-only task placeholder only while work is still unassigned.

## Quick Start

Run the controller with Python:

```powershell
python scripts/git_pm.py doctor --interactive
python scripts/git_pm.py init --repo ".\project-hub" --name "Project Hub" --owner "Your Name" --provider github --github-repo "owner/project-hub"
python scripts/git_pm.py validate --repo ".\project-hub"
python scripts/git_pm.py audit-docs --repo ".\project-hub"
python scripts/git_pm.py compile --repo ".\project-hub"
python scripts/git_pm.py project-status --repo ".\project-hub" --project-id PROJ1
python scripts/git_pm.py my-tasks --repo ".\project-hub" --user "Your Name"
python scripts/git_pm.py create-milestone --repo ".\project-hub" --project-id PROJ1 --title "FTUE Vertical Slice" --owner "Your Name"
python scripts/git_pm.py propose-feature --repo ".\project-hub" --project-id PROJ1 --title "FTUE Data Tracking" --owner "Your Name"
python scripts/git_pm.py website --repo ".\project-hub" --port 8787
```

The local website will be available at:

```text
http://127.0.0.1:8787/
```

Generate a realistic game-team demo workspace:

```powershell
python scripts/git_pm.py demo --repo ".\demo-game-hub" --name "Demo Game Hub" --owner "Maya"
```

## Node.js Website

The deployable website runtime is in `assets/website`.

```powershell
cd assets\website
$env:GPM_REPO = "C:\path\to\project-hub"
npm start
```

The website reads Git-backed project state and supports dry-run proposals by default. Set live provider credentials only when you want website edits to create PRs/MRs.

## Docker

```powershell
docker build -t project-hub-website assets\website
docker run --rm -p 8787:8787 -e GPM_REPO=/data/project-hub -v "C:\path\to\project-hub:/data/project-hub" project-hub-website
```

## Environment Variables

Use environment variables for local setup and provider access. Do not commit tokens.

- `GPM_REPO`: local management repo path.
- `GPM_PROVIDER`: `github` or `gitlab`.
- `GPM_LIVE_PROPOSALS`: set to `1` to create live PRs/MRs from the website.
- `GPM_GITHUB_REPO`: GitHub repo path, for example `owner/project-hub`.
- `GPM_GITHUB_TOKEN`: GitHub token with repository write access.
- `GPM_GITLAB_URL`: GitLab instance URL.
- `GPM_GITLAB_PROJECT`: GitLab project path.
- `GPM_GITLAB_TOKEN`: GitLab token with API/repository write access.

## Validation

Run these before handing the setup to another agent or deploying changes:

```powershell
python -m py_compile scripts/git_pm.py scripts/smoke_test.py scripts/node_website_smoke_test.py
node --check assets/website/server.mjs
node --check assets/website/static/app.js
python scripts/git_pm.py audit-docs --repo ".\project-hub"
python scripts/smoke_test.py
python scripts/node_website_smoke_test.py
```

## Collaboration Model

- Durable changes go through pull requests or merge requests.
- The website is a human interface over Git, not the canonical database.
- This operating model does not use Git Issues for task tracking; task state, events, reviews, and attempts live in Git files.
- IDs are allocated by the controller or website backend, then validated before merge.
- Roadmaps and milestones provide planning structure above tasks.
- Owners propose new features with `propose-feature`; accepted proposals are decomposed into milestones, tasks, docs, and linked implementation repo work.
- New tasks live in task folders with `task.yaml`, `notes.md`, `outputs.md`, and `attachments/`.
- Agents can answer day-to-day questions with `my-tasks`, `project-status`, `review-queue`, `blocked-tasks`, and `stale-work`.
- Day-to-day task updates use `update-task`, `add-event`, `record-attempt`, `record-verification-failed`, `withdraw-output`, `supersede-output`, `cancel-review`, `submit-output`, `review-task`, `register-repo`, and `register-asset`.
- `record-attempt` is preferred for completion attempts; `submit-output` is the short submission path. `Done` and `Verified` require output, output commit for code tasks, acceptance criteria, and an approved review record.
- Every attempt to complete work should leave an append-only event or review record, even when the output is rejected, withdrawn, superseded, or review is cancelled.
- Meeting minutes, project notes, weekly updates, risk logs, retros, and decisions are first-class documents created with `create-doc`.
- Live docs should be updated when terminology or scope changes; completed tasks and finalized records should stay historical.
- Large videos, builds, source art, and captures should live in Git LFS, releases/packages, object storage, or implementation repos, with references tracked in asset manifests.

See `references/operating-model.md`, `references/architecture.md`, `references/schemas.md`, `references/wiki-guidelines.md`, `references/day-to-day-workflows.md`, `references/agent-entrypoints.md`, `references/attempt-workflows.md`, `references/team-cadence.md`, and `references/website.md` for the detailed model.
