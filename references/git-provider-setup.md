# Git Provider Setup

## Required Inputs

The installer should probe for:

- Provider: `github` or `gitlab`.
- GitHub repository path such as `owner/git-based-project-management`.
- GitLab project path such as `group/subgroup/project-hub`.
- Local clone path.
- User role: owner, manager, assignee, reviewer, or installer.
- Token availability.

## GitHub Token Scopes

For GitHub.com classic tokens:

- `repo` for private repositories, or `public_repo` for public repositories.

For fine-grained tokens:

- Repository contents: Read and write.
- Pull requests: Read and write.
- Metadata: Read-only.

Environment variables:

```powershell
$env:GPM_PROVIDER = "github"
$env:GPM_GITHUB_REPO = "owner/git-based-project-management"
$env:GPM_GITHUB_TOKEN = "<token>"
$env:GPM_GITHUB_API_URL = "https://api.github.com"
```

## GitLab Token Scopes

For GitLab:

- `api`
- `read_repository`
- `write_repository`

Environment variables:

```powershell
$env:GPM_PROVIDER = "gitlab"
$env:GPM_GITLAB_TOKEN = "<token>"
$env:GPM_GITLAB_URL = "https://gitlab.garena.com"
$env:GPM_GITLAB_PROJECT = "group/project-hub"
```

Do not commit tokens. `.project-hub/local.json` may store non-secret local defaults only.

## Protected Branches

Protect the default branch:

- Require PRs/MRs.
- Require successful validation.
- Restrict direct pushes to maintainers.
- Require approval for schema/policy changes if the team wants stricter control.

## CI

At minimum, CI should run:

```powershell
python scripts/git_pm.py validate --repo .
python scripts/git_pm.py audit-docs --repo .
python scripts/git_pm.py compile --repo .
```

If the skill is vendored in a separate path, adapt the script path accordingly.

Run the audit on every PR/MR and on a scheduled cadence before planning or release reviews. It is the check that catches master-file drift, missing policy files, terminology drift in live docs, and blocked tasks without blocker detail.

Treat validation errors as merge blockers. In particular, a PR/MR that marks a task `Done` or `Verified` without output and an approved review record should be rejected before merge.

## Website Deployment

Deploy the website as one of:

- Internal VM/container running the Node.js runtime in `assets/website`.
- Docker image built from `assets/website/Dockerfile`.
- Static host serving generated data plus a separate API service for write proposals.
- Local Python preview through `git_pm.py website`.
- Developer local server for small-team use.

The write path needs a backend with a provider token. A fully static deployment can read compiled data, but it cannot create PRs/MRs without an API service.

Node.js container example:

```powershell
docker build -t project-hub-website assets\website
docker run --rm -p 8787:8787 -e GPM_REPO=/data/project-hub -v "C:\path\to\project-hub:/data/project-hub" project-hub-website
```

GitHub PR mode:

```powershell
docker run --rm -p 8787:8787 `
  -e GPM_REPO=/data/project-hub `
  -e GPM_PROVIDER=github `
  -e GPM_LIVE_PROPOSALS=1 `
  -e GPM_GITHUB_REPO=owner/git-based-project-management `
  -e GPM_GITHUB_TOKEN=<token> `
  -v "C:\path\to\project-hub:/data/project-hub" `
  project-hub-website
```

GitLab MR mode:

```powershell
docker run --rm -p 8787:8787 `
  -e GPM_REPO=/data/project-hub `
  -e GPM_PROVIDER=gitlab `
  -e GPM_LIVE_PROPOSALS=1 `
  -e GPM_GITLAB_URL=https://gitlab.garena.com `
  -e GPM_GITLAB_PROJECT=group/project-hub `
  -e GPM_GITLAB_TOKEN=<token> `
  -v "C:\path\to\project-hub:/data/project-hub" `
  project-hub-website
```
