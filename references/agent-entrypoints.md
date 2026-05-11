# Agent Entrypoints

Use this file when the user asks normal day-to-day project questions.

## What Do I Need To Do Today?

1. Pull latest Git state.
2. Run:

```powershell
git_pm.py my-tasks --repo . --user "<name>"
```

3. Read each returned task folder:

- `task.yaml`
- `notes.md`
- `outputs.md`
- linked docs
- linked implementation repo from `target_repo`
- recent events and reviews for that task

4. Report:

- active tasks
- blocked tasks
- tasks waiting for the user as reviewer
- expected output
- next concrete action
- linked repo/doc paths

## Owner Wants To Propose A Feature

Do not jump straight into tasks unless the owner explicitly asks for execution tasks.

Create a feature proposal:

```powershell
git_pm.py propose-feature --repo . --project-id PROJ1 --title "Feature Name" --owner "Owner Name"
```

Fill or propose these sections:

- Problem
- Player/User Value
- Proposed Scope
- Non-Goals
- Risks
- Task Breakdown
- Decision Needed

After the proposal is approved, create milestones and tasks:

```powershell
git_pm.py create-milestone --repo . --project-id PROJ1 --title "Feature Milestone" --owner "Maya"
git_pm.py create-task --repo . --project-id PROJ1 --title "Implement client events" --assigned-to "Paul" --role "Programmer" --expected-output "Pull Request"
```

## Manager Wants Project Health

Run:

```powershell
git_pm.py project-status --repo . --project-id PROJ1
git_pm.py review-queue --repo .
git_pm.py blocked-tasks --repo .
git_pm.py stale-work --repo .
git_pm.py audit-docs --repo .
```

Report:

- current project counts
- blocked tasks
- stale tasks
- review queue
- failed verification
- active feature proposals
- validation/document audit issues
- decisions needed

## Reviewer Wants Work To Review

Run:

```powershell
git_pm.py review-queue --repo .
```

For each item:

1. Open the task folder.
2. Open the output link.
3. Run objective checks where possible.
4. Choose one:

```powershell
git_pm.py review-task --repo . --task-id TASK# --reviewer "Name" --decision approved --notes "Accepted."
git_pm.py review-task --repo . --task-id TASK# --reviewer "Name" --decision changes_requested --notes "Concrete revision needed."
git_pm.py record-verification-failed --repo . --task-id TASK# --reviewer "Name" --reason "Objective check failed."
```

## Source Of Truth Rules

- Management repo: project intent, tasks, docs, decisions, events, reviews, attempts, links.
- Implementation repos: source code, game code, services, websites, product assets that belong with code.
- Releases/packages/object storage: large builds, videos, captures, source art, model files, datasets.
- Website: human interface over Git state, not the canonical database.
- PRs/MRs: approval and audit path for durable changes.

