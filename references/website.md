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
- My Work view for assignee/reviewer task lookup.
- Project Health view for blocked tasks, stale work, feature proposals awaiting decision, and repo verification gaps.
- Review queue for work in review, failed verification, withdrawn outputs, cancelled reviews, and stale review items.
- Search across docs/tasks/assets/owners/status.
- Task table with status and expected output.
- Documents panel with Git paths.
- Document rows include file hashes so raw edit proposals can carry a base hash.
- Assets panel with mockups, art, models, videos, builds, and external links.
- Create-task proposal form with optional target repo.
- Register-repo proposal form for project implementation repos.
- Feature-proposal form.
- Create-milestone proposal form.
- Create-document proposal form.
- Update-task, record-attempt, submit-output, record-verification-failed, withdraw-output, supersede-output, cancel-review, add-event, and review-task forms.
- Register-asset proposal form.
- Edit-file proposal form.
- Historical record edit guard for completed tasks, finalized docs, and append-only logs.
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
  "expected_output": "Concept Doc",
  "target_repo": "game-client"
}
```

```json
{
  "type": "register_repo",
  "project_id": "PROJ1",
  "name": "game-client",
  "provider": "github",
  "url": "https://github.com/example/game-client",
  "default_branch": "main",
  "role": "client/gameplay"
}
```

```json
{
  "type": "propose_feature",
  "project_id": "PROJ1",
  "title": "FTUE Data Tracking",
  "owner": "Maya",
  "problem": "Tutorial drop-off is not measurable.",
  "value": "Team can diagnose onboarding friction.",
  "scope": "Client events, backend ingest, validation dashboard.",
  "task_breakdown": "Design event spec; implement client events; add ingest endpoint."
}
```

```json
{
  "type": "edit_file",
  "path": "projects/PROJ1-sample-game/docs/design/DOC2-core-loop.md",
  "content": "...full file content...",
  "message": "Update core loop scope",
  "base_sha256": "optional-current-file-hash"
}
```

If `base_sha256` is provided and the file has changed, the website rejects the proposal as stale.

```json
{
  "type": "create_milestone",
  "project_id": "PROJ1",
  "title": "FTUE vertical slice",
  "owner": "Maya",
  "status": "Planned"
}
```

```json
{
  "type": "update_task",
  "task_id": "TASK2",
  "actor": "Gina",
  "status": "In Progress",
  "user_update": "Testing two tuning directions."
}
```

```json
{
  "type": "register_asset",
  "project_id": "PROJ1",
  "title": "HUD mockup v2",
  "asset_type": "mockup",
  "source_url": "https://example.com/mockup",
  "used_by": "PROJ1,TASK4",
  "owner": "Fern"
}
```

```json
{
  "type": "record_attempt",
  "task_id": "TASK3",
  "actor": "Paul",
  "output": "https://gitlab.garena.com/group/game/-/merge_requests/42",
  "target_repo": "game-client",
  "output_commit": "0123456789abcdef0123456789abcdef01234567",
  "message": "FTUE tracking implementation ready for objective checks."
}
```

```json
{
  "type": "record_verification_failed",
  "task_id": "TASK3",
  "reviewer": "Maya",
  "reason": "The linked MR deployment is not accessible to the reviewer account."
}
```

```json
{
  "type": "supersede_output",
  "task_id": "TASK3",
  "actor": "Paul",
  "new_output": "https://gitlab.garena.com/group/game/-/merge_requests/43",
  "reason": "Replaced the inaccessible output with the correct branch."
}
```

```json
{
  "type": "withdraw_output",
  "task_id": "TASK3",
  "actor": "Paul",
  "reason": "Output no longer required after scope changed."
}
```

```json
{
  "type": "cancel_review",
  "task_id": "TASK3",
  "actor": "Maya",
  "reason": "Review cancelled because the output was withdrawn."
}
```

```json
{
  "type": "create_doc",
  "project_id": "PROJ1",
  "title": "Sprint Planning 2026-05-11",
  "owner": "Maya",
  "doc_type": "meeting-notes"
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
- Attempt outcomes should be visible in the review queue and backed by append-only event/review records.
- Daily workflow forms should create the same canonical file changes an agent would create from the CLI.
- Raw file edits should not be used to rewrite completed tasks, finalized docs, events, or reviews. Create a project note, decision, event, or review instead.
- Raw file edits should include `base_sha256` when available so stale edits are rejected before PR/MR creation.
- Submit-output should move work to `In Review`; invalid direct `Done` changes should be rejected by validation.
- Every proposed change should show the target branch/MR or dry-run proposal path.
