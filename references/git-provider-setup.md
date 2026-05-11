# Git Provider Setup

## Required Inputs

The installer should probe for:

- Provider: `github` or `gitlab`.
- GitHub repository path such as `owner/git-based-project-management`.
- GitLab project path such as `group/subgroup/project-os`.
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
$env:PROJECT_OS_PROVIDER = "github"
$env:PROJECT_OS_GITHUB_REPO = "owner/git-based-project-management"
$env:PROJECT_OS_GITHUB_TOKEN = "<token>"
$env:PROJECT_OS_GITHUB_API_URL = "https://api.github.com"
```

## GitLab Token Scopes

For GitLab:

- `api`
- `read_repository`
- `write_repository`

Environment variables:

```powershell
$env:PROJECT_OS_PROVIDER = "gitlab"
$env:PROJECT_OS_GITLAB_TOKEN = "<token>"
$env:PROJECT_OS_GITLAB_URL = "https://gitlab.garena.com"
$env:PROJECT_OS_GITLAB_PROJECT = "group/project-os"
```

Do not commit tokens. `.project-os/local.json` may store non-secret local defaults only.

## Protected Branches

Protect the default branch:

- Require PRs/MRs.
- Require successful validation.
- Restrict direct pushes to maintainers.
- Require approval for schema/policy changes if the team wants stricter control.

## CI

At minimum, CI should run:

```powershell
python scripts/project_os.py validate --repo .
python scripts/project_os.py compile --repo .
```

If the skill is vendored in a separate path, adapt the script path accordingly.

## Website Deployment

Deploy the website as one of:

- Internal VM/container running the Node.js runtime in `assets/website`.
- Docker image built from `assets/website/Dockerfile`.
- Static host serving generated data plus a separate API service for write proposals.
- Local Python preview through `project_os.py website`.
- Developer local server for small-team use.

The write path needs a backend with a provider token. A fully static deployment can read compiled data, but it cannot create PRs/MRs without an API service.

Node.js container example:

```powershell
docker build -t project-os-website assets\website
docker run --rm -p 8787:8787 -e PROJECT_OS_REPO=/data/project-os -v "C:\path\to\project-os:/data/project-os" project-os-website
```

GitHub PR mode:

```powershell
docker run --rm -p 8787:8787 `
  -e PROJECT_OS_REPO=/data/project-os `
  -e PROJECT_OS_PROVIDER=github `
  -e PROJECT_OS_LIVE_PROPOSALS=1 `
  -e PROJECT_OS_GITHUB_REPO=owner/git-based-project-management `
  -e PROJECT_OS_GITHUB_TOKEN=<token> `
  -v "C:\path\to\project-os:/data/project-os" `
  project-os-website
```

GitLab MR mode:

```powershell
docker run --rm -p 8787:8787 `
  -e PROJECT_OS_REPO=/data/project-os `
  -e PROJECT_OS_PROVIDER=gitlab `
  -e PROJECT_OS_LIVE_PROPOSALS=1 `
  -e PROJECT_OS_GITLAB_URL=https://gitlab.garena.com `
  -e PROJECT_OS_GITLAB_PROJECT=group/project-os `
  -e PROJECT_OS_GITLAB_TOKEN=<token> `
  -v "C:\path\to\project-os:/data/project-os" `
  project-os-website
```
