# Schemas

## Repository Layout

```text
registry.yaml
README.md
projects/
  PROJ1-sample-game/
    README.md
    project.yaml
    planning/
      roadmap.yaml
      milestones/
        MILESTONE1.yaml
    tasks/
      TASK1/
        task.yaml
        notes.md
        outputs.md
        attachments/
          README.md
    docs/
      proposals/
      design/
      engineering/
      reports/
      production/
      release/
      decisions/
      notes/
    assets/
      assets.yaml
templates/
events/
  task-events.jsonl
reviews/
  task-reviews.jsonl
policies/
  output-requirements.yaml
  definition-of-ready.yaml
  definition-of-done.yaml
  review-gates.yaml
  role-permissions.yaml
  storage-policy.yaml
  branch-protection.md
  agent-operating-rules.md
```

`registry.yaml`, task files, project files, and policy files use JSON-subset YAML by default. This keeps them easy for agents to parse without extra dependencies while remaining readable.

## Registry

Required top-level fields:

- `schema_version`
- `name`
- `provider`
- `github`
- `gitlab`
- `next_ids`
- `people`
- `projects`
- `tasks`
- `docs`
- `assets`

## Project

```json
{
  "id": "PROJ1",
  "slug": "sample-game",
  "name": "Sample Game",
  "type": "game",
  "status": "Active",
  "owners": ["Terence"],
  "summary": "Short project summary.",
  "path": "projects/PROJ1-sample-game/project.yaml",
  "readme": "projects/PROJ1-sample-game/README.md",
  "roadmap": "projects/PROJ1-sample-game/planning/roadmap.yaml",
  "repos": [
    {
      "name": "game-client",
      "provider": "github",
      "url": "https://github.com/org/game-client",
      "default_branch": "main",
      "role": "implementation"
    }
  ]
}
```

## Roadmap And Milestone

`planning/roadmap.yaml`:

```json
{
  "project_id": "PROJ1",
  "horizon": "Now / Next / Later",
  "now": ["Ship FTUE telemetry"],
  "next": ["Run tutorial playtest"],
  "later": [],
  "milestones": ["MILESTONE1"],
  "review_cadence": "Weekly",
  "last_reviewed": "2026-05-11"
}
```

`planning/milestones/MILESTONE1.yaml`:

```json
{
  "id": "MILESTONE1",
  "project_id": "PROJ1",
  "title": "FTUE vertical slice",
  "owner": "Maya",
  "status": "Active",
  "start": "",
  "target": "",
  "goals": ["Instrument tutorial funnel"],
  "scope": ["Client events", "Backend ingest", "Dashboard"],
  "exit_criteria": ["Events verified in staging"],
  "risks": [],
  "linked_tasks": ["TASK1"],
  "linked_docs": ["DOC1"]
}
```

## Task

```json
{
  "id": "TASK1",
  "project_id": "PROJ1",
  "title": "Implement tutorial analytics",
  "assigned_to": "Kenneth",
  "role": "Eng",
  "status": "Backlog",
  "checkpoint": "Drafting",
  "priority": "Medium",
  "deadline": "",
  "milestone": "MILESTONE1",
  "feature_area": "FTUE",
  "release_target": "",
  "estimate": "",
  "risk": "",
  "reviewer": "Maya",
  "expected_output": "Pull Request",
  "acceptance_criteria": ["Events are documented", "Tests pass"],
  "dependencies": [],
  "target_repo": "game-client",
  "output": "",
  "blocker": "",
  "ai_update": "",
  "user_update": "",
  "artifacts": {
    "notes": "projects/PROJ1-sample-game/tasks/TASK1/notes.md",
    "outputs": "projects/PROJ1-sample-game/tasks/TASK1/outputs.md",
    "attachments": "projects/PROJ1-sample-game/tasks/TASK1/attachments/"
  }
}
```

New tasks should be folder-based. `task.yaml` is durable state, `notes.md` is task-local context, `outputs.md` stores submitted artifacts and verification notes, and `attachments/` is only for small local references.

Task statuses:

- `Backlog`: accepted but not active.
- `In Progress`: active work.
- `Blocked`: blocked and must include blocker detail.
- `In Review`: output submitted, awaiting checks/review.
- `Done`: completed with output and approved review.
- `Verified`: completed and passed verification gate.
- `Iceboxed`: intentionally paused or closed.

## Document

Documents are Markdown with frontmatter:

```markdown
---
id: DOC1
project_id: PROJ1
type: playtest-report
owner: Samantha
status: draft
---

# DOC1 - First Playtest Report
```

Document statuses:

- `draft`: work in progress.
- `live`: current source of truth.
- `review`: current doc waiting review.
- `final`: completed record that should not be rewritten.
- `archived`: retained historical record.
- `historical`: preserved context from past work.

## Assets

Use project-level asset manifests for durable asset tracking:

```json
{
  "assets": {
    "ASSET1": {
      "title": "Prototype gameplay capture",
      "type": "video",
      "storage": "github-release",
      "path": "",
      "source_url": "https://...",
      "used_by": ["PROJ1", "TASK1", "DOC1"],
      "owner": "Celine"
    }
  }
}
```

Small previews may live in Git or Git LFS. Large builds, videos, source art, and captures should live in releases/packages/object storage or the relevant implementation repo.

## Events

Task events are append-only JSONL rows in `events/task-events.jsonl`:

```json
{
  "id": "EVENT1",
  "task_id": "TASK1",
  "project_id": "PROJ1",
  "actor": "Gina",
  "event_type": "task_update",
  "message": "Core loop questions are ready for review.",
  "created_at": "2026-05-11T10:00:00+08:00"
}
```

Use events for daily notes, handoffs, blockers, and output submission context. Durable task state still belongs in the task YAML file.

## Reviews

Task reviews are append-only JSONL rows in `reviews/task-reviews.jsonl`:

```json
{
  "id": "REVIEW1",
  "task_id": "TASK1",
  "project_id": "PROJ1",
  "reviewer": "Maya",
  "decision": "changes_requested",
  "notes": "Link the design doc before this can be verified.",
  "created_at": "2026-05-11T10:15:00+08:00"
}
```

Valid review decisions are `approved`, `changes_requested`, and `rejected`.

## Document Types

Core document types:

- `proposal`
- `brief`
- `feature-brief`
- `game-design`
- `technical-spec`
- `frontend-spec`
- `backend-spec`
- `telemetry-spec`
- `api-contract`
- `playtest-plan`
- `playtest-session`
- `playtest-report`
- `qa-report`
- `qa-bug-report`
- `research-report`
- `asset-brief`
- `3d-asset-brief`
- `art-handoff`
- `3d-model-handoff`
- `video-brief`
- `mockup-review`
- `build-note`
- `release-plan`
- `postmortem`
- `decision`
- `meeting-notes`
- `project-note`
- `weekly-update`
- `risk-log`
- `retro-notes`

## Live Versus Historical

Live/master files include `README.md`, `registry.yaml`, project `README.md`, `project.yaml`, current docs with `draft/live/review` status, and policy files. These should be updated when terminology or project direction changes.

Historical files include completed or verified task folders, append-only event/review logs, archived reports, finalized meeting notes, and docs with `final/archived/historical` status. These should not be modified to chase current terminology. Create a `decision` or `project-note` instead.

Example: if the team renames `heroes` to `champions`, update live docs. Do not rewrite a completed `TASK17` titled `Create hero Athena`; preserve the record and link the terminology decision.

## Review Gate Policy

`submit-output` should move work to `In Review`, not directly to `Done`. `Done` and `Verified` require output, acceptance criteria, and an approved review record. A PR/MR that directly marks a task `Done` without those fields should fail validation.

If output cannot be objectively accessed or checked, reject the PR/MR. Use the failed check or review comment as the historical footprint.

## Terminology Policy

`policies/terminology.yaml` can define preferred terms for `audit-docs`:

```json
{
  "schema_version": 1,
  "review_scope": "live-docs-and-master-files",
  "skip_paths": ["registry.yaml", "policies/*"],
  "allowed_occurrences": [
    {
      "path": "projects/PROJ1-arena/README.md",
      "term": "hero",
      "text": "Create hero Athena",
      "reason": "Exact historical task title reference."
    }
  ],
  "preferred_terms": [
    {
      "preferred": "champion",
      "avoid": ["hero", "heroes"],
      "enabled": true
    }
  ]
}
```
