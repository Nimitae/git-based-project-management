# Schemas

## Repository Layout

```text
registry.yaml
README.md
projects/
  PROJ1-sample-game/
    README.md
    project.yaml
    tasks/
      TASK1.yaml
    docs/
      proposals/
      design/
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
  "expected_output": "Pull Request",
  "acceptance_criteria": ["Events are documented", "Tests pass"],
  "dependencies": [],
  "target_repo": "game-client",
  "output": "",
  "blocker": "",
  "ai_update": "",
  "user_update": ""
}
```

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
- `game-design`
- `technical-spec`
- `frontend-spec`
- `backend-spec`
- `playtest-plan`
- `playtest-report`
- `qa-report`
- `research-report`
- `asset-brief`
- `3d-asset-brief`
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

Historical files include completed or verified task YAML, append-only event/review logs, archived reports, finalized meeting notes, and docs with `final/archived/historical` status. These should not be modified to chase current terminology. Create a `decision` or `project-note` instead.

Example: if the team renames `heroes` to `champions`, update live docs. Do not rewrite a completed `TASK17` titled `Create hero Athena`; preserve the record and link the terminology decision.

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
