# Architecture

## Principle

Git is canonical. The website, generated dashboards, issues, and exported views are interfaces over Git state.

## Canonical Surfaces

| Surface | Role | Canonical |
|---|---|---|
| Management repo | Project state, docs, task specs, assets index, policies, events, reviews | Yes |
| Pull requests / merge requests | Durable change approval and audit trail | Yes |
| Issues | Task discussion and lightweight updates | Optional |
| Website | Read UI and proposal UI | No |
| Implementation repos | Product/game/website/source code | Yes for product code |
| Releases/packages/object storage | Large assets, builds, videos | Yes for binaries |

## Data Model

- Project: a game, software product, tool, website, service, campaign, research stream, or internal process.
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
```

## Document Types

Use these types unless a team extends the schema:

- `proposal`
- `brief`
- `game-design`
- `technical-spec`
- `playtest-plan`
- `playtest-report`
- `qa-report`
- `research-report`
- `asset-brief`
- `video-brief`
- `build-note`
- `release-plan`
- `postmortem`
- `decision`
- `meeting-notes`

## Collaboration Rules

- Durable changes go through pull requests or merge requests.
- The website creates proposals; it does not write directly to the default branch.
- Task status and quick updates may use issue comments or append-only event files.
- Each managed project may link multiple implementation repos. Agents must read the management repo first, then inspect only the implementation repos relevant to their assigned work.
