#!/usr/bin/env python3
"""Dependency-light controller for Git-based project management."""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
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
TASK_STATUSES = {"Backlog", "In Progress", "Blocked", "Done", "Verified", "Iceboxed"}
CHECKPOINTS = {"", "Drafting", "Ready", "Review", "Revising", "Blocked"}
PROJECT_STATUSES = {"Planning", "Active", "Paused", "Shipped", "Archived"}
DOC_TYPES = {
    "proposal",
    "brief",
    "game-design",
    "technical-spec",
    "playtest-plan",
    "playtest-report",
    "qa-report",
    "research-report",
    "asset-brief",
    "video-brief",
    "build-note",
    "release-plan",
    "postmortem",
    "decision",
    "meeting-notes",
}
ID_PREFIX = {
    "project": "PROJ",
    "task": "TASK",
    "doc": "DOC",
    "asset": "ASSET",
    "event": "EVENT",
    "review": "REVIEW",
}


class GitPMError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "project"


def repo_arg(value: str | None) -> Path:
    return Path(value or os.environ.get("GPM_REPO") or ".").resolve()


def safe_repo_path(repo: Path, rel: str) -> Path:
    clean = str(rel or "").replace("\\", "/").lstrip("/")
    candidate = (repo / clean).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError as exc:
        raise GitPMError(f"path escapes repo: {rel}") from exc
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
        raise GitPMError(f"{path} must use JSON-subset YAML: {exc}") from exc


def dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def registry_path(repo: Path) -> Path:
    return repo / "registry.yaml"


def load_registry(repo: Path) -> dict:
    return read_json_subset(registry_path(repo), {})


def save_registry(repo: Path, registry: dict) -> None:
    write_text(registry_path(repo), dump(registry))


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
        raise GitPMError(result.stderr.strip() or result.stdout.strip() or "git command failed")
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
    section = "docs" if kind == "doc" else f"{kind}s"
    existing = set(registry.get(section, {}).keys())
    next_ids = registry.setdefault("next_ids", {})
    number = int(next_ids.get(kind, 1))
    while f"{prefix}{number}" in existing:
        number += 1
    next_ids[kind] = number + 1
    return f"{prefix}{number}"


def project_folder(project_id: str, name: str) -> str:
    return f"{project_id}-{slugify(name)}"


def doc_folder(doc_type: str) -> str:
    if doc_type in {"proposal", "brief"}:
        return "proposals"
    if doc_type in {"game-design", "technical-spec"}:
        return "design"
    if doc_type in {"playtest-plan", "playtest-report", "qa-report", "research-report"}:
        return "reports"
    if doc_type in {"asset-brief", "video-brief", "build-note"}:
        return "production"
    if doc_type in {"release-plan", "postmortem"}:
        return "release"
    if doc_type in {"decision", "meeting-notes"}:
        return "notes"
    return "docs"


def make_project_record(project_id: str, name: str, owner: str, project_type: str, status: str) -> dict:
    folder = project_folder(project_id, name)
    return {
        "id": project_id,
        "slug": slugify(name),
        "name": name,
        "type": project_type,
        "status": status,
        "owners": [owner],
        "summary": "Describe the product, game, tool, or project outcome.",
        "path": f"projects/{folder}/project.yaml",
        "readme": f"projects/{folder}/README.md",
        "repos": [],
    }


def make_task(task_id: str, project_id: str, project_name: str, title: str, assigned_to: str, role: str, expected_output: str) -> tuple[str, dict, dict]:
    folder = project_folder(project_id, project_name)
    path = f"projects/{folder}/tasks/{task_id}.yaml"
    task = {
        "id": task_id,
        "project_id": project_id,
        "title": title,
        "assigned_to": assigned_to,
        "role": role or "",
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
    ref = {
        "project_id": project_id,
        "path": path,
        "title": title,
        "assigned_to": assigned_to,
        "status": "Backlog",
        "expected_output": expected_output,
    }
    return path, task, ref


def make_doc(doc_id: str, project: dict, doc_type: str, title: str, owner: str) -> tuple[str, str, dict]:
    folder = project_folder(project["id"], project["name"])
    rel = f"projects/{folder}/docs/{doc_folder(doc_type)}/{doc_id}-{slugify(title)}.md"
    text = markdown_doc(
        {
            "id": doc_id,
            "project_id": project["id"],
            "type": doc_type,
            "owner": owner,
            "status": "draft",
        },
        f"{doc_id} - {title}",
        """
## Purpose

State why this document exists and what decision or work it supports.

## Context

Link relevant tasks, repos, builds, references, videos, reports, or assets.

## Content

Write the proposal, design, report, or decision here.

## Open Questions

- TBD
""",
    )
    ref = {"project_id": project["id"], "doc_type": doc_type, "title": title, "owner": owner, "path": rel, "status": "draft"}
    return rel, text, ref


def ensure_base_registry(name: str, owner: str, provider: str, github_repo: str, gitlab_url: str, gitlab_project: str) -> dict:
    project = make_project_record("PROJ1", name, owner, "game", "Active")
    task_path, task, task_ref = make_task("TASK1", "PROJ1", name, "Confirm collaboration setup", owner, "PM", "Setup Confirmation")
    doc_path, _doc_text, doc_ref = make_doc("DOC1", project, "proposal", "Kickoff Proposal", owner)
    return {
        "schema_version": 2,
        "name": name,
        "provider": provider,
        "github": {"api_url": "https://api.github.com", "repo": github_repo, "default_branch": "main"},
        "gitlab": {"url": gitlab_url, "project_path": gitlab_project, "default_branch": "main"},
        "next_ids": {"project": 2, "task": 2, "doc": 2, "asset": 1, "event": 1, "review": 1},
        "people": [{"name": owner, "role": "Owner", "email": ""}],
        "projects": {"PROJ1": project},
        "tasks": {"TASK1": task_ref},
        "docs": {"DOC1": doc_ref},
        "assets": {},
        "_seed": {"task_path": task_path, "task": task, "doc_path": doc_path},
    }


def write_initial_files(repo: Path, registry: dict) -> None:
    seed = registry.pop("_seed")
    project = registry["projects"]["PROJ1"]
    folder = project_folder("PROJ1", project["name"])
    write_text(repo / ".gitignore", ".project-hub/local.json\n.project-hub/proposals/\n*.log\n__pycache__/\n")
    write_text(repo / "registry.yaml", dump(registry))
    write_text(
        repo / "README.md",
        f"""# {registry['name']}

This repository is the canonical project management workspace for the team.

Use it to track project state, tasks, proposals, design docs, playtest reports, QA reports, videos, game assets, decisions, and links to implementation repositories.

## Start Here

- `registry.yaml`: project, task, document, asset, and person index.
- `projects/`: one folder per managed project.
- `templates/`: document and task templates.
- `events/task-events.jsonl`: append-only collaboration updates.
- `reviews/task-reviews.jsonl`: append-only output reviews.

Agents and humans should make durable changes through pull requests or merge requests.
""",
    )
    write_text(repo / project["path"], dump(project))
    write_text(
        repo / project["readme"],
        markdown_doc(
            {"id": "PROJ1", "type": "project", "owner": project["owners"][0], "status": project["status"]},
            f"PROJ1 - {project['name']}",
            """
## State

- Status: Active
- Current focus: complete collaboration setup.
- Next review: TBD

## Repositories

Add implementation repositories in `project.yaml` so collaborators and agents know where source code, game builds, websites, services, or tooling live.

## Documents

- DOC1 - Kickoff Proposal

## Tasks

- TASK1 - Confirm collaboration setup
""",
        ),
    )
    write_text(repo / seed["task_path"], dump(seed["task"]))
    doc_rel, doc_text, _doc_ref = make_doc("DOC1", project, "proposal", "Kickoff Proposal", project["owners"][0])
    write_text(repo / doc_rel, doc_text)
    for rel, text in template_files().items():
        write_text(repo / rel, text)
    write_text(repo / f"projects/{folder}/assets/assets.yaml", dump({"assets": {}}))
    write_text(repo / "events/task-events.jsonl", "")
    write_text(repo / "reviews/task-reviews.jsonl", "")
    write_text(repo / "policies/output-requirements.yaml", dump(default_output_policy()))
    (repo / ".project-hub/site-data").mkdir(parents=True, exist_ok=True)


def template_files() -> dict[str, str]:
    return {
        "templates/proposal.md": "# Proposal\n\n## Problem\n\n## Proposed Direction\n\n## Risks\n\n## Decision Needed\n",
        "templates/game-design.md": "# Game Design\n\n## Player Fantasy\n\n## Core Loop\n\n## Systems\n\n## UX Notes\n\n## Tuning Questions\n",
        "templates/technical-spec.md": "# Technical Spec\n\n## Goal\n\n## Architecture\n\n## Interfaces\n\n## Test Plan\n\n## Rollout\n",
        "templates/playtest-report.md": "# Playtest Report\n\n## Build\n\n## Participants\n\n## Findings\n\n## Evidence\n\n## Recommended Changes\n",
        "templates/qa-report.md": "# QA Report\n\n## Build\n\n## Scope\n\n## Defects\n\n## Risks\n\n## Release Recommendation\n",
        "templates/asset-brief.md": "# Asset Brief\n\n## Purpose\n\n## References\n\n## Requirements\n\n## Format\n\n## Delivery\n",
        "templates/video-brief.md": "# Video Brief\n\n## Goal\n\n## Audience\n\n## Script/Beats\n\n## Assets Needed\n\n## Delivery Specs\n",
        "templates/task.yaml": dump(make_task("TASK#", "PROJ#", "project", "Task title", "Owner", "Role", "Expected Output")[1]),
    }


def default_output_policy() -> dict:
    return {
        "schema_version": 2,
        "common": {"requires_output_link": True, "requires_accessible_source": True},
        "output_types": {
            "Setup Confirmation": {"matches": ["Setup Confirmation"], "manual_checks": ["Repository validates", "Website loads locally"]},
            "Proposal": {"matches": ["Proposal", "Pitch"], "manual_checks": ["Problem is clear", "Decision needed is explicit"]},
            "Game Design": {"matches": ["Game Design", "Design Doc"], "manual_checks": ["Player-facing behavior is clear", "Open tuning questions are listed"]},
            "Technical Spec": {"matches": ["Technical Spec", "Architecture Doc"], "manual_checks": ["Interfaces and test plan are clear"]},
            "Playtest Report": {"matches": ["Playtest Report"], "manual_checks": ["Build and participants are stated", "Findings include evidence"]},
            "QA Report": {"matches": ["QA Report"], "manual_checks": ["Defects are reproducible", "Release risk is stated"]},
            "Asset": {"matches": ["Asset", "Game Asset", "Art Asset"], "manual_checks": ["Format and usage are clear"]},
            "Video": {"matches": ["Video", "Trailer", "Gameplay Capture"], "manual_checks": ["Source or final video is linked"]},
            "Pull Request": {"matches": ["Pull Request", "Merge Request", "Implementation PR", "Implementation MR"], "manual_checks": ["PR/MR links to task", "Verification notes are present"]},
        },
    }


def cmd_init(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    repo.mkdir(parents=True, exist_ok=True)
    if registry_path(repo).exists() and not args.force:
        raise GitPMError(f"{registry_path(repo)} already exists; pass --force to overwrite generated seed files")
    registry = ensure_base_registry(args.name, args.owner, args.provider, args.github_repo, args.gitlab_url, args.gitlab_project)
    write_initial_files(repo, registry)
    if args.git_init and not (repo / ".git").exists():
        git(["init", "-b", "main"], repo, check=True)
        git(["add", "."], repo, check=True)
        git(["commit", "-m", "Initialize project management workspace"], repo, check=False)
    print(f"Initialized project management repo at {repo}")
    print("Next: run validate, compile, then website.")
    return 0


def issue(level: str, code: str, message: str, path: str = "") -> dict:
    return {"level": level, "code": code, "message": message, "path": path}


def max_suffix(ids: list[str], prefix: str) -> int:
    values = []
    for item in ids:
        match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", item)
        if match:
            values.append(int(match.group(1)))
    return max(values) if values else 0


def validate_repo(repo: Path) -> list[dict]:
    issues: list[dict] = []
    if not registry_path(repo).exists():
        return [issue("error", "REGISTRY_MISSING", "registry.yaml is missing", "registry.yaml")]
    try:
        registry = load_registry(repo)
    except GitPMError as exc:
        return [issue("error", "REGISTRY_PARSE", str(exc), "registry.yaml")]
    for section in ["projects", "tasks", "docs", "people", "next_ids"]:
        if section not in registry:
            issues.append(issue("error", "REGISTRY_SECTION", f"{section} must exist", "registry.yaml"))
    for kind, section in [("project", "projects"), ("task", "tasks"), ("doc", "docs")]:
        prefix = ID_PREFIX[kind]
        records = registry.get(section, {})
        for entity_id, row in records.items():
            if not re.fullmatch(rf"{prefix}\d+", entity_id):
                issues.append(issue("error", "ID_FORMAT", f"{entity_id} should match {prefix}#", "registry.yaml"))
            rel = row.get("path") or row.get("readme")
            if rel and not safe_repo_path(repo, rel).exists():
                issues.append(issue("error", "PATH_MISSING", f"{entity_id} path does not exist", rel))
        expected = max_suffix(list(records.keys()), prefix) + 1
        if int(registry.get("next_ids", {}).get(kind, 1)) < expected:
            issues.append(issue("error", "NEXT_ID_STALE", f"next_ids.{kind} should be at least {expected}", "registry.yaml"))
    for project_id, project in registry.get("projects", {}).items():
        if project.get("status") not in PROJECT_STATUSES:
            issues.append(issue("warn", "PROJECT_STATUS", f"{project_id} status is unusual: {project.get('status')}", project.get("path", "")))
        if not project.get("owners"):
            issues.append(issue("warn", "PROJECT_OWNER_MISSING", f"{project_id} has no owners", project.get("path", "")))
        for repo_link in project.get("repos", []):
            if not repo_link.get("url"):
                issues.append(issue("warn", "PROJECT_REPO_URL_MISSING", f"{project_id} has repo link without url", project.get("path", "")))
    for doc_id, doc in registry.get("docs", {}).items():
        if doc.get("project_id") not in registry.get("projects", {}):
            issues.append(issue("error", "REL_DOC_PROJECT", f"{doc_id} references missing project {doc.get('project_id')}", doc.get("path", "")))
        if doc.get("doc_type") not in DOC_TYPES:
            issues.append(issue("warn", "DOC_TYPE", f"{doc_id} has unusual doc_type {doc.get('doc_type')}", doc.get("path", "")))
        full = safe_repo_path(repo, doc.get("path", ""))
        if full.exists():
            frontmatter, body = parse_frontmatter(read_text(full))
            if frontmatter.get("id") != doc_id:
                issues.append(issue("error", "DOC_ID_MISMATCH", f"{doc.get('path')} frontmatter id should be {doc_id}", doc.get("path", "")))
            if not markdown_title(body, ""):
                issues.append(issue("warn", "DOC_TITLE_MISSING", f"{doc.get('path')} has no H1 title", doc.get("path", "")))
    for task_id, task_ref in registry.get("tasks", {}).items():
        path = task_ref.get("path", "")
        try:
            task = read_json_subset(safe_repo_path(repo, path), {})
        except GitPMError as exc:
            issues.append(issue("error", "TASK_PARSE", str(exc), path))
            continue
        if task.get("id") != task_id:
            issues.append(issue("error", "TASK_ID_MISMATCH", f"{path} id is {task.get('id')}, expected {task_id}", path))
        if task.get("project_id") not in registry.get("projects", {}):
            issues.append(issue("error", "REL_TASK_PROJECT", f"{task_id} references missing project {task.get('project_id')}", path))
        if task.get("status") not in TASK_STATUSES:
            issues.append(issue("error", "TASK_STATUS", f"{task_id} has invalid status {task.get('status')}", path))
        if task.get("checkpoint", "") not in CHECKPOINTS:
            issues.append(issue("warn", "TASK_CHECKPOINT", f"{task_id} has unusual checkpoint {task.get('checkpoint')}", path))
        if not task.get("assigned_to"):
            issues.append(issue("warn", "TASK_ASSIGNEE_MISSING", f"{task_id} has no assignee", path))
        if task.get("status") not in {"Iceboxed", "Verified"} and not task.get("expected_output"):
            issues.append(issue("warn", "TASK_EXPECTED_OUTPUT_MISSING", f"{task_id} has no expected_output", path))
        for dep in task.get("dependencies", []) or []:
            if dep not in registry.get("tasks", {}):
                issues.append(issue("error", "REL_TASK_DEPENDENCY", f"{task_id} depends on missing {dep}", path))
    for rel in ["policies/output-requirements.yaml"]:
        if not safe_repo_path(repo, rel).exists():
            issues.append(issue("warn", "POLICY_MISSING", f"{rel} is missing", rel))
    return issues


def cmd_validate(args: argparse.Namespace) -> int:
    issues = validate_repo(repo_arg(args.repo))
    if args.json:
        print(json.dumps({"issues": issues}, indent=2))
    else:
        if not issues:
            print("Validation passed.")
        for item in issues:
            location = f" [{item['path']}]" if item.get("path") else ""
            print(f"{item['level'].upper()} {item['code']}: {item['message']}{location}")
    return 1 if any(item["level"] == "error" for item in issues) else 0


def collect_docs(repo: Path, registry: dict) -> list[dict]:
    docs = []
    for doc_id, row in registry.get("docs", {}).items():
        text = read_text(safe_repo_path(repo, row.get("path", "")))
        frontmatter, body = parse_frontmatter(text)
        docs.append(
            {
                "id": doc_id,
                "project_id": row.get("project_id", ""),
                "type": row.get("doc_type") or frontmatter.get("type", ""),
                "title": markdown_title(body, row.get("title", doc_id)),
                "path": row.get("path", ""),
                "owner": row.get("owner", ""),
                "status": row.get("status", ""),
            }
        )
    return docs


def collect_tasks(repo: Path, registry: dict) -> list[dict]:
    tasks = []
    for task_id, ref in registry.get("tasks", {}).items():
        try:
            task = read_json_subset(safe_repo_path(repo, ref.get("path", "")), {})
        except GitPMError:
            task = {"id": task_id, "title": ref.get("title", ""), "status": "Invalid"}
        project = registry.get("projects", {}).get(task.get("project_id") or ref.get("project_id", ""), {})
        merged = {**ref, **task}
        merged["id"] = task_id
        merged["path"] = ref.get("path", "")
        merged["project_name"] = project.get("name", "")
        tasks.append(merged)
    return tasks


def compile_data(repo: Path) -> dict:
    registry = load_registry(repo)
    issues = validate_repo(repo)
    return {
        "schema_version": registry.get("schema_version", 2),
        "repo_name": registry.get("name", repo.name),
        "repo_path": str(repo),
        "provider": registry.get("provider", ""),
        "github_repo": registry.get("github", {}).get("repo", ""),
        "gitlab_url": registry.get("gitlab", {}).get("url", ""),
        "gitlab_project": registry.get("gitlab", {}).get("project_path", ""),
        "git_commit": git_commit(repo),
        "generated_at": now_iso(),
        "projects": [{"id": key, **value} for key, value in registry.get("projects", {}).items()],
        "docs": collect_docs(repo, registry),
        "tasks": collect_tasks(repo, registry),
        "people": registry.get("people", []),
        "events": read_jsonl(repo / "events/task-events.jsonl"),
        "reviews": read_jsonl(repo / "reviews/task-reviews.jsonl"),
        "validation": {"issues": issues},
    }


def cmd_compile(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    data = compile_data(repo)
    output = repo / ".project-hub/site-data/project-hub.json"
    write_text(output, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "issues": data["validation"]["issues"]}, indent=2) if args.json else f"Wrote {output}")
    return 1 if any(item["level"] == "error" for item in data["validation"]["issues"]) else 0


def cmd_create_project(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    project_id = allocate_id(registry, "project")
    project = make_project_record(project_id, args.name, args.owner, args.type, args.status)
    registry.setdefault("projects", {})[project_id] = project
    write_text(repo / project["path"], dump(project))
    write_text(repo / project["readme"], markdown_doc({"id": project_id, "type": "project", "owner": args.owner, "status": args.status}, f"{project_id} - {args.name}", "## State\n\nNew project.\n\n## Documents\n\n## Tasks\n"))
    write_text(repo / f"projects/{project_folder(project_id, args.name)}/assets/assets.yaml", dump({"assets": {}}))
    save_registry(repo, registry)
    print(f"Created {project_id} at {project['readme']}")
    return 0


def create_task_payload(registry: dict, project_id: str, title: str, assigned_to: str, role: str, expected_output: str) -> tuple[str, str, dict]:
    projects = registry.get("projects", {})
    if project_id not in projects:
        raise GitPMError(f"missing project {project_id}")
    task_id = allocate_id(registry, "task")
    path, task, ref = make_task(task_id, project_id, projects[project_id]["name"], title, assigned_to, role, expected_output)
    registry.setdefault("tasks", {})[task_id] = ref
    return task_id, path, task


def cmd_create_task(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    task_id, path, task = create_task_payload(registry, args.project_id, args.title, args.assigned_to, args.role, args.expected_output)
    write_text(repo / path, dump(task))
    save_registry(repo, registry)
    print(f"Created {task_id} at {path}")
    return 0


def cmd_create_doc(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    project = registry.get("projects", {}).get(args.project_id)
    if not project:
        raise GitPMError(f"missing project {args.project_id}")
    doc_id = allocate_id(registry, "doc")
    rel, text, ref = make_doc(doc_id, project, args.doc_type, args.title, args.owner)
    registry.setdefault("docs", {})[doc_id] = ref
    write_text(repo / rel, text)
    save_registry(repo, registry)
    print(f"Created {doc_id} at {rel}")
    return 0


def proposal_actions(repo: Path, payload: dict) -> tuple[str, str, list[dict]]:
    change_type = payload.get("type")
    title = payload.get("title") or payload.get("message") or change_type or "Project change"
    message = payload.get("message") or title
    if change_type == "edit_file":
        rel = payload.get("path", "").replace("\\", "/").lstrip("/")
        if not rel:
            raise GitPMError("edit_file requires path")
        safe_repo_path(repo, rel)
        action = "update" if (repo / rel).exists() else "create"
        return title, message, [{"action": action, "file_path": rel, "content": payload.get("content", "")}]
    if change_type == "create_task":
        registry = load_registry(repo)
        task_id, path, task = create_task_payload(
            registry,
            payload.get("project_id", ""),
            payload.get("title", ""),
            payload.get("assigned_to", ""),
            payload.get("role", ""),
            payload.get("expected_output", ""),
        )
        title = f"Create {task_id}: {payload.get('title', '')}"
        return title, title, [
            {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
            {"action": "create", "file_path": path, "content": dump(task)},
        ]
    if change_type == "create_doc":
        registry = load_registry(repo)
        project = registry.get("projects", {}).get(payload.get("project_id", ""))
        if not project:
            raise GitPMError(f"missing project {payload.get('project_id')}")
        doc_id = allocate_id(registry, "doc")
        rel, text, ref = make_doc(doc_id, project, payload.get("doc_type", "proposal"), payload.get("title", ""), payload.get("owner", ""))
        registry.setdefault("docs", {})[doc_id] = ref
        title = f"Create {doc_id}: {payload.get('title', '')}"
        return title, title, [
            {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
            {"action": "create", "file_path": rel, "content": text},
        ]
    raise GitPMError(f"unknown proposal type: {change_type}")


def local_proposal(repo: Path, title: str, message: str, actions: list[dict]) -> dict:
    proposal_id = f"{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{slugify(title)[:40]}"
    proposal_dir = repo / ".project-hub/proposals" / proposal_id
    proposal_dir.mkdir(parents=True, exist_ok=True)
    write_text(proposal_dir / "proposal.json", dump({"title": title, "message": message, "actions": actions, "created_at": now_iso()}))
    for index, action in enumerate(actions, start=1):
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", action["file_path"])
        if len(safe_name) > 90:
            digest = hashlib.sha1(action["file_path"].encode("utf-8")).hexdigest()[:10]
            suffix = Path(action["file_path"]).suffix[:12]
            safe_name = f"{safe_name[:70].rstrip('._-')}-{digest}{suffix}"
        write_text(proposal_dir / f"{index:02d}-{action['action']}-{safe_name}", action["content"])
    return {"mode": "dry-run", "proposal_dir": str(proposal_dir), "title": title, "actions": len(actions)}


def gitlab_request(gitlab_url: str, token: str, method: str, endpoint: str, body: dict | None = None) -> dict:
    req = request.Request(gitlab_url.rstrip("/") + endpoint, data=None if body is None else json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "PRIVATE-TOKEN": token}, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        raise GitPMError(f"GitLab API failed: {exc.code} {exc.read().decode('utf-8', errors='replace')}") from exc


def github_request(api_url: str, token: str, method: str, endpoint: str, body: dict | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "git-based-project-management", "X-GitHub-Api-Version": "2022-11-28", "Authorization": f"Bearer {token}"}
    req = request.Request(api_url.rstrip("/") + endpoint, data=None if body is None else json.dumps(body).encode("utf-8"), headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        raise GitPMError(f"GitHub API failed: {exc.code} {exc.read().decode('utf-8', errors='replace')}") from exc


def gitlab_create_mr(repo: Path, args: argparse.Namespace, title: str, message: str, actions: list[dict]) -> dict:
    registry = load_registry(repo)
    gitlab_url = args.gitlab_url or os.environ.get("GPM_GITLAB_URL") or registry.get("gitlab", {}).get("url", "")
    project_path = args.gitlab_project or os.environ.get("GPM_GITLAB_PROJECT") or registry.get("gitlab", {}).get("project_path", "")
    token = args.gitlab_token or os.environ.get("GPM_GITLAB_TOKEN") or ""
    if not gitlab_url or not project_path or not token:
        raise GitPMError("GitLab MR mode requires GitLab URL, project, and token")
    target = args.target_branch or registry.get("gitlab", {}).get("default_branch", "main")
    source = f"project-hub/{slugify(title)[:48]}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
    encoded = parse.quote(project_path, safe="")
    gitlab_request(gitlab_url, token, "POST", f"/api/v4/projects/{encoded}/repository/commits", {"branch": source, "start_branch": target, "commit_message": message, "actions": actions})
    mr = gitlab_request(gitlab_url, token, "POST", f"/api/v4/projects/{encoded}/merge_requests", {"source_branch": source, "target_branch": target, "title": title, "description": "Created by Git-Based Project Management.", "remove_source_branch": True})
    return {"mode": "gitlab", "branch": source, "merge_request": mr.get("web_url", "")}


def github_create_pr(repo: Path, args: argparse.Namespace, title: str, message: str, actions: list[dict]) -> dict:
    registry = load_registry(repo)
    api_url = args.github_api_url or os.environ.get("GPM_GITHUB_API_URL") or registry.get("github", {}).get("api_url", "https://api.github.com")
    repo_name = args.github_repo or os.environ.get("GPM_GITHUB_REPO") or registry.get("github", {}).get("repo", "")
    token = args.github_token or os.environ.get("GPM_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not api_url or not repo_name or not token:
        raise GitPMError("GitHub PR mode requires GitHub repo and token")
    target = args.target_branch or registry.get("github", {}).get("default_branch", "main")
    source = f"project-hub/{slugify(title)[:48]}-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
    encoded = "/".join(parse.quote(part, safe="") for part in repo_name.split("/"))
    ref = github_request(api_url, token, "GET", f"/repos/{encoded}/git/ref/heads/{parse.quote(target, safe='')}")
    github_request(api_url, token, "POST", f"/repos/{encoded}/git/refs", {"ref": f"refs/heads/{source}", "sha": ref["object"]["sha"]})
    for action in actions:
        endpoint = f"/repos/{encoded}/contents/{parse.quote(action['file_path'], safe='/')}"
        sha = None
        if action.get("action") == "update":
            try:
                existing = github_request(api_url, token, "GET", endpoint + f"?ref={parse.quote(source, safe='')}")
                sha = existing.get("sha")
            except GitPMError:
                sha = None
        body = {"message": message, "content": base64.b64encode(action["content"].encode("utf-8")).decode("ascii"), "branch": source}
        if sha:
            body["sha"] = sha
        github_request(api_url, token, "PUT", endpoint, body)
    pr = github_request(api_url, token, "POST", f"/repos/{encoded}/pulls", {"title": title, "head": source, "base": target, "body": "Created by Git-Based Project Management."})
    return {"mode": "github", "branch": source, "pull_request": pr.get("html_url", "")}


def handle_proposal(repo: Path, payload: dict, args: argparse.Namespace) -> dict:
    title, message, actions = proposal_actions(repo, payload)
    provider = (getattr(args, "provider", "") or os.environ.get("GPM_PROVIDER") or "").lower()
    live = (
        getattr(args, "github", False)
        or getattr(args, "gitlab", False)
        or getattr(args, "live", False)
        or str(os.environ.get("GPM_LIVE_PROPOSALS", "")).lower() in {"1", "true", "yes"}
    )
    if live and (getattr(args, "github", False) or provider == "github"):
        return github_create_pr(repo, args, title, message, actions)
    if live and (getattr(args, "gitlab", False) or provider == "gitlab"):
        return gitlab_create_mr(repo, args, title, message, actions)
    return local_proposal(repo, title, message, actions)


def cmd_propose(args: argparse.Namespace) -> int:
    result = handle_proposal(repo_arg(args.repo), json.loads(read_text(Path(args.change_file))), args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


class GitPMHandler(BaseHTTPRequestHandler):
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
            self.send_json({"ok": True, "repo": str(self.repo), "runtime": "python"})
            return
        if parsed.path == "/api/data":
            self.send_json(compile_data(self.repo))
            return
        path = "/static/index.html" if parsed.path == "/" else parsed.path
        if not path.startswith("/static/"):
            self.send_error(404)
            return
        target = (STATIC_DIR / path.removeprefix("/static/")).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.exists():
            self.send_error(404)
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if parse.urlparse(self.path).path != "/api/proposals":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        try:
            self.send_json(handle_proposal(self.repo, payload, self.args))
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def cmd_website(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    handler = type("BoundGitPMHandler", (GitPMHandler,), {"repo": repo, "args": args})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving website at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping website.")
    finally:
        server.server_close()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    provider = args.provider or os.environ.get("GPM_PROVIDER", "github")
    github_repo = args.github_repo or os.environ.get("GPM_GITHUB_REPO", "")
    gitlab_url = args.gitlab_url or os.environ.get("GPM_GITLAB_URL", "")
    github_token = args.github_token or os.environ.get("GPM_GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    gitlab_project = args.gitlab_project or os.environ.get("GPM_GITLAB_PROJECT", "")
    gitlab_token = args.gitlab_token or os.environ.get("GPM_GITLAB_TOKEN", "")
    if args.interactive:
        print("Setup probe. Secrets are not saved by default.")
        provider = input(f"Provider [github/gitlab] [{provider}]: ").strip() or provider
        if provider == "github":
            github_repo = input(f"GitHub repo [owner/repo] [{github_repo or 'owner/repo'}]: ").strip() or github_repo
        if provider == "gitlab":
            gitlab_url = input(f"GitLab URL [{gitlab_url or 'https://gitlab.garena.com'}]: ").strip() or gitlab_url
            gitlab_project = input(f"GitLab project [group/project] [{gitlab_project or 'group/project-hub'}]: ").strip() or gitlab_project
        role = input("Role [owner/manager/assignee/reviewer/installer]: ").strip() or "installer"
        repo_input = input(f"Local repo path [{repo}]: ").strip()
        repo = Path(repo_input).resolve() if repo_input else repo
        local = {"provider": provider, "github_repo": github_repo, "gitlab_url": gitlab_url, "gitlab_project": gitlab_project, "role": role, "repo": str(repo), "created_at": now_iso()}
        write_text(repo / ".project-hub/local.json", dump(local))
        print(f"Wrote non-secret local setup hints to {repo / '.project-hub/local.json'}")
    checks = [
        {"check": "git", "ok": bool(shutil.which("git")), "detail": shutil.which("git") or "missing"},
        {"check": "repo_path", "ok": repo.exists(), "detail": str(repo)},
        {"check": "registry", "ok": registry_path(repo).exists(), "detail": str(registry_path(repo))},
        {"check": "provider", "ok": provider in {"github", "gitlab"}, "detail": provider},
    ]
    if provider == "github":
        checks.extend(
            [
                {"check": "github_repo", "ok": bool(github_repo), "detail": github_repo or "missing"},
                {"check": "github_token", "ok": bool(github_token), "detail": "provided" if github_token else "missing"},
            ]
        )
    if provider == "gitlab":
        checks.extend(
            [
                {"check": "gitlab_url", "ok": bool(gitlab_url), "detail": gitlab_url or "missing"},
                {"check": "gitlab_project", "ok": bool(gitlab_project), "detail": gitlab_project or "missing"},
                {"check": "gitlab_token", "ok": bool(gitlab_token), "detail": "provided" if gitlab_token else "missing"},
            ]
        )
    print(json.dumps({"checks": checks}, indent=2) if args.json else "\n".join(f"{'OK' if row['ok'] else 'MISSING'} {row['check']}: {row['detail']}" for row in checks))
    return 0


def cmd_init_github(args: argparse.Namespace) -> int:
    body = {"name": args.name, "private": args.private, "description": args.description, "auto_init": False}
    endpoint = f"/orgs/{parse.quote(args.org, safe='')}/repos" if args.org else "/user/repos"
    if args.dry_run:
        print(json.dumps({"dry_run": True, "endpoint": endpoint, "request": body}, indent=2))
        return 0
    token = args.github_token or os.environ.get("GPM_GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    if not token:
        raise GitPMError("init-github requires GPM_GITHUB_TOKEN, GH_TOKEN, or --github-token")
    print(json.dumps(github_request(args.github_api_url, token, "POST", endpoint, body), indent=2))
    return 0


def cmd_init_gitlab(args: argparse.Namespace) -> int:
    body = {"name": args.name, "path": args.path, "visibility": args.visibility}
    if args.namespace_id:
        body["namespace_id"] = args.namespace_id
    if args.dry_run:
        print(json.dumps({"dry_run": True, "request": body}, indent=2))
        return 0
    token = args.gitlab_token or os.environ.get("GPM_GITLAB_TOKEN", "")
    if not token:
        raise GitPMError("init-gitlab requires GPM_GITLAB_TOKEN or --gitlab-token")
    print(json.dumps(gitlab_request(args.gitlab_url, token, "POST", "/api/v4/projects", body), indent=2))
    return 0


def add_common_repo(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=os.environ.get("GPM_REPO", "."), help="Project management repository path")


def add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default="")
    parser.add_argument("--live", action="store_true", help="Create a live PR/MR instead of a local dry-run proposal")
    parser.add_argument("--github", action="store_true")
    parser.add_argument("--github-api-url", default="")
    parser.add_argument("--github-repo", default="")
    parser.add_argument("--github-token", default="")
    parser.add_argument("--gitlab", action="store_true")
    parser.add_argument("--gitlab-url", default="")
    parser.add_argument("--gitlab-project", default="")
    parser.add_argument("--gitlab-token", default="")
    parser.add_argument("--target-branch", default="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git-based project management controller")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor")
    add_common_repo(p)
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--json", action="store_true")
    add_provider_args(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init")
    add_common_repo(p)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--provider", default=os.environ.get("GPM_PROVIDER", "github"), choices=["github", "gitlab"])
    p.add_argument("--github-repo", default=os.environ.get("GPM_GITHUB_REPO", ""))
    p.add_argument("--gitlab-url", default=os.environ.get("GPM_GITLAB_URL", ""))
    p.add_argument("--gitlab-project", default=os.environ.get("GPM_GITLAB_PROJECT", ""))
    p.add_argument("--git-init", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("compile")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("website")
    add_common_repo(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    add_provider_args(p)
    p.set_defaults(func=cmd_website)

    p = sub.add_parser("create-project")
    add_common_repo(p)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--type", default="game")
    p.add_argument("--status", default="Planning")
    p.set_defaults(func=cmd_create_project)

    p = sub.add_parser("create-task")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--assigned-to", required=True)
    p.add_argument("--role", default="")
    p.add_argument("--expected-output", required=True)
    p.set_defaults(func=cmd_create_task)

    p = sub.add_parser("create-doc")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--doc-type", default="proposal")
    p.set_defaults(func=cmd_create_doc)

    p = sub.add_parser("propose")
    add_common_repo(p)
    p.add_argument("--change-file", required=True)
    add_provider_args(p)
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("init-github")
    p.add_argument("--github-api-url", default=os.environ.get("GPM_GITHUB_API_URL", "https://api.github.com"))
    p.add_argument("--github-token", default="")
    p.add_argument("--name", required=True)
    p.add_argument("--org", default="")
    p.add_argument("--description", default="Git-based project management skill and website.")
    p.add_argument("--private", action="store_true", default=True)
    p.add_argument("--public", dest="private", action="store_false")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init_github)

    p = sub.add_parser("init-gitlab")
    p.add_argument("--gitlab-url", default=os.environ.get("GPM_GITLAB_URL", ""))
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
    except GitPMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
