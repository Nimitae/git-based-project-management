# Architecture

## Principle

Git is canonical. The website, generated dashboards, PR/MR views, and exported views are interfaces over Git state.

## Canonical Surfaces

| Surface | Role | Canonical |
|---|---|---|
| Management repo | Project state, docs, task specs, assets index, policies, events, reviews | Yes |
| Pull requests / merge requests | Durable change approval and audit trail | Yes |
| Website | Read UI and proposal UI | No |
| Implementation repos | Product/game/website/source code | Yes for product code |
| Releases/packages/object storage | Large assets, builds, videos | Yes for binaries |

## Data Model

- Project: a game, software product, tool, website, service, campaign, research stream, or internal process.
- Roadmap: Now/Next/Later planning state for a project.
- Milestone: a release, sprint, vertical slice, or major deliverable with goals and exit criteria.
- Document: a durable Markdown record such as a proposal, game design, technical spec, playtest report, QA report, asset brief, video brief, release plan, postmortem, or decision.
- Task: one owned unit of work with expected output and acceptance criteria.
- Asset: a registered image, video, build, source art file, design file, audio clip, deck, dataset, or external artifact.
- Event: append-only project/task activity update.
- Review: append-only output review decision.

## Recommended Project Folder

```text
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
```

## Document Types

Use these types unless a team extends the schema:

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

## Collaboration Rules

- Durable changes go through pull requests or merge requests.
- The website creates proposals; it does not write directly to the default branch.
- Task status, output attempts, and quick updates use controller commands, website proposals, and append-only event/review files.
- Submitted output moves a task to `In Review`. `Done` and `Verified` require output plus an approved review record.
- If output cannot be objectively verified, reject the PR/MR and record a `verification_failed` attempt event/review so the attempted completion is visible in Git history.
- Each managed project may link multiple implementation repos. Agents must read the management repo first, then inspect only the implementation repos relevant to their assigned work.
- Live documents should be audited for terminology and scope drift. Historical records should be preserved unless an explicit correction is approved.
