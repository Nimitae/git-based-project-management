# Website

## Purpose

The website gives humans a project-management UI while preserving Git as source of truth.

It must:

- Read project state from canonical Markdown/YAML files.
- Display dashboards, docs, tasks, owners, blockers, dependencies, and recent events.
- Let users propose edits without mutating the default branch.
- Convert edits into GitHub pull requests or GitLab merge requests when provider credentials are configured.
- Fall back to local dry-run proposal files when credentials are missing.

## Included UI

The bundled static UI supports:

- Project/document/task dashboard.
- Search across docs/tasks/owners/status.
- Task table with status and expected output.
- Documents panel with Git paths.
- Create-task proposal form.
- Edit-file proposal form.
- Local dry-run proposal output.

## Runtime Options

The default deployable website runtime is Node.js:

```powershell
cd assets\website
$env:GPM_REPO = "C:\path\to\project-hub"
npm start
```

The Python controller can still serve the same UI for local agent workflows:

```powershell
git_pm.py website --repo . --port 8787
```

Use the Node.js runtime for Docker/container deployment. Use the Python runtime when the agent is already operating through `git_pm.py` and wants a quick local preview.

## API

Both website runtimes serve:

- `GET /api/data`: compiled Project Hub data.
- `POST /api/proposals`: create a local dry-run proposal, GitHub PR, or GitLab MR.
- `GET /healthz`: readiness check.

Proposal payload examples:

```json
{
  "type": "create_task",
  "title": "Draft concept doc",
  "project_id": "PROJ1",
  "assigned_to": "Samantha",
  "role": "Design",
  "expected_output": "Concept Doc"
}
```

```json
{
  "type": "edit_file",
  "path": "projects/PROJ1-sample-game/docs/design/DOC2-core-loop.md",
  "content": "...full file content...",
  "message": "Update core loop scope"
}
```

## Deployment Notes

For local Python review:

```powershell
git_pm.py compile --repo .
git_pm.py website --repo . --port 8787
```

For local Node.js review:

```powershell
cd assets\website
$env:GPM_REPO = "C:\path\to\project-hub"
$env:PORT = "8787"
npm start
```

For Docker:

```powershell
docker build -t project-hub-website assets\website
docker run --rm -p 8787:8787 -e GPM_REPO=/data/project-hub -v "C:\path\to\project-hub:/data/project-hub" project-hub-website
```

For live GitHub PR creation from the website container:

```powershell
docker run --rm -p 8787:8787 `
  -e GPM_REPO=/data/project-hub `
  -e GPM_PROVIDER=github `
  -e GPM_LIVE_PROPOSALS=1 `
  -e GPM_GITHUB_REPO=owner/git-based-project-management `
  -e GPM_GITHUB_TOKEN=<token> `
  -v "C:\path\to\project-hub:/data/project-hub" `
  project-hub-website
```

For live GitLab MR creation from the website container:

```powershell
docker run --rm -p 8787:8787 `
  -e GPM_REPO=/data/project-hub `
  -e GPM_PROVIDER=gitlab `
  -e GPM_LIVE_PROPOSALS=1 `
  -e GPM_GITLAB_URL=https://gitlab.garena.com `
  -e GPM_GITLAB_PROJECT=group/project-hub `
  -e GPM_GITLAB_TOKEN=<token> `
  -v "C:\path\to\project-hub:/data/project-hub" `
  project-hub-website
```

For a manager asking an agent to deploy:

1. Run `doctor --interactive`.
2. Confirm GitLab token permissions.
3. Run `validate`.
4. Start the Node.js website in dry-run mode first.
5. Build and run the Docker image against a mounted Project Hub repo.
6. Switch to live PR/MR mode by setting `GPM_LIVE_PROPOSALS=1`, provider, and token/repo env vars.
7. Configure the service manager/container/runner outside this skill according to team infrastructure.

## UX Rules

- The first screen is the dashboard, not a landing page.
- Long-form prose edits are accepted, but saved as MR proposals.
- Status updates should be lightweight and visible in recent events.
- Every proposed change should show the target branch/MR or dry-run proposal path.
