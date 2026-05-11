# Team Cadence

This cadence assumes a small team of around six people using Git as the project management source of truth.

## Daily

Each collaborator:

- Pulls the latest management repo.
- Runs `git_pm.py my-tasks --repo . --user "<name>"`.
- Reads assigned task folders and linked live docs.
- Checks relevant implementation repos only after understanding the management repo state.
- Records blockers, handoffs, notes, and output attempts through the controller or website.

The project manager:

- Runs `git_pm.py project-status --repo .`.
- Reviews blocked tasks.
- Reviews the website review queue.
- Checks new PR/MR proposals for task, doc, asset, milestone, and policy changes.
- Checks active feature proposals before creating execution tasks.

## Twice Weekly

The team reviews:

- Roadmap `now` / `next` / `later`.
- Active milestone scope and exit criteria.
- Stale `In Review` items.
- Failed verification records.
- Live docs that may conflict with current terminology or scope.

## Weekly

Run:

```powershell
git_pm.py validate --repo .
git_pm.py audit-docs --repo .
git_pm.py compile --repo .
```

The manager should update live master files through PRs/MRs:

- Root/project README.
- `project.yaml`.
- Roadmap.
- Milestones.
- Active specs.
- Risk logs.
- Current asset manifests.

Completed tasks, finalized notes, archived reports, event logs, and review logs stay historical.

## Milestone Or Release Review

Before marking work `Done` or `Verified`:

- Confirm every task has output, acceptance criteria, and approved review.
- Confirm objective checks can access the output.
- Confirm failed or withdrawn attempts are recorded.
- Confirm live docs match shipped terminology and scope.
- Confirm large artifacts are registered and stored in the correct system.

## Manager Agent Prompt

Use this prompt pattern when asking an agent to inspect project health:

```text
Pull the latest Project Hub repo. Read registry.yaml, the project README, roadmap, active milestones, live docs, task folders, events, reviews, and the review queue. Report blockers, stale review items, failed verification, missing outputs, terminology drift, and PR/MR proposals that need human decision. Do not use Git Issues; use Git files and PR/MR state only.
```
