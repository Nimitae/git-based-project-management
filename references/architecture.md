# Architecture

## Principle

Git is canonical. The website, generated dashboards, GitHub/GitLab Issues, and any exported documents are interfaces over Git state.

## Canonical Surfaces

| Surface | Role | Canonical |
|---|---|---|
| Project OS Git repo | Wiki docs, specs, registry, policies, events, reviews | Yes |
| GitHub PRs / GitLab MRs | Durable change approval and audit trail | Yes |
| GitHub/GitLab Issues | Task discussion and lightweight work updates | Optional |
| Project OS website | Read UI and MR proposal UI | No |
| Implementation repos | Product/game/website source code | Yes for product code |
| Object storage/Git LFS/GitLab Releases | Large assets, videos, builds | Yes for binaries |

## Entity Model

- Initiative: strategic why.
- Project: durable product, system, feature, process, or game.
- EW: experiment/workstream under a project.
- Task: owned execution unit with one primary owner and one expected output.
- Asset: image, video, build, design file, deck, or external artifact.
- Task event: append-only execution update.
- Task review: append-only review decision.

## Sync Rules

- Project/EW/task specs live in Markdown/YAML and are changed through MRs.
- Website edits become PR/MR proposals, never direct writes to the default branch.
- Generated `site-data/project-os.json` is rebuilt from canonical files.
- GitHub Actions or GitLab CI should run `project_os.py validate` before allowing merge.
- If optional Google Docs are used later, treat them as generated reflections and import direct human edits into MRs before accepting them.

## Migration From Google Workspace

Keep these concepts:

- Stable IDs: `INIT#`, `PROJ#`, `EW#`, `TASK#`, `ASSET#`.
- Output requirements and verification policy.
- Append-only task reviews.
- Current task status plus append-only events.

Change these concepts:

- Replace Sheet-as-database with Git registry/spec files.
- Replace Docs-as-collaboration-source with website/MR editing.
- Replace Drive-link-only assets with an asset registry that can reference Git LFS, GitLab Releases, object storage, product repos, Figma, or Drive if retained.

## External Product Repos

Project OS may link separate implementation repositories. Store links at project/EW/task level:

```json
{
  "repos": [
    {
      "name": "game-client",
      "provider": "gitlab",
      "url": "https://gitlab.garena.com/group/game-client",
      "default_branch": "main",
      "role": "implementation"
    }
  ]
}
```

Tasks that require code should declare `target_repo` and expect a Merge Request/Pull Request output.
