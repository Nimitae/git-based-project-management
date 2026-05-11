# Wiki Guidelines

## Project Home Page

Every project `README.md` should be the first page a human or agent reads.

Required sections:

- `State`: current status, current focus, next review, and major blockers.
- `Roadmap`: roadmap file, active milestone, release target, and review cadence.
- `Repositories`: linked implementation repos and what each repo owns.
- `Documents`: canonical docs grouped by design, engineering, production, reports, release, and decisions.
- `Tasks`: active task IDs and owners.
- `Assets`: important builds, mockups, videos, art, models, captures, and external storage links.
- `Operating Notes`: team conventions, meeting cadence, review expectations, and known constraints.

The root `START_HERE_FOR_AGENTS.md` should tell agents how to answer daily task checks, owner feature proposals, manager health checks, and reviewer queue checks.

## Document Rules

Use one Markdown file per durable document. Each document must have frontmatter:

```markdown
---
id: DOC#
project_id: PROJ#
type: game-design
owner: Name
status: draft
---
```

The H1 must start with the document ID:

```markdown
# DOC7 - Core Loop Design
```

Use stable section names. Validation warns when required sections are missing for common document types.

## Artifact Taxonomy

Store non-task artifacts as documents or assets, not as loose files:

- Meeting minutes: `meeting-notes` in `docs/notes/`.
- Project notes: `project-note` in `docs/notes/`.
- Weekly status updates: `weekly-update` in `docs/notes/`.
- Risk tracking: `risk-log` in `docs/notes/`.
- Retrospectives: `retro-notes` in `docs/notes/`.
- Durable decisions: `decision` in `docs/decisions/`.
- Designs/specs: `game-design`, `feature-brief` in `docs/design/`.
- Feature proposals: `feature-proposal` in `docs/proposals/`.
- Engineering specs: `technical-spec`, `frontend-spec`, `backend-spec`, `telemetry-spec`, `api-contract` in `docs/engineering/`.
- Reports: `playtest-plan`, `playtest-session`, `playtest-report`, `qa-report`, `qa-bug-report`, `research-report` in `docs/reports/`.
- Asset/mockup briefs and handoffs: `asset-brief`, `3d-asset-brief`, `art-handoff`, `3d-model-handoff`, `video-brief`, `mockup-review` in `docs/production/`.

Create them through `create-doc` so IDs and registry links stay consistent.

## Required Document Shapes

`proposal`:

- `Problem`
- `Proposed Direction`
- `Risks`
- `Decision Needed`

`game-design`:

- `Player Fantasy`
- `Core Loop`
- `Systems`
- `UX Notes`
- `Tuning Questions`

`feature-brief`:

- `Player/User Value`
- `Scope`
- `Dependencies`
- `Success Metrics`

`technical-spec`:

- `Goal`
- `Architecture`
- `Interfaces`
- `Test Plan`
- `Rollout`

`frontend-spec`:

- `User Flow`
- `State`
- `Components`
- `API Contract`
- `Test Plan`

`backend-spec`:

- `Goal`
- `Data Model`
- `API`
- `Operations`
- `Test Plan`

`telemetry-spec`:

- `Events`
- `Properties`
- `Consumers`
- `Privacy`
- `Validation`

`api-contract`:

- `Endpoints`
- `Auth`
- `Errors`
- `Compatibility`
- `Tests`

`playtest-report`:

- `Build`
- `Participants`
- `Findings`
- `Evidence`
- `Recommended Changes`

`playtest-session`:

- `Session`
- `Participants`
- `Script`
- `Observations`
- `Captures`

`qa-bug-report`:

- `Build`
- `Reproduction`
- `Expected`
- `Actual`
- `Evidence`

`mockup-review`:

- `Context`
- `Mockups`
- `Feedback`
- `Decision`
- `Follow-up Tasks`

`meeting-notes`:

- `Attendees`
- `Discussion`
- `Decisions`
- `Actions`

`project-note`:

- `Context`
- `Note`
- `Links`
- `Follow-up`

`weekly-update`:

- `Highlights`
- `Progress`
- `Risks`
- `Next Week`

`risk-log`:

- `Risk`
- `Impact`
- `Mitigation`
- `Owner`

`retro-notes`:

- `What Worked`
- `What Did Not`
- `Actions`
- `Owners`

## Live Documents And Historical Records

Live documents are current truth. Keep them consistent when naming, scope, architecture, or ownership changes. Examples:

- Root `README.md`
- `registry.yaml`
- Project `README.md`
- `project.yaml`
- Current design/spec docs
- Active risk logs and weekly updates

Historical records are evidence of what was true when work happened. Do not rewrite them just to match new terminology. Examples:

- Completed or verified task folders
- Finalized meeting notes
- Archived reports
- Append-only events and reviews
- Old task output records

If terminology changes, update live docs and create a decision or project note. For example, if `heroes` becomes `champions`, update the live design docs and project README. Do not edit an old completed task titled `Create hero Athena`; preserve it and add a note linking the terminology decision.

Use statuses:

- `draft`, `live`, `review`: editable current documents.
- `final`, `archived`, `historical`: protected historical documents.

Run `audit-docs` regularly to find terminology drift and master-file inconsistencies.

Use `policies/terminology.yaml` for terminology changes that should be enforced in live docs. Do not make the audit scan force changes to historical task titles. If a live overview must quote an old completed task name, add a narrow `allowed_occurrences` entry with the exact quoted text and a reason.

`asset-brief` and `3d-asset-brief`:

- `Purpose`
- `References`
- Requirements sections appropriate to the asset.
- `Delivery`

`art-handoff`:

- `Source Files`
- `Export Format`
- `Style References`
- `Acceptance`
- `Integration Notes`

`3d-model-handoff`:

- `Scale`
- `Geometry`
- `Materials`
- `LODs`
- `Collision`
- `Export`

## Task Folders And Review Gates

New tasks should use:

```text
tasks/TASK123/
  task.yaml
  notes.md
  outputs.md
  attachments/README.md
```

`record-attempt` or `submit-output` moves a task to `In Review`. `record-attempt` is preferred for normal completion attempts because it clearly preserves attempt history. `Done` and `Verified` require output, acceptance criteria, output commit for code tasks, and an approved review record.

If a PR/MR marks a task `Done` but the output cannot be objectively verified, reject the PR/MR and record `record-verification-failed`. The rejected PR/MR plus the append-only failed verification record is the historical footprint. Do not merge false completed state.

Use `withdraw-output`, `supersede-output`, and `cancel-review` when an output is no longer current or a review stops before a decision. Do not rewrite the old attempt out of history.

## Assets And Mockups

Do not bury assets only in prose. Register every important file, video, mockup, build, model, deck, or capture through `register-asset` or the website.

Use the asset manifest for:

- Figma, Miro, or image links.
- GLB/FBX/Blend/source art links.
- Gameplay videos and playtest recordings.
- Build downloads and release packages.
- Screenshots or QA reproduction clips.

Large files should live in Git LFS, releases/packages, object storage, or implementation repos. The management repo records the link and ownership.

## Task Links

Every task should link to its durable context:

- `project_id`: owning project.
- `target_repo`: implementation repo when relevant.
- `expected_output`: PR, design doc, asset, video, report, build, or review.
- `output`: final submitted artifact.
- `output_commit`: exact implementation commit when a code repo output is submitted.
- `dependencies`: task IDs that must be resolved first.
- `user_update`: latest human-authored status.
- `ai_update`: latest agent-authored status.

Use task events for daily status notes and handoffs. Use task YAML changes for durable task state.
