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
