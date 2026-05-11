# Wiki Guidelines

## Project Home Page

Every project `README.md` should be the first page a human or agent reads.

Required sections:

- `State`: current status, current focus, next review, and major blockers.
- `Repositories`: linked implementation repos and what each repo owns.
- `Documents`: canonical docs grouped by design, engineering, production, reports, release, and decisions.
- `Tasks`: active task IDs and owners.
- `Assets`: important builds, mockups, videos, art, models, captures, and external storage links.
- `Operating Notes`: team conventions, meeting cadence, review expectations, and known constraints.

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

`playtest-report`:

- `Build`
- `Participants`
- `Findings`
- `Evidence`
- `Recommended Changes`

`mockup-review`:

- `Context`
- `Mockups`
- `Feedback`
- `Decision`
- `Follow-up Tasks`

`asset-brief` and `3d-asset-brief`:

- `Purpose`
- `References`
- Requirements sections appropriate to the asset.
- `Delivery`

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
- `dependencies`: task IDs that must be resolved first.
- `user_update`: latest human-authored status.
- `ai_update`: latest agent-authored status.

Use task events for daily status notes and handoffs. Use task YAML changes for durable task state.
