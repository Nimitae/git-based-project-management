# Schemas

## Repository Layout

```text
project-os/
  registry.yaml
  initiatives/
    INIT1.md
  projects/
    PROJ1/
      project.md
      ews/
        EW1.md
      tasks/
        TASK1.yaml
  assets/
    assets.yaml
  policies/
    output-requirements.yaml
  events/
    task-events.jsonl
  reviews/
    task-reviews.jsonl
  .project-os/
    site-data/
      project-os.json
```

`registry.yaml`, task files, asset manifests, and policy files use JSON-subset YAML by default. This keeps them valid YAML and lets the bundled controller validate them without external dependencies.

## Registry

`registry.yaml` owns ID allocation and relationships.

Required top-level fields:

- `schema_version`
- `gitlab`
- `next_ids`
- `people`
- `entities.initiatives`
- `entities.projects`
- `entities.ews`
- `entities.tasks`

Do not hand-copy IDs between files. Use the controller or website backend to allocate IDs, then run validation.

## Markdown Documents

Initiative, project, and EW documents use frontmatter for machine-readable identity:

```markdown
---
id: EW1
type: ew
project_id: PROJ1
initiative_id: INIT1
owner: Terence
status: Running
---

# EW1 - Project Setup
```

The frontmatter should match `registry.yaml`. The body should contain human/agent-readable sections:

- Summary
- Goals
- Scope
- Acceptance Criteria
- Decisions
- Risks
- Open Questions
- Linked Tasks
- Change Log

## Task Spec

Task files are JSON-subset YAML:

```json
{
  "id": "TASK1",
  "ew_id": "EW1",
  "project_id": "PROJ1",
  "title": "Confirm Project OS setup",
  "assigned_to": "Terence",
  "role": "PM",
  "status": "Backlog",
  "checkpoint": "Drafting",
  "deadline": "",
  "expected_output": "Setup Confirmation",
  "acceptance_criteria": [
    "Repository validates",
    "Website loads locally"
  ],
  "dependencies": [],
  "target_repo": "",
  "output": "",
  "ai_update": "",
  "user_update": ""
}
```

## Events

Append execution updates to `events/task-events.jsonl`:

```json
{"event_id":"EVENT1","task_id":"TASK1","actor":"Terence","event_type":"blocked","message":"Waiting on access","created_at":"2026-05-10T10:00:00+08:00"}
```

## Reviews

Append review decisions to `reviews/task-reviews.jsonl`:

```json
{"review_id":"REVIEW1","task_id":"TASK1","reviewer":"Terence","decision":"revise","reasons":["Missing setup proof"],"created_at":"2026-05-10T10:00:00+08:00"}
```

## Assets

Register every durable image, video, build, design, or deck in `assets/assets.yaml`:

```json
{
  "assets": {
    "ASSET1": {
      "title": "FTUE reference",
      "type": "image",
      "storage": "git_lfs",
      "path": "assets/ASSET1.png",
      "source_url": "",
      "used_by": ["EW1"]
    }
  }
}
```

Use Git or Git LFS for small previews. Use GitLab Releases/Packages, object storage, Figma, or implementation repos for large binaries.
