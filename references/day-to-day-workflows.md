# Day-To-Day Workflows

Use these examples as the default interaction model for a game/software team.

## Project Manager

Daily read path:

```powershell
git pull
git_pm.py compile --repo .
git_pm.py validate --repo .
git_pm.py audit-docs --repo .
```

Typical updates:

```powershell
git_pm.py create-task --repo . --project-id PROJ1 --title "Prepare Friday playtest checklist" --assigned-to "Maya" --role "Project Manager" --expected-output "Playtest Plan"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type playtest-plan --title "Friday Playtest Plan" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type meeting-notes --title "Sprint Planning 2026-05-11" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type weekly-update --title "Week 20 Project Update" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type risk-log --title "Release Risk Log" --owner "Maya"
git_pm.py add-event --repo . --task-id TASK8 --actor "Maya" --event-type "planning" --message "Checklist ready for design and QA review."
```

PMs should review validation warnings, audit warnings, stale blockers, missing outputs, and tasks waiting for review. Meeting notes, weekly updates, project notes, risk logs, and retrospectives belong in `docs/notes/`; durable decisions belong in `docs/decisions/`.

## Game Designer

Daily read path:

- Project README.
- Current `game-design` docs.
- Assigned design tasks.
- Recent playtest reports and mockup reviews.

Typical updates:

```powershell
git_pm.py update-task --repo . --task-id TASK2 --actor "Gina" --status "In Progress" --user-update "Testing two ability cooldown curves against the latest playtest notes."
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type game-design --title "Ability Tuning Notes" --owner "Gina"
git_pm.py create-doc --repo . --project-id PROJ1 --doc-type project-note --title "Ability Terminology Follow-up" --owner "Gina"
git_pm.py submit-output --repo . --task-id TASK2 --actor "Gina" --output "projects/PROJ1-demo-game-hub/docs/design/DOC9-ability-tuning-notes.md" --message "Ready for programmer implementation review."
```

## Programmer

Daily read path:

- Assigned task YAML.
- Linked design/technical docs.
- `target_repo` implementation repo.
- Dependencies and acceptance criteria.

Typical updates:

```powershell
git_pm.py update-task --repo . --task-id TASK3 --actor "Paul" --status "In Progress" --user-update "Prototype branch is running locally; tuning hooks still missing."
git_pm.py submit-output --repo . --task-id TASK3 --actor "Paul" --output "https://github.com/example/game-client/pull/42" --message "Ability prototype ready; reviewer should check input buffering and cooldown values."
```

## Artist

Daily read path:

- Asset briefs.
- Mockup reviews.
- Assigned art tasks.
- Asset manifest for ownership and delivery format.

Typical updates:

```powershell
git_pm.py register-asset --repo . --project-id PROJ1 --title "HUD icon sheet v1" --asset-type "image" --storage "external-link" --source-url "https://example.com/hud-icons-v1" --used-by "PROJ1,TASK4" --owner "Anika"
git_pm.py submit-output --repo . --task-id TASK4 --actor "Anika" --output "https://example.com/hud-icons-v1" --message "First icon pass ready for game designer review."
```

## 3D Artist

Daily read path:

- `3d-asset-brief` docs.
- Model requirements and references.
- Asset manifest for file links and status.
- Implementation repo import rules if assets are checked into a game repo.

Typical updates:

```powershell
git_pm.py register-asset --repo . --project-id PROJ1 --title "Arena prop blockout" --asset-type "3d-model" --storage "external-link" --source-url "https://example.com/arena-props-blockout.glb" --used-by "PROJ1,TASK5" --owner "Tara"
git_pm.py update-task --repo . --task-id TASK5 --actor "Tara" --status "In Progress" --user-update "Blockout scale pass complete; collision proxy still pending."
```

## Modeller

Daily read path:

- 3D asset task.
- Source model link in the asset manifest.
- Retopology/polycount/UV/texture requirements.

Typical updates:

```powershell
git_pm.py update-task --repo . --task-id TASK6 --actor "Mo" --status "Blocked" --blocker "Waiting for approved prop silhouette from 3D art." --user-update "Ready to retopo once silhouette is locked."
git_pm.py add-event --repo . --task-id TASK6 --actor "Mo" --event-type "handoff" --message "Need final GLB from Tara before retopo."
```

## Backend Engineer

Daily read path:

- Backend spec.
- Task YAML and dependencies.
- API contract docs.
- Linked implementation repo.

Typical updates:

```powershell
git_pm.py update-task --repo . --task-id TASK7 --actor "Bao" --status "In Progress" --target-repo "game-backend" --user-update "Telemetry endpoint implemented; load test pending."
git_pm.py submit-output --repo . --task-id TASK7 --actor "Bao" --output "https://github.com/example/game-backend/pull/18" --message "Reviewer should check schema migration and retry behavior."
```

## Frontend Engineer

Daily read path:

- Frontend spec.
- Mockup review doc.
- Registered mockup/prototype links.
- API contract and target repo.

Typical updates:

```powershell
git_pm.py register-asset --repo . --project-id PROJ1 --title "Signup flow mockup v2" --asset-type "mockup" --storage "external-link" --source-url "https://example.com/figma/signup-v2" --used-by "PROJ1,TASK8" --owner "Fern"
git_pm.py submit-output --repo . --task-id TASK8 --actor "Fern" --output "https://github.com/example/web-portal/pull/9" --message "Signup page ready; backend endpoint is mocked behind feature flag."
```

## Reviewer

Reviewers record outcomes with `review-task`:

```powershell
git_pm.py review-task --repo . --task-id TASK3 --reviewer "Maya" --decision "changes_requested" --notes "Prototype works, but tuning values need to be linked from the design doc."
git_pm.py review-task --repo . --task-id TASK4 --reviewer "Gina" --decision "approved" --notes "Icons match current art direction and are ready for integration."
```

Use `approved` only when output is accessible, acceptance criteria are satisfied, and the task can move to `Verified`.

## Website Workflow

The website exposes the same flows:

- `Tasks`: search and filter.
- `Docs`: find canonical docs.
- `Assets`: find mockups, art, videos, builds, and external files.
- `Updates`: update task status, submit output, add events, and review tasks.
- `Create`: create tasks/docs, register assets, and propose raw file edits.

In dry-run mode, proposals are written under `.project-hub/proposals/`. In live mode, they become GitHub PRs or GitLab MRs.

## Live And Completed Documents

Use live docs for the current truth: project READMEs, `project.yaml`, active specs, current risk logs, weekly updates, and open notes. These should be updated when terminology, scope, owners, links, or repo state changes.

Use completed records as historical evidence: `Done` or `Verified` task folders, finalized meeting notes, archived reports, event logs, and review logs. Do not rewrite old completed files to match a new naming decision. If `heroes` becomes `champions`, update the live docs and create a `decision` or `project-note`; leave an old completed task such as `Create hero Athena` untouched.
