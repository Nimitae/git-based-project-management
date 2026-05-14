---
name: git-based-project-management
description: Build, install, initialize, operate, validate, and deploy a Git-first project management/wiki system for small teams on GitHub or GitLab. Use when Codex needs to set up or manage Git-backed project docs, task specs, game/software project state, agent-searchable Markdown/YAML records, GitHub pull requests or GitLab merge requests from website/human edits, role-specific owner/manager/assignee/reviewer workflows, a Docker/Node.js website backed by Git, validation for IDs/dependencies/assets/reviews, or collaboration across multiple linked implementation repositories.
---

# Git-Based Project Management

## Operating Model

Treat Git as the operating system:

- Git repository: canonical source of truth for projects, task specs, project documents, asset manifests, policies, review logs, and durable decisions.
- GitHub PRs or GitLab MRs: approval path for project state changes, document edits, task spec changes, and policy/template changes.
- Event/review files: lightweight task discussion, output attempts, failed verification, withdrawals, supersessions, and review cancellation.
- Website: human interface that reads Git-derived data and turns edits into PRs/MRs instead of mutating canonical state directly.
- Agents: use deterministic scripts first; use LLM judgment only to draft, summarize, review quality, or propose changes.

**Always pull latest Git state before reading files or making edits, and pull regularly during longer sessions.** Project Hub state is shared team knowledge and may change while you are working. Pull before making decisions, before creating or reviewing PRs/MRs, before writing files, before running planning/status summaries, and again after any pause or significant elapsed time. Every `git_pm.py` command automatically runs `git pull --ff-only` before touching files. Use `--no-pull` only when working offline or when you have already pulled in the same session and know no newer commits are needed. If the pull fails (no remote, diverged branch), the command prints a warning and continues so you can still work locally.

**Confirm the target Project Hub before acting.** A single conversation may involve multiple Project Hub repositories, linked implementation repos, or new hubs being initialized. Do not infer the active hub only from the current working directory, previous request, browser tab, or last-used repo when more than one hub is plausible. Before reading, writing, initializing, validating, reviewing, committing, or pushing, ensure the target hub path, provider/repo, project ID, and intended operation are explicit. Ask a concise clarification question when the target hub or operation is ambiguous; this is mandatory before initialization because `init` creates canonical source-of-truth files and website/runtime scaffolding.

**Offer regular user attention checks for each new hub.** When first used to operate a Project Hub for a user, ask whether to set up recurring checks that pull the latest hub state and inspect related PRs/MRs, issues, review requests, comments, mentions, assignments, and relevant commits. If recurring checks are not set up and the user has not explicitly said to stop reminding them, recommend setting them up during each daily Project Hub check-in.

**Check for conflicts before every write operation.** All write commands (`create-task`, `update-task`, `submit-output`, `review-task`, etc.) run a conflict scan before applying changes. If hard errors are found (missing project, missing task), the command always aborts. If only warnings are found (duplicate title, status regression, uncommitted working-tree changes), the command prints them and requires explicit confirmation:

```powershell
# Re-run with --confirm to acknowledge warnings and proceed
git_pm.py create-task ... --confirm

# Or supply a reason, which also counts as confirmation
git_pm.py update-task ... --reason "Reverting to Backlog after scope cut"
```

Note: commands that already require `--reason` (record-verification-failed, withdraw-output, supersede-output, cancel-review) treat the provided reason as automatic confirmation for warnings.

**Use Project Hub scripts as far as possible.** Prefer `scripts/git_pm.py` commands, generated launch scripts, smoke tests, and deterministic project-specific scripts over hand-editing Project Hub files. This applies to initialization, validation, compile/audit, project health checks, task creation/updates, documents, milestones, repo registration, asset registration, events, attempts, reviews, withdrawals, supersessions, cancellation, and website startup. Treat direct YAML/Markdown edits as a fallback for one-off prose or a documented script gap; after any direct edit, run the relevant controller validation/audit/compile commands before committing. If a workflow becomes repeated or structurally important, add or extend a deterministic script or website function instead of continuing manual edits.

**Review proposed content before writing it.** Before adding or modifying Project Hub records, docs, tasks, assets, policies, templates, or reviews from user-provided content, inspect the proposed content itself and compare it against existing repo state. Flag inconsistencies, contradictions, stale assumptions, missing owners or staff emails, ambiguous scope, duplicate records, invalid IDs/dependencies, unverifiable outputs, broken links/assets, leaked secrets, unrealistic status claims, and anything else likely to contaminate canonical project state. Do not silently encode questionable information as source of truth; either resolve it with the user, keep it out of the repo, or put it in a PR/MR with explicit notes for the project owner, team lead, or accountable function owner to review.

**Check existing tasks before suggesting new tasks.** Before suggesting, proposing, or creating a new task, search the current Project Hub for existing tasks with identical, overlapping, or relevant objectives. Compare task title, expected output, acceptance criteria, status, milestone, feature area, dependencies, target repo, linked docs, notes, recent events, and owner/reviewer fields. Use `project-status`, compiled website/search data, the task table, and direct task-folder inspection as needed. If an existing task covers the objective, suggest updating, reopening, splitting, linking, or adding an event to that task instead of creating a duplicate. Create a new task only when the objective is distinct, or explicitly explain why existing related tasks do not cover the requested work.

Keep implementation codebases in their own GitHub/GitLab repos. This management repo stores links, intent, tasks, reviews, and source-of-truth project metadata.

It is acceptable and encouraged to add deterministic scripts, importers, compiled data, or website views when a project develops special navigation or reporting needs that the generic Project Hub does not cover. Examples include scripts that ingest user stories, trace requirements into tasks, or add website pages for project-specific catalogs. Keep these extensions reviewable, documented, validated, committed, and pushed with the rest of the Project Hub.

## Roles

- Owner/Admin: initialize the repo, configure provider permissions, deploy the website, approve schema/policy changes.
- Manager/PM: create projects, documents, and tasks; review PR/MR diffs; run validation; publish the website; inspect blockers and workload.
- Assignee: read assigned tasks, project docs, dependencies, and submit status/output updates through the website, controller commands, or task events.
- Reviewer: verify task outputs against `policies/output-requirements.yaml`, append review records, and move tasks through review states.
- Agent installer: run `doctor --interactive`, collect required credentials/access, and report missing permissions without storing long-lived secrets unless explicitly approved.

Task lifecycle is `Backlog` -> `In Progress`/`Blocked` -> `In Review` -> `Done`/`Verified`. Prefer `record-attempt` for day-to-day completion attempts because it leaves explicit attempt history; `submit-output` is the short convenience path for the same basic transition. Do not directly mark work `Done` or `Verified` unless output, output commit when a code repo is involved, acceptance criteria, and approved review records are present.

Strongly prefer concrete task actors: assignees, reviewers, event actors, and attempt actors should be real staff in `registry.yaml` with an email address, or the field value should be the staff email directly. A new backlog task may keep `assigned_to` empty and use `role` as the placeholder until someone explicitly assigns the work; before active execution, replace the role-only placeholder with a staff email.

Read `references/role-workflows.md` when deciding which fields a role may change.

## Common User Intents

When a user asks what they need to do today, pull latest Git state and run:

```powershell
git_pm.py my-tasks --repo . --user "Bao"
```

Then read the listed task folders, linked docs, recent events, and relevant implementation repos.

When an owner proposes a new feature, create a reviewable feature proposal before creating execution tasks:

```powershell
git_pm.py propose-feature --repo . --project-id PROJ-MNQRV --title "FTUE Data Tracking" --owner "Maya" --problem "Tutorial drop-off is not measurable" --value "Team can diagnose onboarding friction" --scope "Client events, backend ingest, validation dashboard" --task-breakdown "Design event spec; implement client events; add backend ingest; verify staging data"
```

When a manager asks for project health, run:

```powershell
git_pm.py project-status --repo . --project-id PROJ-MNQRV
git_pm.py review-queue --repo .
git_pm.py blocked-tasks --repo .
git_pm.py stale-work --repo .
```

When a reviewer asks what needs review, start with `review-queue`, then inspect each task output before approval. For code tasks, read the task `target_repo`, find that repo in the project `repos` list, and verify the `output_commit` exists in that implementation repo before approving.

When a PM wants a team-facing update on what has changed, run:

```powershell
git_pm.py commit-summary --repo . --since "1 week ago"
# Or save it as a doc in the hub
git_pm.py commit-summary --repo . --since "1 week ago" --project-id PROJ-MNQRV --create-doc
```

When a team wants automated PR/MR triage, run a dry-run first then post when ready:

```powershell
# Preview what the reviewer would say (no API call)
git_pm.py review-mrs --repo . --dry-run

# Post review comments to the provider for all open PRs/MRs
git_pm.py review-mrs --repo . --post
```

## Canonical User Prompts

- "What should I work on today?" Pull latest Git, run `my-tasks`, read assigned task folders, summarize active work, blockers, review responsibilities, and next actions.
- "Create a new feature proposal." Use `propose-feature`; do not create execution tasks until the owner/manager approves or explicitly asks for task breakdown PRs/MRs.
- "Create a new task." Pull latest Git state, search existing tasks for matching or overlapping objectives, and prefer updating/linking an existing task unless the new objective is clearly distinct.
- "Add this implementation repo to the project." Use `register-repo` with project ID, repo name, provider, URL, default branch, and role.
- "Mark my task ready for review." Use `record-attempt` with `--output`, `--target-repo` when applicable, and `--output-commit` when the output is code.
- "Review this task." Verify output access, task acceptance criteria, registered target repo, and output commit. Approve only when objective checks pass; otherwise use `record-verification-failed` or `review-task --decision changes_requested`.
- "What is project health?" Run `project-status`, `review-queue`, `blocked-tasks`, `stale-work`, `audit-docs`, and inspect `repo_state_unknown` in compiled/website data.

## Core Commands

Use `scripts/git_pm.py` for deterministic work before editing canonical Project Hub files directly:

```powershell
& "<python>" "...\git-based-project-management\scripts\git_pm.py" doctor --interactive
& "<python>" "...\git-based-project-management\scripts\git_pm.py" init --repo ".\project-hub" --name "New Project Hub" --owner "Terence" --provider github --github-repo "owner/project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" validate --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" audit-docs --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" compile --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" my-tasks --repo ".\project-hub" --user "Bao"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" project-status --repo ".\project-hub" --project-id PROJ-MNQRV
& "<python>" "...\git-based-project-management\scripts\git_pm.py" review-queue --repo ".\project-hub"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" create-milestone --repo ".\project-hub" --project-id PROJ-MNQRV --title "FTUE Vertical Slice" --owner "Maya"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" propose-feature --repo ".\project-hub" --project-id PROJ-MNQRV --title "FTUE Data Tracking" --owner "Maya"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" register-repo --repo ".\project-hub" --project-id PROJ-MNQRV --name game-client --provider gitlab --url "https://gitlab.garena.com/group/game-client" --default-branch main --role "client/gameplay"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" record-attempt --repo ".\project-hub" --task-id TASK-20260514-BAJQP --actor "Paul" --target-repo game-client --output "https://gitlab.garena.com/group/game/-/merge_requests/42" --output-commit "0123456789abcdef0123456789abcdef01234567" --message "FTUE tracking implementation ready for review."
& "<python>" "...\git-based-project-management\scripts\git_pm.py" website --repo ".\project-hub" --port 8787
& "<python>" "...\git-based-project-management\scripts\git_pm.py" demo --repo ".\demo-game-hub" --name "Demo Game Hub" --owner "Maya"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" commit-summary --repo ".\project-hub" --since "1 week ago"
& "<python>" "...\git-based-project-management\scripts\git_pm.py" commit-summary --repo ".\project-hub" --count 20 --project-id PROJ-MNQRV --create-doc
& "<python>" "...\git-based-project-management\scripts\git_pm.py" review-mrs --repo ".\project-hub" --dry-run
& "<python>" "...\git-based-project-management\scripts\git_pm.py" review-mrs --repo ".\project-hub" --post --provider github
```

Use the copied Project Hub website runtime for the deployable human UI. Project Hub initialization copies the bundled web template into the initialized hub under `website/`, writes local launcher scripts, and initializes the launch environment from that hub's registry/provider settings:

```powershell
cd "C:\path\to\project-hub"
.\start-website.ps1
```

The copied runtime should read from the initialized hub itself (`GPM_REPO` points at the hub root and `GPM_STATIC_DIR` points at `website/static`). The generated launch scripts prefill `GPM_PROVIDER`, `GPM_GITHUB_REPO`, `GPM_GITLAB_URL`, and `GPM_GITLAB_PROJECT` from the initialization inputs; users only add local tokens and opt into live PR/MR creation when ready. Use the source `assets/website` runtime only when developing the skill's website template itself.

Use Docker for container deployment:

```powershell
docker build -t project-hub-website "...\git-based-project-management\assets\website"
docker run --rm -p 8787:8787 -e GPM_REPO=/data/project-hub -v "C:\path\to\project-hub:/data/project-hub" project-hub-website
```

Use the bundled smoke tests before handing a setup to another agent:

```powershell
& "<python>" "...\git-based-project-management\scripts\smoke_test.py"
& "<python>" "...\git-based-project-management\scripts\node_website_smoke_test.py"
```

## Setup Workflow

1. Confirm the exact Project Hub target before initialization or cloning:
   - Whether the user wants a new hub initialized, an existing hub cloned, or an existing local hub updated.
   - Local target path and hub name.
   - Project owner/admin, provider, remote repo path, and default branch expectations.
   - Project ID or initial project scope when multiple projects or hubs are in the same conversation.
2. Run `doctor --interactive` to probe for:
   - Git executable.
   - Python/controller script availability.
   - Node.js availability for the copied website runtime.
   - Provider: `github` or `gitlab`.
   - GitHub repo path such as `owner/project-hub`, or GitLab project path such as `group/project-hub`.
   - Token with repo/API write permission if the website or agent must create PRs/MRs.
   - Local Project Hub repo path.
   - Copied hub launch scripts and website runtime are present and runnable for the user's platform.
   - User role and permission intent.
   If a required executable, runtime, controller script, or hub launcher is missing or not runnable, stop normal setup and prompt the user to install or repair it before treating the Project Hub as ready.
3. Run `init` for a new management repo, or clone an existing repo. Initialization must copy the bundled Node.js website template into the Project Hub as `website/server.mjs` and `website/static/`, generate `start-website.ps1` and `start-website.sh`, and preconfigure those launchers from the hub's provider/repository settings.
4. Ensure initialization embeds the current skill instructions into the Project Hub, including a full copy of `SKILL.md` under `.project-hub/skill/` and a README that references the original skill source repo (`https://github.com/Nimitae/git-based-project-management`) for future updates. This makes the hub self-describing when viewed without the local Codex skill installed.
5. Ask whether to set up regular user attention checks for this hub. These checks should pull latest Git state, inspect PRs/MRs/issues/reviews/comments/mentions related to the user, and report relevant commits since the last check.
6. Confirm the init self-test passed. Initialization runs validation and compile after seeding files and website assets; resolve any reported errors before committing or deploying.
7. Run the copied website from the Project Hub root for review, then deploy that initialized website runtime with Docker or the team's preferred runner.
8. Commit the Project Hub repo and push it to GitHub/GitLab.

Never commit tokens. Prefer environment variables:

- `GPM_PROVIDER`: `github` or `gitlab`.
- `GPM_GITHUB_REPO`: `owner/repo`.
- `GPM_GITHUB_TOKEN`: token for GitHub PR creation.
- `GPM_GITHUB_API_URL`: defaults to `https://api.github.com`.
- `GPM_GITLAB_URL`
- `GPM_GITLAB_PROJECT`
- `GPM_GITLAB_TOKEN`
- `GPM_REPO`

## Daily Workflow

Use Git-local files for project intent:

1. Pull latest Git state at the start, then pull again regularly during the session so decisions use the latest project information.
2. Read `START_HERE_FOR_AGENTS.md`, project README, roadmap, milestone, task folder, and Markdown docs from the local repo.
3. Review any user-proposed additions or edits for consistency with existing repo facts before writing them.
4. Use the website/API or controller to propose changes as PRs/MRs.
5. Use direct task events and attempt/review commands for lightweight execution updates.
6. Run `validate`, `audit-docs`, and `compile` before merging.

## Regular User Attention Checks

For each Project Hub a user asks you to operate, track whether recurring attention checks are configured or explicitly declined:

- On first use of a new hub, offer to set up a recurring check or reminder that pulls the latest Project Hub state and any linked repos needed for assigned work.
- Check GitHub PRs or GitLab MRs involving the user as author, assignee, reviewer, requested reviewer, mention target, or participant with unresolved comments.
- Check issues involving the user as assignee, reporter, mention target, or commenter, including new comments since the last check.
- Check commits made to the Project Hub and linked implementation repos since the last check, then summarize changes that affect the user's tasks, reviews, docs, or decisions.
- If no recurring check is configured and the user has not said "do not remind me again" or equivalent, recommend setting it up during each daily Project Hub check-in.
- When a pull or provider check finds a PR/MR, issue, comment, review request, mention, or commit that needs the user's attention, propose the concrete next action: draft reply, comment, code/doc change, task event, task spec update, commit, or PR/MR. Ask the user whether to proceed before posting, committing, pushing, or changing provider state.

Keep Project Hub repos synchronized after every file change. If an agent or website workflow modifies tracked Project Hub files such as `registry.yaml`, project/task YAML, docs, assets, policies, events, reviews, or templates, it must create a Git commit and push it to the configured remote before reporting the work complete. Do not leave successful Project Hub edits only in the local worktree. For durable changes that require review, push the proposal branch and provide the PR/MR instead of committing directly to the protected default branch. When in doubt, every durable Project Hub file change should land through a PR/MR so the project owner, team lead, or accountable owner for the affected function/domain can review the diff before merge. If commit or push is blocked by credentials, network, branch protection, or validation errors, stop and report the exact branch, files changed, validation state, and next command needed to finish synchronization.

## Project Hub PR/MR Reviewer Checklist

When reviewing a Project Hub PR/MR, review the content diff directly; passing validation is necessary but not sufficient. The reviewer should request changes before merge when the proposed state would make the repo less clean, complete, or trustworthy.

Check for:

- Fact conflicts: new claims must agree with `registry.yaml`, project/task YAML, current docs, decisions, reviews, events, and registered assets.
- Timeline conflicts: dates, sprint names, release windows, milestones, dependencies, needed-by fields, and status transitions must be internally consistent and not contradict historical records.
- Vagueness: reject unclear scope, undefined success criteria, unexplained placeholders, "TBD" in active work, ambiguous owners, or language that cannot guide execution or review.
- Missing information: durable records should include accountable owner, real staff email when work is assigned, project/task IDs, status, acceptance criteria, expected output, target repo when applicable, reviewer, links/assets, and decision context.
- Structural correctness: IDs, dependencies, YAML/frontmatter, doc paths, asset references, event/review records, and task-folder files must match the schema and repository conventions.
- Verifiability: completed or review-bound work must include accessible outputs, output commits for code, objective evidence, and approved review records where required.
- Documentation hygiene: docs should be readable, current, non-duplicative, clearly marked as live or historical, and free of stale assumptions, broken links, leaked secrets, or unsupported assertions.
- Review routing: domain-changing edits should be visible to the project owner, team lead, or accountable function owner before merge.

If the PR/MR is directionally useful but incomplete, leave review comments that name the exact missing facts or contradictions and ask for a follow-up update before merge. Do not merge vague or conflicting project state just to fix it later.

Use PRs/MRs for durable changes:

- Project objective, scope, acceptance criteria, or decision changes.
- Feature proposals and accepted feature scope.
- Task creation/deletion/spec changes.
- Dependency changes.
- Asset manifest changes.
- Review policy/template changes.
- Live document terminology or scope changes.

**Append `Reviewed-By: GBPM` to every commit message when operating a Project Hub using this skill.** This trailer signals that the skill was part of the process — enabling the team to quickly distinguish agent-assisted commits from manual ones in `git log`, `commit-summary` output, and audit trails.

```
git commit -m "feat: add telemetry task and kickoff doc

Reviewed-By: GBPM"
```

When using `git_pm.py` commands that write files, the skill stages and commits on your behalf where applicable (e.g. `init`), and the trailer is added automatically. For commits you make manually after controller commands update files, append the trailer yourself. Every commit that was guided, reviewed, drafted, or proposed with skill assistance counts — the trailer does not mean the skill authored every line, only that it was consulted.

Use task events and attempt/review commands for operational updates:

- Started, blocked, submitted output, output attempt, verification failed, output withdrawn, output superseded, review cancelled, handoff note, quick status update.

Use documents for durable artifacts beyond tasks:

```powershell
git_pm.py propose-feature --repo . --project-id PROJ-MNQRV --title "FTUE Data Tracking" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ-MNQRV --doc-type meeting-notes --title "Sprint Planning 2026-05-11" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ-MNQRV --doc-type project-note --title "FTUE Analytics Notes" --owner "Bao"
git_pm.py create-doc --repo . --project-id PROJ-MNQRV --doc-type risk-log --title "Release Risk Log" --owner "Maya"
git_pm.py create-doc --repo . --project-id PROJ-MNQRV --doc-type decision --title "Rename Heroes To Champions" --owner "Maya"
```

Use controller commands for normal day-to-day updates instead of hand-editing task/event/review YAML or Markdown:

```powershell
git_pm.py register-repo --repo . --project-id PROJ-MNQRV --name game-client --provider github --url "https://github.com/org/game-client" --default-branch main --role "client/gameplay"
git_pm.py update-task --repo . --task-id TASK-20260514-BAJQP --actor "Paul" --status "In Progress" --target-repo "game-client" --user-update "Prototype branch is running locally."
git_pm.py submit-output --repo . --task-id TASK-20260514-BAJQP --actor "Paul" --target-repo "game-client" --output "https://github.com/org/game-client/pull/42" --output-commit "0123456789abcdef0123456789abcdef01234567" --message "Ready for review."
git_pm.py record-attempt --repo . --task-id TASK-20260514-BAJQP --actor "Paul" --target-repo "game-client" --output "https://github.com/org/game-client/pull/42" --output-commit "0123456789abcdef0123456789abcdef01234567" --message "Ready for objective verification."
git_pm.py record-verification-failed --repo . --task-id TASK-20260514-BAJQP --reviewer "Maya" --reason "PR link is inaccessible to the reviewer account."
git_pm.py supersede-output --repo . --task-id TASK-20260514-BAJQP --actor "Paul" --new-output "https://github.com/org/game-client/pull/43" --reason "Replaced inaccessible PR with the correct branch."
git_pm.py withdraw-output --repo . --task-id TASK-20260514-BAJQP --actor "Paul" --reason "Output is obsolete after scope changed."
git_pm.py cancel-review --repo . --task-id TASK-20260514-BAJQP --actor "Maya" --reason "Review cancelled because the output was withdrawn."
git_pm.py review-task --repo . --task-id TASK-20260514-BAJQP --reviewer "Maya" --decision "approved" --notes "Accepted."
git_pm.py register-asset --repo . --project-id PROJ-MNQRV --title "HUD mockup v2" --asset-type "mockup" --source-url "https://example.com/mockup" --used-by "PROJ-MNQRV,TASK-CQRSV" --owner "Fern"
```

New tasks live in folders: `task.yaml`, `notes.md`, `outputs.md`, and `attachments/README.md`. Use the task folder for task-local context and link large artifacts through the asset manifest.

If a PR/MR marks a task `Done` but the output cannot be objectively verified, reject the PR/MR and record `record-verification-failed` against the task in a follow-up proposal or review branch. If the output is accessible but quality/scope is insufficient, record `changes_requested` through `review-task`.

Run `audit-docs` regularly, especially before planning reviews or release reviews. It checks validation, expected master files, live docs, terminology drift, and blocked task details. Configure terminology checks in `policies/terminology.yaml`; use narrow `allowed_occurrences` for exact historical references that should remain unchanged.

Treat live docs and historical records differently. Update live docs when terminology changes, such as renaming `heroes` to `champions`. Do not rewrite completed task records, finalized meeting notes, archived reports, append-only events, or reviews just to match new terminology. Instead, create a `decision` or `project-note` that explains the change.

## Commit Summary (PM Team Update)

`commit-summary` reads git commits, correlates them to hub entities (tasks, docs, policies, registry), and produces a PM-style team update. Use it whenever you need to brief the team on what landed, what needs attention, or what to discuss next.

**What the output includes:**
- **Period and contributors** — date range, commit count, authors
- **What changed** — tasks touched (with status), docs updated, policies or registry changed
- **Needs team alignment** — tasks in review without a reviewer, blocked tasks, policy changes with compliance implications
- **Suggested discussion topics** — review-ready tasks, feature proposals, completed milestones
- **Commit log** — raw subjects for reference

**Options:**
```powershell
# Last 20 commits
git_pm.py commit-summary --repo . --count 20

# Last week
git_pm.py commit-summary --repo . --since "1 week ago"

# Save as a meeting-notes doc in the hub
git_pm.py commit-summary --repo . --since "1 week ago" --project-id PROJ-MNQRV --create-doc

# Machine-readable JSON for further processing
git_pm.py commit-summary --repo . --since "1 week ago" --json
```

**Schedule with the schedule skill:** set up a weekly agent that runs `commit-summary --create-doc` and posts the result to the team channel.

## Automated MR / PR Review

`review-mrs` fetches all open PRs/MRs from the hub's provider, runs deterministic hub checks against each linked task, and optionally posts a structured review comment. Use it to give submitters immediate feedback without waiting for a human reviewer.

**Deterministic checks performed per PR:**
- Task ID (e.g. `TASK-20260514-BAJQP`) referenced in PR title or body
- Task is in `In Review` status
- Task has an `output` field set (matching the PR URL)
- `output_commit` is set when a `target_repo` is registered
- Task has `acceptance_criteria` defined
- A `reviewer` is assigned to the task
- PR has a substantive description (> 30 characters)

**Failures** (items marked `[ ]`) block approval; **warnings** (items marked `[~]`) are shown but do not block. The comment also lists the task's acceptance criteria and the hub's output policy checklist from `policies/output-requirements.yaml`.

**Options:**
```powershell
# Preview what the review comment would say (no API call)
git_pm.py review-mrs --repo . --dry-run

# Post review comments to all open PRs/MRs
git_pm.py review-mrs --repo . --post

# Limit to 5 PRs and use explicit credentials
git_pm.py review-mrs --repo . --post --limit 5 --github-repo owner/hub --github-token $env:GH_TOKEN

# GitLab
git_pm.py review-mrs --repo . --post --provider gitlab --gitlab-url https://gitlab.example.com --gitlab-project group/hub --gitlab-token $env:GITLAB_TOKEN

# JSON output for scripting
git_pm.py review-mrs --repo . --json
```

**Credentials:** provider tokens are read from `--github-token` / `--gitlab-token`, or from `GPM_GITHUB_TOKEN` / `GPM_GITLAB_TOKEN` environment variables, or from the registry. Never commit tokens.

**Schedule with the schedule skill:** run `review-mrs --post` on a cron (e.g. every 6 hours) so submitters get automated feedback the same day they open a PR. Combine with `commit-summary --create-doc` in the same scheduled agent for a fully automated PM loop.

## References

- `references/architecture.md`: canonical data model, Git/website/PR/MR boundaries, and collaboration rules.
- `references/operating-model.md`: lifecycle, verification rule, planning structure, and task-folder model.
- `references/schemas.md`: repository layout and file schemas.
- `references/wiki-guidelines.md`: required wiki page shapes, document sections, asset registration, and task-linking rules.
- `references/day-to-day-workflows.md`: role-specific workflows for PMs, game designers, programmers, artists, 3D artists, modellers, backend engineers, frontend engineers, and reviewers.
- `references/agent-entrypoints.md`: exact behavior for common day-to-day user prompts.
- `references/role-workflows.md`: owner/manager/assignee/reviewer/agent rules.
- `references/git-provider-setup.md`: GitHub/GitLab tokens, repository permissions, PR/MR creation, and deployment guidance.
- `references/website.md`: website behavior, API endpoints, proposal flow, and deployment options.
- `references/attempt-workflows.md`: output attempts, failed verification, withdrawals, supersessions, and cancellation.
- `references/team-cadence.md`: daily/weekly/release operating rhythm for a six-person team.

## Safety Rules

- Always pull latest Git state before reading or modifying project files (`git pull --ff-only`) and repeat pulls regularly during longer work or review sessions. Use `--no-pull` only when explicitly working offline or when you have already pulled in the same session and have a concrete reason not to refresh.
- Do not initialize, mutate, validate, review, commit, or push a Project Hub when multiple hubs are plausible until the target hub path/repo and intended operation are explicit. Ask for clarification instead of guessing, especially before running `init`.
- Do not let user-attention checks mutate provider state or repo state automatically. Draft replies, comments, changes, commits, or PRs/MRs are proposals until the user approves the specific action.
- Always check for conflicts before applying any write operation. Hard errors (missing project, missing task) block the command unconditionally. Warnings (duplicate titles, status regression, uncommitted changes) block the command until the requestor re-runs with `--confirm` or `--reason`. Document the reason when overriding a warning.
- Always review user-proposed content before adding it to canonical Project Hub files. Flag and stop on contradictions, bad assumptions, broken references, missing accountable owners, unverifiable claims, duplicate work, unsafe links/assets, or secrets instead of normalizing them into the repo for someone to clean up later.
- Do not suggest or create a new task until existing tasks have been checked for identical, overlapping, or relevant objectives. Prefer updating or linking existing work when it already covers the request.
- Do not trust hand-copied IDs. Allocate IDs through the controller or website backend and validate every PR/MR.
- Do not use Git Issues as task state for this workflow. Use Git files, event/review logs, and PRs/MRs.
- Always append `Reviewed-By: GBPM` to commit messages when the skill was consulted during the work. The `init` command adds this trailer automatically; append it manually on all other commits made while operating a Project Hub.
- Do not let the website mutate the default branch directly. It must create a branch and PR/MR, or produce a local proposal in dry-run mode.
- Do not store binary-heavy assets directly in normal Git. Use Git LFS, Releases/Packages, object storage, or external product repos, and register them in `assets/assets.yaml`.
- Do not treat generated website data as canonical. Rebuild it from Markdown/YAML.
- Do not bypass validation when merging structural changes.
- Do not rewrite completed tasks, finalized docs, append-only events, or reviews to match current terminology. Preserve them and add a live decision/project note instead.
- Do not merge invalid completed state. Failed objective verification should block the PR/MR instead of producing a false `Done` record.
