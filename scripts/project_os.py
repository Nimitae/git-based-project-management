#!/usr/bin/env python3
"""Dependency-light controller for a Git-first Project OS."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, parse, request


SKILL_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = SKILL_ROOT / "assets" / "website" / "static"
ID_PREFIX = {
    "initiative": "INIT",
    "project": "PROJ",
    "ew": "EW",
    "task": "TASK",
    "asset": "ASSET",
    "event": "EVENT",
    "review": "REVIEW",
}
ENTITY_BY_KIND = {
    "initiative": "initiatives",
    "project": "projects",
    "ew": "ews",
    "task": "tasks",
}
TASK_STATUSES = {"Backlog", "In Progress", "Blocked", "Done", "Verified", "Iceboxed"}
CHECKPOINTS = {"", "Drafting", "Pending Approval", "Revising", "Ready"}


class ProjectOSError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "change"


def repo_arg(value: str | None) -> Path:
    return Path(value or os.environ.get("PROJECT_OS_REPO") or ".").resolve()


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def safe_repo_path(repo: Path, rel: str) -> Path:
    clean = rel.replace("\\", "/").lstrip("/")
    candidate = (repo / clean).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError as exc:
        raise ProjectOSError(f"path escapes repo: {rel}") from exc
    return candidate


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json_subset(path: Path, default):
    if not path.exists():
        return copy.deepcopy(default)
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return copy.deepcopy(default)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectOSError(
            f"{path} must use JSON-subset YAML so this skill can validate without external dependencies: {exc}"
        ) from exc


def dump_yaml_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def registry_path(repo: Path) -> Path:
    return repo / "registry.yaml"


def load_registry(repo: Path) -> dict:
    return read_json_subset(registry_path(repo), default={})


def save_registry(repo: Path, registry: dict) -> None:
    write_text(registry_path(repo), dump_yaml_json(registry))


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"error": f"invalid jsonl at {path}:{lineno}", "raw": line})
    return rows


def git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True)
    if check and result.returncode != 0:
        raise ProjectOSError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result


def git_commit(repo: Path) -> str:
    result = git(["rev-parse", "--short", "HEAD"], repo)
    return result.stdout.strip() if result.returncode == 0 else ""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip("\n")
    data = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, body


def markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def markdown_doc(frontmatter: dict, title: str, body: str) -> str:
    fm = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    return f"---\n{fm}\n---\n\n# {title}\n\n{body.strip()}\n"


def allocate_id(registry: dict, kind: str) -> str:
    prefix = ID_PREFIX[kind]
    entity_name = ENTITY_BY_KIND.get(kind)
    existing = set(registry.get("entities", {}).get(entity_name, {}).keys()) if entity_name else set()
    next_ids = registry.setdefault("next_ids", {})
    number = int(next_ids.get(kind, 1))
    while f"{prefix}{number}" in existing:
        number += 1
    next_ids[kind] = number + 1
    return f"{prefix}{number}"


def ensure_base_registry(name: str, owner: str, provider: str, github_repo: str, gitlab_url: str, gitlab_project: str) -> dict:
    return {
        "schema_version": 1,
        "name": name,
        "provider": provider,
        "github": {
            "api_url": "https://api.github.com",
            "repo": github_repo,
            "default_branch": "main",
        },
        "gitlab": {
            "url": gitlab_url,
            "project_path": gitlab_project,
            "default_branch": "main",
        },
        "next_ids": {
            "initiative": 2,
            "project": 2,
            "ew": 2,
            "task": 2,
            "asset": 1,
            "event": 1,
            "review": 1,
        },
        "people": [{"name": owner, "role": "Owner", "email": ""}],
        "entities": {
            "initiatives": {
                "INIT1": {
                    "name": "Default Initiative",
                    "path": "initiatives/INIT1.md",
                    "owner": owner,
                    "status": "Active",
                }
            },
            "projects": {
                "PROJ1": {
                    "initiative_id": "INIT1",
                    "name": name,
                    "path": "projects/PROJ1/project.md",
                    "owner": owner,
                    "status": "Active",
                    "repos": [],
                }
            },
            "ews": {
                "EW1": {
                    "project_id": "PROJ1",
                    "initiative_id": "INIT1",
                    "name": "Project OS Setup",
                    "path": "projects/PROJ1/ews/EW1.md",
                    "owner": owner,
                    "status": "Running",
                }
            },
            "tasks": {
                "TASK1": {
                    "ew_id": "EW1",
                    "project_id": "PROJ1",
                    "path": "projects/PROJ1/tasks/TASK1.yaml",
                    "title": "Confirm Project OS setup",
                    "assigned_to": owner,
                    "status": "Backlog",
                    "expected_output": "Setup Confirmation",
                }
            },
        },
    }


def sample_task(task_id: str, ew_id: str, project_id: str, title: str, owner: str, expected_output: str) -> dict:
    return {
        "id": task_id,
        "ew_id": ew_id,
        "project_id": project_id,
        "title": title,
        "assigned_to": owner,
        "role": "PM",
        "status": "Backlog",
        "checkpoint": "Drafting",
        "deadline": "",
        "expected_output": expected_output,
        "acceptance_criteria": ["Repository validates", "Website loads locally"],
        "dependencies": [],
        "target_repo": "",
        "output": "",
        "ai_update": "",
        "user_update": "",
    }


def write_initial_files(repo: Path, registry: dict) -> None:
    write_text(
        repo / ".gitignore",
        "\n".join(
            [
                ".project-os/local.json",
                ".project-os/proposals/",
                "*.log",
                "__pycache__/",
                "",
            ]
        ),
    )
    write_text(repo / "registry.yaml", dump_yaml_json(registry))
    write_text(
        repo / "initiatives/INIT1.md",
        markdown_doc(
            {
                "id": "INIT1",
                "type": "initiative",
                "owner": registry["entities"]["initiatives"]["INIT1"]["owner"],
                "status": "Active",
            },
            "INIT1 - Default Initiative",
            """
## Summary

Initial initiative created by Git-Based Project Management.

## Goals

- Keep project knowledge in Git.
- Route durable changes through merge requests.

## Change Log

- Created initial initiative.
""",
        ),
    )
    write_text(
        repo / "projects/PROJ1/project.md",
        markdown_doc(
            {
                "id": "PROJ1",
                "type": "project",
                "initiative_id": "INIT1",
                "owner": registry["entities"]["projects"]["PROJ1"]["owner"],
                "status": "Active",
            },
            f"PROJ1 - {registry['entities']['projects']['PROJ1']['name']}",
            """
## Summary

This project was initialized from the Git-Based Project Management skill.

## Goals

- Validate the repo structure.
- Deploy the Project OS website.
- Confirm PR/MR-based editing works.

## Repositories

Add implementation repositories here or in `registry.yaml`.

## Change Log

- Created initial project.
""",
        ),
    )
    write_text(
        repo / "projects/PROJ1/ews/EW1.md",
        markdown_doc(
            {
                "id": "EW1",
                "type": "ew",
                "project_id": "PROJ1",
                "initiative_id": "INIT1",
                "owner": registry["entities"]["ews"]["EW1"]["owner"],
                "status": "Running",
            },
            "EW1 - Project OS Setup",
            """
## Summary

Set up the Git-first Project OS repository and website.

## Acceptance Criteria

- `project_os.py validate` passes.
- The website loads against this repo.
- Team roles and permissions are confirmed.

## Linked Tasks

- TASK1
""",
        ),
    )
    task = sample_task("TASK1", "EW1", "PROJ1", "Confirm Project OS setup", registry["people"][0]["name"], "Setup Confirmation")
    write_text(repo / "projects/PROJ1/tasks/TASK1.yaml", dump_yaml_json(task))
    write_text(
        repo / "assets/assets.yaml",
        dump_yaml_json({"assets": {}}),
    )
    write_text(
        repo / "policies/output-requirements.yaml",
        dump_yaml_json(
            {
                "schema_version": 1,
                "common": {
                    "requires_output_link": True,
                    "requires_accessible_source": True,
                },
                "output_types": {
                    "Setup Confirmation": {
                        "matches": ["Setup Confirmation"],
                        "manual_checks": ["Repository validates", "Website loads locally"],
                        "insights_reports": {"create_on_verified": False},
                    },
                    "Design Doc": {
                        "matches": ["Design Doc", "Concept Doc", "Spec"],
                        "manual_checks": ["Problem is clear", "Acceptance criteria are testable"],
                        "insights_reports": {"create_on_verified": False},
                    },
                    "Merge Request": {
                        "matches": ["Merge Request", "Implementation PR", "Implementation MR"],
                        "manual_checks": ["MR links to task", "Tests or verification notes are present"],
                        "insights_reports": {"create_on_verified": False},
                    },
                    "Report": {
                        "matches": ["Report", "Playtest Report", "QA Report", "Research Report"],
                        "manual_checks": ["Findings are evidence-backed", "Next actions are clear"],
                        "insights_reports": {"create_on_verified": True, "default_tag": "report"},
                    },
                },
            }
        ),
    )
    write_text(repo / "events/task-events.jsonl", "")
    write_text(repo / "reviews/task-reviews.jsonl", "")
    (repo / ".project-os/site-data").mkdir(parents=True, exist_ok=True)


def cmd_init(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    repo.mkdir(parents=True, exist_ok=True)
    if registry_path(repo).exists() and not args.force:
        raise ProjectOSError(f"{registry_path(repo)} already exists; pass --force to overwrite generated seed files")
    registry = ensure_base_registry(args.name, args.owner, args.provider, args.github_repo, args.gitlab_url, args.gitlab_project)
    write_initial_files(repo, registry)
    if args.git_init and not (repo / ".git").exists():
        git(["init", "-b", "main"], repo, check=True)
        git(["add", "."], repo, check=True)
        git(["commit", "-m", "Initialize Project OS"], repo, check=False)
    print(f"Initialized Project OS repo at {repo}")
    print("Next: run validate, compile, then website.")
    return 0


def issue(level: str, code: str, message: str, path: str = "") -> dict:
    return {"level": level, "code": code, "message": message, "path": path}


def max_suffix(ids: list[str], prefix: str) -> int:
    found = []
    for item in ids:
        match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", item)
        if match:
            found.append(int(match.group(1)))
    return max(found) if found else 0


def validate_repo(repo: Path) -> list[dict]:
    issues: list[dict] = []
    if not registry_path(repo).exists():
        return [issue("error", "REGISTRY_MISSING", "registry.yaml is missing", "registry.yaml")]
    try:
        registry = load_registry(repo)
    except ProjectOSError as exc:
        return [issue("error", "REGISTRY_PARSE", str(exc), "registry.yaml")]
    entities = registry.get("entities", {})
    required_sections = ["initiatives", "projects", "ews", "tasks"]
    for section in required_sections:
        if not isinstance(entities.get(section), dict):
            issues.append(issue("error", "REGISTRY_SECTION", f"entities.{section} must exist", "registry.yaml"))
    for kind, section in ENTITY_BY_KIND.items():
        prefix = ID_PREFIX[kind]
        records = entities.get(section, {})
        for entity_id, row in records.items():
            if not re.fullmatch(rf"{prefix}\d+", entity_id):
                issues.append(issue("error", "ID_FORMAT", f"{entity_id} should match {prefix}#", "registry.yaml"))
            path = row.get("path", "")
            if not path:
                issues.append(issue("error", "PATH_MISSING", f"{entity_id} has no path", "registry.yaml"))
                continue
            if not safe_repo_path(repo, path).exists():
                issues.append(issue("error", "PATH_MISSING", f"{entity_id} path does not exist", path))
        next_value = int(registry.get("next_ids", {}).get(kind, 1))
        expected_min = max_suffix(list(records.keys()), prefix) + 1
        if next_value < expected_min:
            issues.append(issue("error", "NEXT_ID_STALE", f"next_ids.{kind}={next_value} should be at least {expected_min}", "registry.yaml"))
    for project_id, project in entities.get("projects", {}).items():
        init_id = project.get("initiative_id", "")
        if init_id not in entities.get("initiatives", {}):
            issues.append(issue("error", "REL_PROJECT_INITIATIVE", f"{project_id} references missing {init_id}", project.get("path", "")))
    for ew_id, ew in entities.get("ews", {}).items():
        project_id = ew.get("project_id", "")
        init_id = ew.get("initiative_id", "")
        if project_id not in entities.get("projects", {}):
            issues.append(issue("error", "REL_EW_PROJECT", f"{ew_id} references missing {project_id}", ew.get("path", "")))
        elif init_id and init_id != entities["projects"][project_id].get("initiative_id"):
            issues.append(issue("error", "REL_EW_INITIATIVE", f"{ew_id} initiative does not match parent project", ew.get("path", "")))
    for task_id, task_ref in entities.get("tasks", {}).items():
        task_path = safe_repo_path(repo, task_ref.get("path", ""))
        try:
            task = read_json_subset(task_path, {})
        except ProjectOSError as exc:
            issues.append(issue("error", "TASK_PARSE", str(exc), task_ref.get("path", "")))
            continue
        if task.get("id") != task_id:
            issues.append(issue("error", "TASK_ID_MISMATCH", f"{task_ref.get('path')} id is {task.get('id')}, expected {task_id}", task_ref.get("path", "")))
        ew_id = task.get("ew_id") or task_ref.get("ew_id")
        if ew_id not in entities.get("ews", {}):
            issues.append(issue("error", "REL_TASK_EW", f"{task_id} references missing {ew_id}", task_ref.get("path", "")))
        status = task.get("status", "")
        if status and status not in TASK_STATUSES:
            issues.append(issue("error", "TASK_STATUS", f"{task_id} has invalid status {status}", task_ref.get("path", "")))
        checkpoint = task.get("checkpoint", "")
        if checkpoint not in CHECKPOINTS:
            issues.append(issue("warn", "TASK_CHECKPOINT", f"{task_id} has unusual checkpoint {checkpoint}", task_ref.get("path", "")))
        if not task.get("assigned_to"):
            issues.append(issue("warn", "TASK_ASSIGNEE_MISSING", f"{task_id} has no assignee", task_ref.get("path", "")))
        if status not in {"Iceboxed", "Verified"} and not task.get("expected_output"):
            issues.append(issue("warn", "TASK_EXPECTED_OUTPUT_MISSING", f"{task_id} has no expected_output", task_ref.get("path", "")))
        for dep in task.get("dependencies", []) or []:
            if dep not in entities.get("tasks", {}):
                issues.append(issue("error", "REL_TASK_DEPENDENCY", f"{task_id} depends on missing {dep}", task_ref.get("path", "")))
    for section in ["initiatives", "projects", "ews"]:
        for entity_id, row in entities.get(section, {}).items():
            path = row.get("path", "")
            full = safe_repo_path(repo, path) if path else None
            if not full or not full.exists():
                continue
            frontmatter, body = parse_frontmatter(read_text(full))
            if frontmatter.get("id") != entity_id:
                issues.append(issue("error", "DOC_ID_MISMATCH", f"{path} frontmatter id should be {entity_id}", path))
            if not markdown_title(body, ""):
                issues.append(issue("warn", "DOC_TITLE_MISSING", f"{path} has no H1 title", path))
    try:
        read_json_subset(repo / "assets/assets.yaml", {"assets": {}})
    except ProjectOSError as exc:
        issues.append(issue("error", "ASSET_PARSE", str(exc), "assets/assets.yaml"))
    return issues


def cmd_validate(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    issues = validate_repo(repo)
    if args.json:
        print(json.dumps({"repo": str(repo), "issues": issues}, indent=2))
    else:
        if not issues:
            print("Validation passed.")
        for item in issues:
            location = f" [{item['path']}]" if item.get("path") else ""
            print(f"{item['level'].upper()} {item['code']}: {item['message']}{location}")
    return 1 if any(item["level"] == "error" for item in issues) else 0


def collect_docs(repo: Path, registry: dict) -> list[dict]:
    docs = []
    for section in ["initiatives", "projects", "ews"]:
        for entity_id, row in registry.get("entities", {}).get(section, {}).items():
            path = row.get("path", "")
            full = safe_repo_path(repo, path)
            text = read_text(full)
            frontmatter, body = parse_frontmatter(text)
            docs.append(
                {
                    "id": entity_id,
                    "type": frontmatter.get("type", section.rstrip("s")),
                    "title": markdown_title(body, row.get("name", entity_id)),
                    "path": path,
                    "owner": row.get("owner", ""),
                    "status": row.get("status", ""),
                }
            )
    return docs


def collect_tasks(repo: Path, registry: dict) -> list[dict]:
    tasks = []
    projects = registry.get("entities", {}).get("projects", {})
    ews = registry.get("entities", {}).get("ews", {})
    for task_id, task_ref in registry.get("entities", {}).get("tasks", {}).items():
        path = task_ref.get("path", "")
        try:
            task = read_json_subset(safe_repo_path(repo, path), {})
        except ProjectOSError:
            task = {"id": task_id, "title": task_ref.get("title", ""), "status": "Invalid"}
        ew = ews.get(task.get("ew_id") or task_ref.get("ew_id"), {})
        project = projects.get(task.get("project_id") or task_ref.get("project_id") or ew.get("project_id", ""), {})
        merged = {**task_ref, **task}
        merged["id"] = task_id
        merged["path"] = path
        merged["ew_name"] = ew.get("name", "")
        merged["project_name"] = project.get("name", "")
        tasks.append(merged)
    return tasks


def compile_data(repo: Path) -> dict:
    registry = load_registry(repo)
    entities = registry.get("entities", {})
    issues = validate_repo(repo)
    return {
        "schema_version": registry.get("schema_version", 1),
        "repo_name": registry.get("name", repo.name),
        "repo_path": str(repo),
        "provider": registry.get("provider", ""),
        "github_repo": registry.get("github", {}).get("repo", ""),
        "gitlab_url": registry.get("gitlab", {}).get("url", ""),
        "gitlab_project": registry.get("gitlab", {}).get("project_path", ""),
        "git_commit": git_commit(repo),
        "generated_at": now_iso(),
        "projects": [{"id": key, **value} for key, value in entities.get("projects", {}).items()],
        "ews": [{"id": key, **value} for key, value in entities.get("ews", {}).items()],
        "tasks": collect_tasks(repo, registry),
        "docs": collect_docs(repo, registry),
        "people": registry.get("people", []),
        "events": read_jsonl(repo / "events/task-events.jsonl"),
        "reviews": read_jsonl(repo / "reviews/task-reviews.jsonl"),
        "validation": {"issues": issues},
    }


def cmd_compile(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    data = compile_data(repo)
    output = repo / ".project-os/site-data/project-os.json"
    write_text(output, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if args.json:
        print(json.dumps({"output": str(output), "issues": data["validation"]["issues"]}, indent=2))
    else:
        print(f"Wrote {output}")
        print(f"Validation issues: {len(data['validation']['issues'])}")
    return 1 if any(item["level"] == "error" for item in data["validation"]["issues"]) else 0


def first_initiative(registry: dict) -> str:
    initiatives = registry.get("entities", {}).get("initiatives", {})
    if not initiatives:
        raise ProjectOSError("no initiative exists")
    return sorted(initiatives.keys(), key=lambda item: int(re.sub(r"\D", "", item) or 0))[0]


def cmd_create_project(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    project_id = allocate_id(registry, "project")
    initiative_id = args.initiative_id or first_initiative(registry)
    path = f"projects/{project_id}/project.md"
    registry["entities"]["projects"][project_id] = {
        "initiative_id": initiative_id,
        "name": args.name,
        "path": path,
        "owner": args.owner,
        "status": args.status,
        "repos": [],
    }
    write_text(
        repo / path,
        markdown_doc(
            {"id": project_id, "type": "project", "initiative_id": initiative_id, "owner": args.owner, "status": args.status},
            f"{project_id} - {args.name}",
            "## Summary\n\nDescribe the project.\n\n## Goals\n\n- TBD\n\n## Change Log\n\n- Created project.\n",
        ),
    )
    save_registry(repo, registry)
    print(f"Created {project_id} at {path}")
    return 0


def cmd_create_ew(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    projects = registry.get("entities", {}).get("projects", {})
    if args.project_id not in projects:
        raise ProjectOSError(f"missing project {args.project_id}")
    ew_id = allocate_id(registry, "ew")
    project = projects[args.project_id]
    path = f"projects/{args.project_id}/ews/{ew_id}.md"
    registry["entities"]["ews"][ew_id] = {
        "project_id": args.project_id,
        "initiative_id": project.get("initiative_id", ""),
        "name": args.name,
        "path": path,
        "owner": args.owner,
        "status": args.status,
    }
    write_text(
        repo / path,
        markdown_doc(
            {
                "id": ew_id,
                "type": "ew",
                "project_id": args.project_id,
                "initiative_id": project.get("initiative_id", ""),
                "owner": args.owner,
                "status": args.status,
            },
            f"{ew_id} - {args.name}",
            "## Summary\n\nDescribe the workstream or experiment.\n\n## Acceptance Criteria\n\n- TBD\n\n## Linked Tasks\n\n- TBD\n",
        ),
    )
    save_registry(repo, registry)
    print(f"Created {ew_id} at {path}")
    return 0


def create_task_payload(registry: dict, ew_id: str, title: str, assigned_to: str, role: str, expected_output: str) -> tuple[str, str, dict]:
    ews = registry.get("entities", {}).get("ews", {})
    if ew_id not in ews:
        raise ProjectOSError(f"missing EW {ew_id}")
    task_id = allocate_id(registry, "task")
    project_id = ews[ew_id]["project_id"]
    path = f"projects/{project_id}/tasks/{task_id}.yaml"
    task = {
        "id": task_id,
        "ew_id": ew_id,
        "project_id": project_id,
        "title": title,
        "assigned_to": assigned_to,
        "role": role or "",
        "status": "Backlog",
        "checkpoint": "Drafting",
        "deadline": "",
        "expected_output": expected_output,
        "acceptance_criteria": [],
        "dependencies": [],
        "target_repo": "",
        "output": "",
        "ai_update": "",
        "user_update": "",
    }
    registry["entities"]["tasks"][task_id] = {
        "ew_id": ew_id,
        "project_id": project_id,
        "path": path,
        "title": title,
        "assigned_to": assigned_to,
        "status": "Backlog",
        "expected_output": expected_output,
    }
    return task_id, path, task


def cmd_create_task(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    task_id, path, task = create_task_payload(registry, args.ew_id, args.title, args.assigned_to, args.role, args.expected_output)
    write_text(repo / path, dump_yaml_json(task))
    save_registry(repo, registry)
    print(f"Created {task_id} at {path}")
    return 0


def proposal_actions(repo: Path, payload: dict) -> tuple[str, str, list[dict]]:
    change_type = payload.get("type")
    title = payload.get("title") or payload.get("message") or change_type or "Project OS change"
    message = payload.get("message") or title
    actions = []
    if change_type == "edit_file":
        path = payload.get("path", "").replace("\\", "/").lstrip("/")
        if not path:
            raise ProjectOSError("edit_file requires path")
        safe_repo_path(repo, path)
        action = "update" if (repo / path).exists() else "create"
        actions.append({"action": action, "file_path": path, "content": payload.get("content", "")})
    elif change_type == "create_task":
        registry = load_registry(repo)
        task_id, path, task = create_task_payload(
            registry,
            payload.get("ew_id", ""),
            payload.get("title", ""),
            payload.get("assigned_to", ""),
            payload.get("role", ""),
            payload.get("expected_output", ""),
        )
        actions.append({"action": "update", "file_path": "registry.yaml", "content": dump_yaml_json(registry)})
        actions.append({"action": "create", "file_path": path, "content": dump_yaml_json(task)})
        title = f"Create {task_id}: {payload.get('title', '')}"
        message = title
    elif change_type == "task_event":
        registry = load_registry(repo)
        event_id = allocate_id(registry, "event")
        event = {
            "event_id": event_id,
            "task_id": payload.get("task_id", ""),
            "actor": payload.get("actor", ""),
            "event_type": payload.get("event_type", "update"),
            "message": payload.get("message", ""),
            "created_at": now_iso(),
        }
        current = read_text(repo / "events/task-events.jsonl")
        actions.append({"action": "update", "file_path": "registry.yaml", "content": dump_yaml_json(registry)})
        actions.append({"action": "update", "file_path": "events/task-events.jsonl", "content": current + json.dumps(event, ensure_ascii=False) + "\n"})
        title = f"{event['task_id']} {event['event_type']}"
        message = title
    else:
        raise ProjectOSError(f"unknown proposal type: {change_type}")
    return title, message, actions


def local_proposal(repo: Path, title: str, message: str, actions: list[dict]) -> dict:
    proposal_id = f"{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{slugify(title)[:40]}"
    proposal_dir = repo / ".project-os/proposals" / proposal_id
    proposal_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        proposal_dir / "proposal.json",
        json.dumps({"title": title, "message": message, "actions": actions, "created_at": now_iso()}, indent=2, ensure_ascii=False) + "\n",
    )
    for index, action in enumerate(actions, start=1):
        file_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", action["file_path"])
        write_text(proposal_dir / f"{index:02d}-{action['action']}-{file_name}", action["content"])
    return {"mode": "dry-run", "proposal_dir": str(proposal_dir), "title": title, "actions": len(actions)}


def gitlab_request(gitlab_url: str, token: str, method: str, endpoint: str, body: dict | None = None) -> dict:
    url = gitlab_url.rstrip("/") + endpoint
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProjectOSError(f"GitLab API {method} {endpoint} failed: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise ProjectOSError(f"GitLab API connection failed: {exc}") from exc


def gitlab_create_mr(repo: Path, args: argparse.Namespace, title: str, message: str, actions: list[dict]) -> dict:
    registry = load_registry(repo)
    gitlab_url = args.gitlab_url or os.environ.get("PROJECT_OS_GITLAB_URL") or registry.get("gitlab", {}).get("url", "")
    project_path = args.gitlab_project or os.environ.get("PROJECT_OS_GITLAB_PROJECT") or registry.get("gitlab", {}).get("project_path", "")
    token = args.gitlab_token or os.environ.get("PROJECT_OS_GITLAB_TOKEN") or ""
    if not gitlab_url or not project_path or not token:
        raise ProjectOSError("GitLab MR mode requires gitlab_url, gitlab_project, and PROJECT_OS_GITLAB_TOKEN")
    encoded_project = parse.quote(project_path, safe="")
    target_branch = args.target_branch or registry.get("gitlab", {}).get("default_branch", "main")
    source_branch = f"project-os/{slugify(title)[:48]}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
    commit_body = {
        "branch": source_branch,
        "start_branch": target_branch,
        "commit_message": message,
        "actions": actions,
    }
    commit = gitlab_request(gitlab_url, token, "POST", f"/api/v4/projects/{encoded_project}/repository/commits", commit_body)
    mr_body = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": "Created by GitLab Project OS website/controller.",
        "remove_source_branch": True,
    }
    mr = gitlab_request(gitlab_url, token, "POST", f"/api/v4/projects/{encoded_project}/merge_requests", mr_body)
    return {"mode": "gitlab", "branch": source_branch, "commit": commit.get("id", ""), "merge_request": mr.get("web_url", "")}


def github_request(api_url: str, token: str, method: str, endpoint: str, body: dict | None = None) -> dict:
    url = api_url.rstrip("/") + endpoint
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "git-based-project-management",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProjectOSError(f"GitHub API {method} {endpoint} failed: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise ProjectOSError(f"GitHub API connection failed: {exc}") from exc


def github_create_pr(repo: Path, args: argparse.Namespace, title: str, message: str, actions: list[dict]) -> dict:
    registry = load_registry(repo)
    api_url = args.github_api_url or os.environ.get("PROJECT_OS_GITHUB_API_URL") or registry.get("github", {}).get("api_url", "https://api.github.com")
    repo_name = args.github_repo or os.environ.get("PROJECT_OS_GITHUB_REPO") or registry.get("github", {}).get("repo", "")
    token = args.github_token or os.environ.get("PROJECT_OS_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not api_url or not repo_name or not token:
        raise ProjectOSError("GitHub PR mode requires github_api_url, github_repo, and PROJECT_OS_GITHUB_TOKEN")
    target_branch = args.target_branch or registry.get("github", {}).get("default_branch", "main")
    source_branch = f"project-os/{slugify(title)[:48]}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
    encoded_repo = "/".join(parse.quote(part, safe="") for part in repo_name.split("/"))
    base_ref = github_request(api_url, token, "GET", f"/repos/{encoded_repo}/git/ref/heads/{parse.quote(target_branch, safe='')}")
    base_sha = base_ref["object"]["sha"]
    github_request(
        api_url,
        token,
        "POST",
        f"/repos/{encoded_repo}/git/refs",
        {"ref": f"refs/heads/{source_branch}", "sha": base_sha},
    )
    for action in actions:
        file_path = action["file_path"]
        endpoint = f"/repos/{encoded_repo}/contents/{parse.quote(file_path, safe='/')}"
        sha = None
        if action.get("action") == "update":
            try:
                existing = github_request(api_url, token, "GET", endpoint + f"?ref={parse.quote(source_branch, safe='')}")
                sha = existing.get("sha")
            except ProjectOSError:
                sha = None
        import base64

        body = {
            "message": message,
            "content": base64.b64encode(action["content"].encode("utf-8")).decode("ascii"),
            "branch": source_branch,
        }
        if sha:
            body["sha"] = sha
        github_request(api_url, token, "PUT", endpoint, body)
    pr = github_request(
        api_url,
        token,
        "POST",
        f"/repos/{encoded_repo}/pulls",
        {"title": title, "head": source_branch, "base": target_branch, "body": "Created by Git-Based Project Management website/controller."},
    )
    return {"mode": "github", "branch": source_branch, "pull_request": pr.get("html_url", "")}


def handle_proposal(repo: Path, payload: dict, args: argparse.Namespace) -> dict:
    title, message, actions = proposal_actions(repo, payload)
    provider = (getattr(args, "provider", "") or os.environ.get("PROJECT_OS_PROVIDER") or "").lower()
    if getattr(args, "github", False) or provider == "github":
        return github_create_pr(repo, args, title, message, actions)
    if getattr(args, "gitlab", False) or provider == "gitlab":
        return gitlab_create_mr(repo, args, title, message, actions)
    return local_proposal(repo, title, message, actions)


def cmd_propose(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    payload = json.loads(read_text(Path(args.change_file)))
    result = handle_proposal(repo, payload, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


class ProjectOSHandler(BaseHTTPRequestHandler):
    repo: Path = Path(".")
    args: argparse.Namespace

    def send_json(self, body: dict, status: int = 200) -> None:
        encoded = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_json({"ok": True, "repo": str(self.repo)})
            return
        if parsed.path == "/api/data":
            try:
                self.send_json(compile_data(self.repo))
            except Exception as exc:  # noqa: BLE001 - API should report errors as JSON.
                self.send_json({"error": str(exc)}, status=500)
            return
        path = parsed.path
        if path == "/":
            path = "/static/index.html"
        if not path.startswith("/static/"):
            self.send_error(404)
            return
        rel = path.removeprefix("/static/").lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        parsed = parse.urlparse(self.path)
        if parsed.path != "/api/proposals":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        try:
            self.send_json(handle_proposal(self.repo, payload, self.args))
        except Exception as exc:  # noqa: BLE001 - website should show proposal errors.
            self.send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def cmd_website(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    handler = type("BoundProjectOSHandler", (ProjectOSHandler,), {"repo": repo, "args": args})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Project OS website at http://{args.host}:{args.port}/")
    print(f"Repo: {repo}")
    provider = (args.provider or os.environ.get("PROJECT_OS_PROVIDER") or "").lower()
    live = args.github or args.gitlab or provider in {"github", "gitlab"}
    print(f"Mode: {provider or 'live'} PR/MR" if live else "Mode: dry-run proposals")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping website.")
    finally:
        server.server_close()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = []
    git_result = shutil.which("git")
    checks.append({"check": "git", "ok": bool(git_result), "detail": git_result or "missing"})
    repo = repo_arg(args.repo)
    checks.append({"check": "repo_path", "ok": repo.exists(), "detail": str(repo)})
    checks.append({"check": "registry", "ok": registry_path(repo).exists(), "detail": str(registry_path(repo))})
    provider = args.provider or os.environ.get("PROJECT_OS_PROVIDER", "github")
    github_repo = args.github_repo or os.environ.get("PROJECT_OS_GITHUB_REPO", "")
    github_token = args.github_token or os.environ.get("PROJECT_OS_GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    github_api_url = args.github_api_url or os.environ.get("PROJECT_OS_GITHUB_API_URL", "https://api.github.com")
    gitlab_url = args.gitlab_url or os.environ.get("PROJECT_OS_GITLAB_URL", "https://gitlab.garena.com")
    gitlab_project = args.gitlab_project or os.environ.get("PROJECT_OS_GITLAB_PROJECT", "")
    token = args.gitlab_token or os.environ.get("PROJECT_OS_GITLAB_TOKEN", "")
    checks.append({"check": "provider", "ok": provider in {"github", "gitlab"}, "detail": provider})
    checks.append({"check": "github_repo", "ok": bool(github_repo), "detail": github_repo or "missing"})
    checks.append({"check": "github_token", "ok": bool(github_token), "detail": "provided" if github_token else "missing"})
    checks.append({"check": "gitlab_url", "ok": bool(gitlab_url), "detail": gitlab_url})
    checks.append({"check": "gitlab_project", "ok": bool(gitlab_project), "detail": gitlab_project or "missing"})
    checks.append({"check": "gitlab_token", "ok": bool(token), "detail": "provided" if token else "missing"})
    if args.live and token:
        try:
            user = gitlab_request(gitlab_url, token, "GET", "/api/v4/user")
            checks.append({"check": "gitlab_api_user", "ok": True, "detail": user.get("username", "ok")})
        except ProjectOSError as exc:
            checks.append({"check": "gitlab_api_user", "ok": False, "detail": str(exc)})
    if args.live and github_token:
        try:
            user = github_request(github_api_url, github_token, "GET", "/user")
            checks.append({"check": "github_api_user", "ok": True, "detail": user.get("login", "ok")})
        except ProjectOSError as exc:
            checks.append({"check": "github_api_user", "ok": False, "detail": str(exc)})
    if args.interactive:
        print("Project OS interactive setup probe. Secrets are not saved by default.")
        provider = input(f"Provider [github/gitlab] [{provider}]: ").strip() or provider
        github_repo = input(f"GitHub repo [owner/repo] [{github_repo or 'owner/project-os'}]: ").strip() or github_repo
        gitlab_url = input(f"GitLab URL [{gitlab_url}]: ").strip() or gitlab_url
        gitlab_project = input(f"GitLab project path [{gitlab_project or 'group/project-os'}]: ").strip() or gitlab_project
        role = input("Role [owner/manager/assignee/reviewer/installer]: ").strip() or "installer"
        repo_input = input(f"Local repo path [{repo}]: ").strip()
        repo = Path(repo_input).resolve() if repo_input else repo
        token_hint = input("Do you have a provider token with repo/API write scope? [y/N]: ").strip().lower()
        local = {
            "provider": provider,
            "github_repo": github_repo,
            "gitlab_url": gitlab_url,
            "gitlab_project": gitlab_project,
            "role": role,
            "repo": str(repo),
            "token_expected_in_env": "PROJECT_OS_GITHUB_TOKEN or PROJECT_OS_GITLAB_TOKEN" if token_hint == "y" else "",
            "created_at": now_iso(),
        }
        write_text(repo / ".project-os/local.json", json.dumps(local, indent=2) + "\n")
        print(f"Wrote non-secret local setup hints to {repo / '.project-os/local.json'}")
        print("Set PROJECT_OS_GITHUB_TOKEN or PROJECT_OS_GITLAB_TOKEN in the environment before live PR/MR creation.")
    if args.json:
        print(json.dumps({"checks": checks}, indent=2))
    else:
        for row in checks:
            marker = "OK" if row["ok"] else "MISSING"
            print(f"{marker} {row['check']}: {row['detail']}")
    return 0 if all(row["ok"] for row in checks if row["check"] in {"git", "repo_path"}) else 1


def cmd_init_gitlab(args: argparse.Namespace) -> int:
    token = args.gitlab_token or os.environ.get("PROJECT_OS_GITLAB_TOKEN", "")
    if not token:
        raise ProjectOSError("init-gitlab requires PROJECT_OS_GITLAB_TOKEN or --gitlab-token")
    body = {
        "name": args.name,
        "path": args.path,
        "visibility": args.visibility,
    }
    if args.namespace_id:
        body["namespace_id"] = args.namespace_id
    if args.dry_run:
        print(json.dumps({"dry_run": True, "request": body}, indent=2))
        return 0
    result = gitlab_request(args.gitlab_url, token, "POST", "/api/v4/projects", body)
    print(json.dumps(result, indent=2))
    return 0


def cmd_init_github(args: argparse.Namespace) -> int:
    body = {
        "name": args.name,
        "private": args.private,
        "description": args.description,
        "auto_init": False,
    }
    endpoint = f"/orgs/{parse.quote(args.org, safe='')}/repos" if args.org else "/user/repos"
    if args.dry_run:
        print(json.dumps({"dry_run": True, "endpoint": endpoint, "request": body}, indent=2))
        return 0
    token = args.github_token or os.environ.get("PROJECT_OS_GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    if not token:
        raise ProjectOSError("init-github requires PROJECT_OS_GITHUB_TOKEN, GH_TOKEN, or --github-token")
    result = github_request(args.github_api_url, token, "POST", endpoint, body)
    print(json.dumps(result, indent=2))
    return 0


def add_common_repo(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=os.environ.get("PROJECT_OS_REPO", "."), help="Project OS repository path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git-first Project OS controller")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="Probe local GitHub/GitLab setup")
    add_common_repo(p)
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--live", action="store_true", help="Call provider /user when token is provided")
    p.add_argument("--provider", default="")
    p.add_argument("--github-api-url", default="")
    p.add_argument("--github-repo", default="")
    p.add_argument("--github-token", default="")
    p.add_argument("--gitlab-url", default="")
    p.add_argument("--gitlab-project", default="")
    p.add_argument("--gitlab-token", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init", help="Initialize a Project OS repo")
    add_common_repo(p)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--provider", default=os.environ.get("PROJECT_OS_PROVIDER", "github"), choices=["github", "gitlab"])
    p.add_argument("--github-repo", default=os.environ.get("PROJECT_OS_GITHUB_REPO", ""))
    p.add_argument("--gitlab-url", default=os.environ.get("PROJECT_OS_GITLAB_URL", "https://gitlab.garena.com"))
    p.add_argument("--gitlab-project", default=os.environ.get("PROJECT_OS_GITLAB_PROJECT", ""))
    p.add_argument("--git-init", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="Validate registry, relationships, docs, tasks, and assets")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("compile", help="Compile website data from canonical files")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("website", help="Serve the Project OS website")
    add_common_repo(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--provider", default="")
    p.add_argument("--github", action="store_true", help="Create live GitHub PRs instead of dry-run proposals")
    p.add_argument("--github-api-url", default="")
    p.add_argument("--github-repo", default="")
    p.add_argument("--github-token", default="")
    p.add_argument("--gitlab", action="store_true", help="Create live GitLab MRs instead of dry-run proposals")
    p.add_argument("--gitlab-url", default="")
    p.add_argument("--gitlab-project", default="")
    p.add_argument("--gitlab-token", default="")
    p.add_argument("--target-branch", default="")
    p.set_defaults(func=cmd_website)

    p = sub.add_parser("create-project", help="Create a project spec directly in the current branch")
    add_common_repo(p)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--initiative-id", default="")
    p.add_argument("--status", default="Active")
    p.set_defaults(func=cmd_create_project)

    p = sub.add_parser("create-ew", help="Create an EW spec directly in the current branch")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--status", default="Planned")
    p.set_defaults(func=cmd_create_ew)

    p = sub.add_parser("create-task", help="Create a task spec directly in the current branch")
    add_common_repo(p)
    p.add_argument("--ew-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--assigned-to", required=True)
    p.add_argument("--role", default="")
    p.add_argument("--expected-output", required=True)
    p.set_defaults(func=cmd_create_task)

    p = sub.add_parser("propose", help="Create a dry-run proposal, GitHub PR, or GitLab MR from a JSON change file")
    add_common_repo(p)
    p.add_argument("--change-file", required=True)
    p.add_argument("--provider", default="")
    p.add_argument("--github", action="store_true")
    p.add_argument("--github-api-url", default="")
    p.add_argument("--github-repo", default="")
    p.add_argument("--github-token", default="")
    p.add_argument("--gitlab", action="store_true")
    p.add_argument("--gitlab-url", default="")
    p.add_argument("--gitlab-project", default="")
    p.add_argument("--gitlab-token", default="")
    p.add_argument("--target-branch", default="")
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("init-github", help="Create a GitHub repository through API")
    p.add_argument("--github-api-url", default=os.environ.get("PROJECT_OS_GITHUB_API_URL", "https://api.github.com"))
    p.add_argument("--github-token", default="")
    p.add_argument("--name", required=True)
    p.add_argument("--org", default="", help="Organization login; omit to create under authenticated user")
    p.add_argument("--description", default="Git-based project management skill and website.")
    p.add_argument("--private", action="store_true", default=True)
    p.add_argument("--public", dest="private", action="store_false")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init_github)

    p = sub.add_parser("init-gitlab", help="Create a GitLab project through API")
    p.add_argument("--gitlab-url", default=os.environ.get("PROJECT_OS_GITLAB_URL", "https://gitlab.garena.com"))
    p.add_argument("--gitlab-token", default="")
    p.add_argument("--name", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--namespace-id", default="")
    p.add_argument("--visibility", default="private", choices=["private", "internal", "public"])
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init_gitlab)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectOSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
