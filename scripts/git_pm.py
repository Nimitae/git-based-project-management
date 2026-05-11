#!/usr/bin/env python3
"""Dependency-light controller for Git-based project management."""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import fnmatch
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
TASK_STATUSES = {"Backlog", "In Progress", "Blocked", "In Review", "Done", "Verified", "Iceboxed"}
CHECKPOINTS = {"", "Drafting", "Ready", "Review", "Revising", "Blocked", "Accepted"}
PROJECT_STATUSES = {"Planning", "Active", "Paused", "Shipped", "Archived"}
MILESTONE_STATUSES = {"Planned", "Active", "At Risk", "Done", "Archived"}
REVIEW_DECISIONS = {"approved", "changes_requested", "rejected", "verification_failed", "cancelled"}
ATTEMPT_EVENT_TYPES = {
    "submitted_output",
    "output_attempted",
    "verification_failed",
    "output_withdrawn",
    "output_superseded",
    "review_cancelled",
}
DOC_TYPES = {
    "proposal",
    "brief",
    "feature-proposal",
    "feature-brief",
    "game-design",
    "technical-spec",
    "frontend-spec",
    "backend-spec",
    "telemetry-spec",
    "api-contract",
    "playtest-plan",
    "playtest-session",
    "playtest-report",
    "qa-report",
    "qa-bug-report",
    "research-report",
    "asset-brief",
    "3d-asset-brief",
    "art-handoff",
    "3d-model-handoff",
    "video-brief",
    "mockup-review",
    "build-note",
    "release-plan",
    "postmortem",
    "decision",
    "meeting-notes",
    "project-note",
    "weekly-update",
    "risk-log",
    "retro-notes",
}
DOC_STATUSES = {"draft", "live", "review", "final", "archived", "historical"}
LIVE_DOC_STATUSES = {"draft", "live", "review"}
HISTORICAL_DOC_STATUSES = {"final", "archived", "historical"}
HISTORICAL_TASK_STATUSES = {"Done", "Verified", "Iceboxed"}
DOC_SECTION_REQUIREMENTS = {
    "proposal": ["Problem", "Proposed Direction", "Risks", "Decision Needed"],
    "brief": ["Goal", "Audience", "Scope", "Success Criteria"],
    "feature-proposal": ["Problem", "Player/User Value", "Proposed Scope", "Non-Goals", "Risks", "Task Breakdown", "Decision Needed"],
    "feature-brief": ["Player/User Value", "Scope", "Dependencies", "Success Metrics"],
    "game-design": ["Player Fantasy", "Core Loop", "Systems", "UX Notes", "Tuning Questions"],
    "technical-spec": ["Goal", "Architecture", "Interfaces", "Test Plan", "Rollout"],
    "frontend-spec": ["User Flow", "State", "Components", "API Contract", "Test Plan"],
    "backend-spec": ["Goal", "Data Model", "API", "Operations", "Test Plan"],
    "telemetry-spec": ["Events", "Properties", "Consumers", "Privacy", "Validation"],
    "api-contract": ["Endpoints", "Auth", "Errors", "Compatibility", "Tests"],
    "playtest-plan": ["Build", "Participants", "Test Goals", "Tasks", "Capture Plan"],
    "playtest-session": ["Session", "Participants", "Script", "Observations", "Captures"],
    "playtest-report": ["Build", "Participants", "Findings", "Evidence", "Recommended Changes"],
    "qa-report": ["Build", "Scope", "Defects", "Risks", "Release Recommendation"],
    "qa-bug-report": ["Build", "Reproduction", "Expected", "Actual", "Evidence"],
    "research-report": ["Question", "Method", "Findings", "Recommendation"],
    "asset-brief": ["Purpose", "References", "Requirements", "Format", "Delivery"],
    "3d-asset-brief": ["Purpose", "References", "Model Requirements", "Texture Requirements", "Delivery"],
    "art-handoff": ["Source Files", "Export Format", "Style References", "Acceptance", "Integration Notes"],
    "3d-model-handoff": ["Scale", "Geometry", "Materials", "LODs", "Collision", "Export"],
    "video-brief": ["Goal", "Audience", "Script/Beats", "Assets Needed", "Delivery Specs"],
    "mockup-review": ["Context", "Mockups", "Feedback", "Decision", "Follow-up Tasks"],
    "build-note": ["Build", "Changes", "Known Issues", "Verification"],
    "release-plan": ["Scope", "Risks", "Checklist", "Rollback"],
    "postmortem": ["Outcome", "What Worked", "What Did Not", "Actions"],
    "decision": ["Context", "Decision", "Options Considered", "Consequences"],
    "meeting-notes": ["Attendees", "Discussion", "Decisions", "Actions"],
    "project-note": ["Context", "Note", "Links", "Follow-up"],
    "weekly-update": ["Highlights", "Progress", "Risks", "Next Week"],
    "risk-log": ["Risk", "Impact", "Mitigation", "Owner"],
    "retro-notes": ["What Worked", "What Did Not", "Actions", "Owners"],
}
ID_PREFIX = {
    "project": "PROJ",
    "task": "TASK",
    "doc": "DOC",
    "asset": "ASSET",
    "event": "EVENT",
    "review": "REVIEW",
    "milestone": "MILESTONE",
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
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


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


def file_sha256(path: Path) -> str:
    if not path.exists() or path.is_dir():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    clean = (text or "").lstrip("\ufeff")
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", clean)
    if not match:
        return {}, clean
    raw = match.group(1).strip()
    body = clean[match.end() :].lstrip("\r\n")
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


def clean_markdown_line(line: str) -> str:
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line or "")
    clean = re.sub(r"`([^`]*)`", r"\1", clean)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"^\s*[-*+]\s+", "", clean)
    clean = re.sub(r"^\s*\d+\.\s+", "", clean)
    clean = clean.replace("*", "").replace("_", "").replace("~", "")
    clean = re.sub(r"\s*\|\s*", " / ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def markdown_preview(text: str, title: str) -> str:
    lines: list[str] = []
    in_fence = False
    for raw_line in (text or "").splitlines():
        trimmed = raw_line.strip()
        if trimmed.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not trimmed or trimmed.startswith("#"):
            continue
        if re.fullmatch(r"[\s|:-]+", trimmed):
            continue
        clean = clean_markdown_line(trimmed)
        if not clean or clean.lower() == (title or "").lower():
            continue
        lines.append(clean)
        if len(" ".join(lines)) >= 360:
            break
    return " ".join(lines)[:360]


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
    if doc_type in {"proposal", "brief", "feature-proposal"}:
        return "proposals"
    if doc_type in {"game-design", "feature-brief"}:
        return "design"
    if doc_type in {"technical-spec", "frontend-spec", "backend-spec", "telemetry-spec", "api-contract"}:
        return "engineering"
    if doc_type in {"playtest-plan", "playtest-session", "playtest-report", "qa-report", "qa-bug-report", "research-report"}:
        return "reports"
    if doc_type in {"asset-brief", "3d-asset-brief", "art-handoff", "3d-model-handoff", "video-brief", "mockup-review", "build-note"}:
        return "production"
    if doc_type in {"release-plan", "postmortem"}:
        return "release"
    if doc_type == "decision":
        return "decisions"
    if doc_type in {"meeting-notes", "project-note", "weekly-update", "risk-log", "retro-notes"}:
        return "notes"
    return "docs"


def doc_body_template(doc_type: str) -> str:
    sections = DOC_SECTION_REQUIREMENTS.get(doc_type, ["Purpose", "Context", "Content", "Open Questions"])
    details = {
        "proposal": {
            "Problem": "What problem or opportunity should the team act on?",
            "Proposed Direction": "What should change, and what alternatives were considered?",
            "Risks": "List product, technical, schedule, art, or dependency risks.",
            "Decision Needed": "State the specific approval or decision needed.",
        },
        "feature-proposal": {
            "Problem": "What user, player, product, or operational problem should this feature solve?",
            "Player/User Value": "State the intended outcome and why this should be prioritized now.",
            "Proposed Scope": "List included behavior, systems, screens, assets, services, and docs.",
            "Non-Goals": "List tempting work that is intentionally out of scope.",
            "Risks": "List product, technical, design, art, schedule, data, or dependency risks.",
            "Task Breakdown": "List proposed tasks, owners, expected outputs, and linked repos if known.",
            "Decision Needed": "State approve/reject/defer criteria and who decides.",
        },
        "feature-brief": {
            "Player/User Value": "State the user outcome and why it matters now.",
            "Scope": "List included and excluded behavior.",
            "Dependencies": "Link prerequisite docs, repos, assets, APIs, or tasks.",
            "Success Metrics": "Define measurable quality, product, or delivery signals.",
        },
        "game-design": {
            "Player Fantasy": "Describe the intended player experience.",
            "Core Loop": "Describe the repeated actions, rewards, and failure states.",
            "Systems": "List mechanics, rules, tuning variables, and dependencies.",
            "UX Notes": "Call out controls, HUD, onboarding, feedback, and accessibility.",
            "Tuning Questions": "List open balance questions for implementation or playtest.",
        },
        "frontend-spec": {
            "User Flow": "Describe screen flow, states, and edge cases.",
            "State": "List client state, persistence, loading, and error handling.",
            "Components": "List UI components, props, and ownership.",
            "API Contract": "Link backend endpoints, mocks, or fixtures.",
            "Test Plan": "List unit, integration, visual, and browser checks.",
        },
        "backend-spec": {
            "Goal": "Describe service behavior and user impact.",
            "Data Model": "List entities, migrations, retention, and ownership.",
            "API": "Document endpoints, events, auth, errors, and rate limits.",
            "Operations": "List observability, rollout, backfill, and failure handling.",
            "Test Plan": "List automated and manual verification.",
        },
        "telemetry-spec": {
            "Events": "List events and when each fires.",
            "Properties": "List names, types, allowed values, and ownership.",
            "Consumers": "State dashboards, analysts, experiments, or game systems using the data.",
            "Privacy": "Call out PII, retention, consent, and regional constraints.",
            "Validation": "Describe test events, QA steps, and rollout checks.",
        },
        "api-contract": {
            "Endpoints": "List routes, methods, payloads, and response shapes.",
            "Auth": "State auth requirements and permissions.",
            "Errors": "List error codes, retry rules, and client handling.",
            "Compatibility": "Document versioning, migration, and rollout behavior.",
            "Tests": "List contract, integration, load, and failure tests.",
        },
        "playtest-session": {
            "Session": "Record date, build, facilitator, and environment.",
            "Participants": "Summarize participant count and relevant profile.",
            "Script": "List tasks, prompts, and timing.",
            "Observations": "Capture durable findings and surprises.",
            "Captures": "Link recordings, clips, screenshots, notes, or surveys.",
        },
        "playtest-report": {
            "Build": "Link the build, branch, platform, and capture folder.",
            "Participants": "Summarize participant profile and session count.",
            "Findings": "Group findings by severity and player impact.",
            "Evidence": "Link clips, screenshots, notes, telemetry, or survey data.",
            "Recommended Changes": "Create or link follow-up tasks.",
        },
        "qa-bug-report": {
            "Build": "State build, branch, platform, account, and environment.",
            "Reproduction": "Write exact steps and frequency.",
            "Expected": "Describe expected behavior.",
            "Actual": "Describe actual behavior and impact.",
            "Evidence": "Link screenshot, video, log, crash dump, or telemetry.",
        },
        "mockup-review": {
            "Context": "State the feature, screen, user goal, and constraints.",
            "Mockups": "Link images, Figma frames, video captures, or prototypes.",
            "Feedback": "Record design, art, engineering, and PM feedback.",
            "Decision": "State approved direction or requested revision.",
            "Follow-up Tasks": "Link generated tasks or owners.",
        },
        "art-handoff": {
            "Source Files": "Link source art, license notes, and ownership.",
            "Export Format": "State required format, dimensions, naming, and variants.",
            "Style References": "Link approved references and art direction notes.",
            "Acceptance": "Define review checks for readability, style, and integration.",
            "Integration Notes": "Call out engine/import rules and dependencies.",
        },
        "3d-model-handoff": {
            "Scale": "State units, pivots, orientation, and gameplay scale.",
            "Geometry": "List polycount, topology, naming, and hierarchy expectations.",
            "Materials": "List texture sets, shader assumptions, and compression.",
            "LODs": "Define LOD count, thresholds, and budgets.",
            "Collision": "Describe collision proxies and navigation constraints.",
            "Export": "State GLB/FBX/Blend packaging and validation checks.",
        },
        "meeting-notes": {
            "Attendees": "List attendees and roles.",
            "Discussion": "Capture durable discussion points, not a transcript.",
            "Decisions": "List decisions or link decision records.",
            "Actions": "List action items with owners and task IDs.",
        },
        "project-note": {
            "Context": "State why the note matters and which project area it affects.",
            "Note": "Write the durable project note.",
            "Links": "Link related docs, tasks, assets, meetings, or repos.",
            "Follow-up": "List follow-up tasks or owners.",
        },
        "weekly-update": {
            "Highlights": "Summarize important progress and outcomes.",
            "Progress": "List shipped, reviewed, and in-progress work.",
            "Risks": "List blockers, schedule risk, quality risk, or dependency risk.",
            "Next Week": "State focus areas and expected outputs.",
        },
        "risk-log": {
            "Risk": "Describe the risk clearly.",
            "Impact": "Explain project impact if it happens.",
            "Mitigation": "State mitigation or contingency.",
            "Owner": "Name the owner and review date.",
        },
        "retro-notes": {
            "What Worked": "List practices or decisions to keep.",
            "What Did Not": "List problems without blame.",
            "Actions": "List concrete changes.",
            "Owners": "Assign owners and target dates.",
        },
    }
    lines = []
    for section in sections:
        lines.append(f"## {section}\n")
        lines.append(details.get(doc_type, {}).get(section, "TBD"))
        lines.append("")
    return "\n".join(lines).strip()


def markdown_h2_sections(body: str) -> set[str]:
    sections = set()
    for line in body.splitlines():
        if line.startswith("## "):
            sections.add(line[3:].strip())
    return sections


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
        "roadmap": f"projects/{folder}/planning/roadmap.yaml",
        "repos": [],
        "milestones": [],
    }


def make_task(task_id: str, project_id: str, project_name: str, title: str, assigned_to: str, role: str, expected_output: str) -> tuple[str, dict, dict]:
    folder = project_folder(project_id, project_name)
    task_folder = f"projects/{folder}/tasks/{task_id}"
    path = f"{task_folder}/task.yaml"
    task = {
        "id": task_id,
        "project_id": project_id,
        "title": title,
        "assigned_to": assigned_to,
        "role": role or "",
        "status": "Backlog",
        "checkpoint": "Drafting",
        "priority": "Medium",
        "deadline": "",
        "milestone": "",
        "feature_area": "",
        "release_target": "",
        "estimate": "",
        "risk": "",
        "reviewer": "",
        "expected_output": expected_output,
        "acceptance_criteria": ["Repository validates", "Website loads locally"],
        "dependencies": [],
        "target_repo": "",
        "output": "",
        "output_commit": "",
        "blocker": "",
        "ai_update": "",
        "user_update": "",
        "artifacts": {
            "notes": f"{task_folder}/notes.md",
            "outputs": f"{task_folder}/outputs.md",
            "attachments": f"{task_folder}/attachments/",
        },
    }
    ref = {
        "project_id": project_id,
        "path": path,
        "folder": task_folder,
        "title": title,
        "assigned_to": assigned_to,
        "status": "Backlog",
        "milestone": "",
        "feature_area": "",
        "expected_output": expected_output,
        "target_repo": "",
        "output_commit": "",
    }
    return path, task, ref


def make_milestone(milestone_id: str, project_id: str, project_name: str, title: str, owner: str, status: str = "Planned") -> tuple[str, dict, dict]:
    folder = project_folder(project_id, project_name)
    path = f"projects/{folder}/planning/milestones/{milestone_id}.yaml"
    milestone = {
        "id": milestone_id,
        "project_id": project_id,
        "title": title,
        "owner": owner,
        "status": status,
        "start": "",
        "target": "",
        "goals": [],
        "scope": [],
        "exit_criteria": [],
        "risks": [],
        "linked_tasks": [],
        "linked_docs": [],
    }
    ref = {"project_id": project_id, "path": path, "title": title, "owner": owner, "status": status}
    return path, milestone, ref


def task_support_files(task_path: str, task: dict) -> dict[str, str]:
    folder = str(Path(task_path).parent).replace("\\", "/")
    task_id = task.get("id", "TASK#")
    title = task.get("title", "Task")
    return {
        f"{folder}/notes.md": f"# {task_id} Notes - {title}\n\n## Context\n\nLink relevant docs, decisions, assets, repos, and prior discussion.\n\n## Working Notes\n\nUse this for task-local notes that should travel with the task.\n",
        f"{folder}/outputs.md": f"# {task_id} Outputs - {title}\n\n## Submitted Output\n\nLink the PR/MR, build, asset, report, document, capture, or release package.\n\n## Verification Notes\n\nRecord objective checks and reviewer observations.\n",
        f"{folder}/attachments/README.md": f"# {task_id} Attachments\n\nStore only small task-local references here. Large files should use Git LFS, releases/packages, object storage, or implementation repos, then be registered in the asset manifest.\n",
    }


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
        doc_body_template(doc_type),
    )
    ref = {"project_id": project["id"], "doc_type": doc_type, "title": title, "owner": owner, "path": rel, "status": "draft"}
    return rel, text, ref


def make_feature_proposal_doc(doc_id: str, project: dict, payload: dict) -> tuple[str, str, dict]:
    title = payload.get("title", "")
    owner = payload.get("owner", "")
    folder = project_folder(project["id"], project["name"])
    rel = f"projects/{folder}/docs/proposals/{doc_id}-{slugify(title)}.md"
    body = f"""
## Problem

{payload.get("problem") or "TBD"}

## Player/User Value

{payload.get("value") or "TBD"}

## Proposed Scope

{payload.get("scope") or "TBD"}

## Non-Goals

{payload.get("non_goals") or "TBD"}

## Risks

{payload.get("risks") or "TBD"}

## Task Breakdown

{payload.get("task_breakdown") or "TBD"}

## Decision Needed

{payload.get("decision_needed") or "Approve, reject, or defer this feature proposal."}
"""
    text = markdown_doc(
        {
            "id": doc_id,
            "project_id": project["id"],
            "type": "feature-proposal",
            "owner": owner,
            "status": "review",
        },
        f"{doc_id} - {title}",
        body,
    )
    ref = {"project_id": project["id"], "doc_type": "feature-proposal", "title": title, "owner": owner, "path": rel, "status": "review"}
    return rel, text, ref


def ensure_base_registry(name: str, owner: str, provider: str, github_repo: str, gitlab_url: str, gitlab_project: str) -> dict:
    project = make_project_record("PROJ1", name, owner, "game", "Active")
    task_path, task, task_ref = make_task("TASK1", "PROJ1", name, "Confirm collaboration setup", owner, "PM", "Setup Confirmation")
    doc_path, _doc_text, doc_ref = make_doc("DOC1", project, "proposal", "Kickoff Proposal", owner)
    owner_email = email_from_actor(owner)
    return {
        "schema_version": 2,
        "name": name,
        "provider": provider,
        "github": {"api_url": "https://api.github.com", "repo": github_repo, "default_branch": "main"},
        "gitlab": {"url": gitlab_url, "project_path": gitlab_project, "default_branch": "main"},
        "next_ids": {"project": 2, "task": 2, "doc": 2, "asset": 1, "event": 1, "review": 1, "milestone": 1},
        "people": [{"name": owner, "role": "Owner", "email": owner_email}],
        "projects": {"PROJ1": project},
        "milestones": {},
        "tasks": {"TASK1": task_ref},
        "docs": {"DOC1": doc_ref},
        "assets": {},
        "_seed": {"task_path": task_path, "task": task, "doc_path": doc_path},
    }


def default_roadmap(project: dict) -> dict:
    return {
        "project_id": project["id"],
        "horizon": "Now / Next / Later",
        "now": ["Complete collaboration setup."],
        "next": [],
        "later": [],
        "milestones": [],
        "review_cadence": "Weekly",
        "last_reviewed": "",
    }


def project_readme_body(project: dict) -> str:
    return f"""
## State

- Status: {project['status']}
- Current focus: complete collaboration setup.
- Next review: TBD
- Top blockers: None recorded.

## Roadmap

- Roadmap file: `{project.get('roadmap', '')}`
- Current milestone: TBD
- Release target: TBD

## Repositories

Add implementation repositories in `project.yaml` so collaborators and agents know where source code, game builds, websites, services, or tooling live.

## Documents

- DOC1 - Kickoff Proposal

## Tasks

- TASK1 - Confirm collaboration setup

## Assets

- Asset manifest: `assets/assets.yaml`

## Open Decisions

- None recorded.

## Risks

- None recorded.

## Operating Notes

- Cadence: weekly planning/review unless the team changes it.
- Durable changes should go through PRs/MRs.
- Daily execution updates should use task events, attempt records, or task-local notes.
"""


def start_here_for_agents_doc() -> str:
    return """# Start Here For Agents

This repository is the source of truth for project intent, task state, documents, reviews, attempts, decisions, and links to implementation repos.

## Before Any Work

1. Pull latest Git state.
2. Run or inspect `git_pm.py project-status --repo .`.
3. Read `registry.yaml`, project `README.md`, roadmap, active milestones, relevant task folders, events, reviews, and linked live docs.
4. Inspect implementation repos only after the management repo identifies the relevant repo or task.
5. Propose durable changes through PRs/MRs or website proposals.

## Common User Requests

If a user asks what they need to do today:

- Run `git_pm.py my-tasks --repo . --user "<name>"`.
- Read the listed task folders and linked docs.
- Report active work, blockers, review items, and next actions.

If an owner proposes a new feature:

- Run `git_pm.py propose-feature --repo . --project-id PROJ# --title "<feature>" --owner "<name>"`.
- Fill the feature proposal with problem, value, scope, non-goals, risks, task breakdown, and decision needed.
- Create follow-up tasks only after the proposal is accepted or explicitly approved.

If a manager asks for project health:

- Run `git_pm.py project-status --repo . --project-id PROJ#`.
- Run `git_pm.py blocked-tasks --repo .`, `git_pm.py review-queue --repo .`, and `git_pm.py stale-work --repo .`.
- Summarize blockers, stale review, failed verification, missing outputs, doc drift, and decision needs.

If a reviewer asks what needs review:

- Run `git_pm.py review-queue --repo .`.
- For each item, verify objective output access before approving.
- For code output, resolve `target_repo` through the project `repos` list and confirm `output_commit` exists in that implementation repo.
- Use `record-verification-failed`, `review-task --decision changes_requested`, or `review-task --decision approved`.

## Rules

- Do not use Git Issues for task state.
- Do not mutate generated website data as source of truth.
- Do not rewrite completed tasks, finalized docs, append-only events, or reviews.
- Do not mark work `Done` or `Verified` without output, acceptance criteria, and approved review.
"""


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
- `policies/wiki-guidelines.md`: required wiki shapes and task/asset linking rules.
- `policies/review-gates.yaml`: rules for Done/Verified task states.

Agents and humans should make durable changes through pull requests or merge requests.

Task state, events, reviews, and output attempts live in Git files. This workflow does not use Git Issues for task tracking.
""",
    )
    write_text(repo / "START_HERE_FOR_AGENTS.md", start_here_for_agents_doc())
    write_text(repo / project["path"], dump(project))
    write_text(
        repo / project["readme"],
        markdown_doc(
            {"id": "PROJ1", "type": "project", "owner": project["owners"][0], "status": project["status"]},
            f"PROJ1 - {project['name']}",
            project_readme_body(project),
        ),
    )
    write_text(repo / project["roadmap"], dump(default_roadmap(project)))
    write_text(repo / seed["task_path"], dump(seed["task"]))
    for rel, text in task_support_files(seed["task_path"], seed["task"]).items():
        write_text(repo / rel, text)
    doc_rel, doc_text, _doc_ref = make_doc("DOC1", project, "proposal", "Kickoff Proposal", project["owners"][0])
    write_text(repo / doc_rel, doc_text)
    for rel, text in template_files().items():
        write_text(repo / rel, text)
    write_text(repo / f"projects/{folder}/assets/assets.yaml", dump({"assets": {}}))
    write_text(repo / "events/task-events.jsonl", "")
    write_text(repo / "reviews/task-reviews.jsonl", "")
    write_text(repo / "policies/output-requirements.yaml", dump(default_output_policy()))
    write_text(repo / "policies/definition-of-ready.yaml", dump(default_definition_of_ready_policy()))
    write_text(repo / "policies/definition-of-done.yaml", dump(default_definition_of_done_policy()))
    write_text(repo / "policies/review-gates.yaml", dump(default_review_gates_policy()))
    write_text(repo / "policies/role-permissions.yaml", dump(default_role_permissions_policy()))
    write_text(repo / "policies/storage-policy.yaml", dump(default_storage_policy()))
    write_text(repo / "policies/branch-protection.md", branch_protection_doc())
    write_text(repo / "policies/agent-operating-rules.md", agent_operating_rules_doc())
    write_text(repo / "policies/wiki-guidelines.md", wiki_guidelines_doc())
    write_text(repo / "policies/terminology.yaml", dump(default_terminology_policy()))
    (repo / ".project-hub/site-data").mkdir(parents=True, exist_ok=True)


def template_files() -> dict[str, str]:
    files = {f"templates/{doc_type}.md": f"# {doc_type.replace('-', ' ').title()}\n\n{doc_body_template(doc_type)}\n" for doc_type in sorted(DOC_TYPES)}
    task_path, task, _task_ref = make_task("TASK#", "PROJ#", "project", "Task title", "Owner", "Role", "Expected Output")
    files["templates/task.yaml"] = dump(task)
    files["templates/task-folder/task.yaml"] = dump(task)
    for rel, text in task_support_files(task_path, task).items():
        files["templates/task-folder/" + rel.split("/tasks/TASK#/", 1)[-1]] = text
    files["templates/project-readme.md"] = markdown_doc({"id": "PROJ#", "type": "project", "owner": "Owner", "status": "Active"}, "PROJ# - Project Name", project_readme_body(make_project_record("PROJ#", "Project Name", "Owner", "game", "Active")))
    files["templates/roadmap.yaml"] = dump(default_roadmap(make_project_record("PROJ#", "Project Name", "Owner", "game", "Active")))
    files["templates/milestone.yaml"] = dump(make_milestone("MILESTONE#", "PROJ#", "Project Name", "Milestone title", "Owner")[1])
    files["templates/policies/definition-of-ready.yaml"] = dump(default_definition_of_ready_policy())
    files["templates/policies/definition-of-done.yaml"] = dump(default_definition_of_done_policy())
    files["templates/policies/review-gates.yaml"] = dump(default_review_gates_policy())
    files["templates/policies/role-permissions.yaml"] = dump(default_role_permissions_policy())
    files["templates/policies/storage-policy.yaml"] = dump(default_storage_policy())
    files["templates/asset.yaml"] = dump({"title": "Asset title", "type": "mockup", "storage": "external-link", "path": "", "source_url": "", "used_by": ["PROJ#"], "owner": "Owner"})
    files["templates/start-here-for-agents.md"] = start_here_for_agents_doc()
    files["templates/verification-failed.md"] = "# Verification Failed\n\n## Attempt\n\n- Task: `TASK#`\n- Output: \n- Reviewer: \n\n## Objective Check That Failed\n\nDescribe the exact check, command, asset access, build, contract, or evidence that could not be verified.\n\n## Expected Next Step\n\nKeep the task out of `Done`/`Verified`. Record `record-verification-failed`, then revise, supersede, withdraw, or cancel the review.\n"
    files["templates/output-withdrawn.md"] = "# Output Withdrawn\n\n## Attempt\n\n- Task: `TASK#`\n- Previous output: \n- Actor: \n\n## Reason\n\nExplain why the output is no longer current, no longer needed, or cannot be reviewed.\n\n## Follow-up\n\nState whether the task returns to `In Progress`, gets superseded by a new output, or is replaced by another task.\n"
    files["templates/review-cancelled.md"] = "# Review Cancelled\n\n## Review\n\n- Task: `TASK#`\n- Reviewer/actor: \n- Output under review: \n\n## Reason\n\nExplain why review stopped before an approval or changes-requested decision.\n\n## Follow-up\n\nState who owns the next action and whether the output should be withdrawn, superseded, or resubmitted.\n"
    files["templates/team-cadence.md"] = "# Team Cadence\n\n## Daily\n\n- Pull latest project hub state.\n- Review assigned task folders and project docs.\n- Record status, blockers, attempts, and handoffs with controller commands or the website.\n\n## Weekly\n\n- Review roadmap, milestones, review queue, blockers, validation issues, and terminology drift.\n- Update live docs and master files through PRs/MRs.\n\n## Release / Milestone\n\n- Run validation, document audit, website compile, and output review gates before marking work `Done` or `Verified`.\n"
    return files


def default_output_policy() -> dict:
    return {
        "schema_version": 2,
        "common": {"requires_output_link": True, "requires_accessible_source": True},
        "output_types": {
            "Setup Confirmation": {"matches": ["Setup Confirmation"], "manual_checks": ["Repository validates", "Website loads locally"]},
            "Proposal": {"matches": ["Proposal", "Pitch"], "manual_checks": ["Problem is clear", "Decision needed is explicit"]},
            "Feature Proposal": {"matches": ["Feature Proposal"], "manual_checks": ["Value is clear", "Scope and non-goals are explicit", "Task breakdown is proposed"]},
            "Game Design": {"matches": ["Game Design", "Design Doc"], "manual_checks": ["Player-facing behavior is clear", "Open tuning questions are listed"]},
            "Technical Spec": {"matches": ["Technical Spec", "Architecture Doc"], "manual_checks": ["Interfaces and test plan are clear"]},
            "Playtest Report": {"matches": ["Playtest Report"], "manual_checks": ["Build and participants are stated", "Findings include evidence"]},
            "QA Report": {"matches": ["QA Report"], "manual_checks": ["Defects are reproducible", "Release risk is stated"]},
            "Asset": {"matches": ["Asset", "Game Asset", "Art Asset"], "manual_checks": ["Format and usage are clear"]},
            "Video": {"matches": ["Video", "Trailer", "Gameplay Capture"], "manual_checks": ["Source or final video is linked"]},
            "Pull Request": {"matches": ["Pull Request", "Merge Request", "Implementation PR", "Implementation MR"], "manual_checks": ["PR/MR links to task", "Verification notes are present"]},
        },
    }


def default_definition_of_ready_policy() -> dict:
    return {
        "schema_version": 1,
        "ready_task_requires": ["expected_output", "acceptance_criteria"],
        "ready_task_recommends": ["assigned_to", "role", "target_repo", "milestone", "reviewer"],
        "active_task_requires": ["assigned_to_staff_email"],
        "ready_doc_requires": ["owner", "status", "required_sections"],
    }


def default_definition_of_done_policy() -> dict:
    return {
        "schema_version": 1,
        "done_requires": ["output", "acceptance_criteria", "approved_review"],
        "verified_requires": ["output", "acceptance_criteria", "approved_review"],
        "code_output_requires": ["target_repo", "output_commit"],
        "attempt_events": ["submitted_output", "output_attempted", "verification_failed", "output_withdrawn", "output_superseded", "review_cancelled"],
        "objective_failures_block_merge": True,
        "subjective_failures_create_review": True,
    }


def default_review_gates_policy() -> dict:
    return {
        "schema_version": 1,
        "submit_output_status": "In Review",
        "approved_review_status": "Verified",
        "changes_requested_status": "In Progress",
        "verification_failed_status": "In Progress",
        "withdrawn_output_status": "In Progress",
        "cancelled_review_status": "In Progress",
        "reject_done_without_output": True,
        "reject_done_without_approved_review": True,
        "reject_verified_without_approved_review": True,
        "reject_done_when_output_not_objectively_verifiable": True,
        "allow_failed_subjective_review_history": True,
        "record_all_output_attempts": True,
    }


def default_role_permissions_policy() -> dict:
    return {
        "schema_version": 1,
        "roles": {
            "owner": {"can_merge": True, "can_change_policies": True, "can_verify_tasks": True},
            "manager": {"can_create_projects": True, "can_create_tasks": True, "can_create_docs": True, "can_review": True},
            "assignee": {"can_update_assigned_tasks": True, "can_submit_output": True, "can_verify_tasks": False},
            "reviewer": {"can_review": True, "can_verify_tasks": True},
        },
        "protected_statuses": ["Done", "Verified", "Iceboxed"],
    }


def default_storage_policy() -> dict:
    return {
        "schema_version": 1,
        "small_previews": {"allowed_in_git": True, "recommended_max_mb": 5},
        "large_artifacts": ["video", "build", "source-art", "3d-source", "dataset"],
        "large_artifact_storage": ["git-lfs", "release", "package-registry", "object-storage", "implementation-repo"],
        "must_register_assets": True,
    }


def branch_protection_doc() -> str:
    return """# Branch Protection

Protect the default branch.

Required checks:

- `validate`
- `audit-docs`
- website/runtime smoke test when website code changes

Rules:

- Durable changes merge through PRs/MRs.
- Schema, policy, and template changes require owner/manager review.
- A PR/MR that marks a task `Done` or `Verified` must pass objective validation before merge.
- If output cannot be accessed or parsed, reject the PR/MR and record failed verification instead of merging an invalid completed state.
"""


def agent_operating_rules_doc() -> str:
    return """# Agent Operating Rules

Agents should:

- Pull latest Git state before reading tasks or docs.
- Read the project README, roadmap, task folder, linked docs, and linked implementation repos before changing work.
- Use controller commands for IDs, task updates, docs, assets, events, reviews, and milestones.
- Prefer `In Review` plus a recorded/submitted output over directly marking work `Done`.
- Record failed verification, withdrawn outputs, superseded outputs, and cancelled reviews instead of losing attempt history.
- Preserve historical records. Add decisions, project notes, events, or reviews instead of rewriting completed context.
- Run `validate`, `audit-docs`, and `compile` before proposing a durable change.
"""


def default_terminology_policy() -> dict:
    return {
        "schema_version": 1,
        "review_scope": "live-docs-and-master-files",
        "skip_paths": ["registry.yaml", "policies/*"],
        "allowed_occurrences": [],
        "preferred_terms": [
            {
                "preferred": "champion",
                "avoid": ["hero", "heroes"],
                "note": "Example only. Replace or remove based on project terminology decisions.",
                "enabled": False,
            }
        ],
    }


def wiki_guidelines_doc() -> str:
    doc_types = "\n".join(f"- `{doc_type}`: {', '.join(DOC_SECTION_REQUIREMENTS.get(doc_type, ['Purpose', 'Context', 'Content']))}" for doc_type in sorted(DOC_TYPES))
    return f"""# Wiki Guidelines

## Project README

Every project README must include:

- `State`: status, current focus, next review, and blockers.
- `Repositories`: implementation repos and ownership.
- `Documents`: canonical docs grouped by purpose.
- `Tasks`: active task IDs and owners.
- `Assets`: important mockups, videos, builds, art, models, captures, and external links.
- `Operating Notes`: cadence, review expectations, and constraints.

Projects should also keep `planning/roadmap.yaml` and optional `planning/milestones/MILESTONE#.yaml` files for roadmap, release, sprint, or vertical-slice planning.

## Documents

Every durable document must be Markdown with frontmatter containing `id`, `project_id`, `type`, `owner`, and `status`.

Every document H1 should start with the document ID, such as `# DOC7 - Core Loop Design`.

## Required Sections

{doc_types}

## Live Documents Versus Historical Records

Live documents are the current source of truth and should be kept consistent when terminology, scope, or ownership changes. Examples: project README files, `project.yaml`, live design specs, current technical specs, active risk logs, and weekly updates.

Historical records are evidence of what happened at the time and should not be rewritten for terminology cleanup. Examples: completed task folders, verified task output records, finalized meeting notes, archived reports, review logs, and event logs.

If `heroes` is renamed to `champions`, update live docs and master files. Do not rewrite an old completed task such as `Create hero Athena`; instead add a decision record or project note explaining the terminology change.

Use statuses:

- `draft`, `live`, `review`: editable current docs.
- `final`, `archived`, `historical`: protected historical docs.

Use `policies/terminology.yaml` for terminology changes that should be enforced in live docs. Do not make the audit scan force changes to historical task titles. If a live overview must quote an old completed task name, add a narrow `allowed_occurrences` entry with the exact quoted text and a reason.

## Tasks

Every task should have an owner, status, expected output, acceptance criteria, and an output link before it can be verified. Code tasks should also have a `target_repo` listed in project `repos` and an `output_commit` for the reviewer to confirm.

Use one folder per task:

- `task.yaml`: durable state and acceptance criteria.
- `notes.md`: task-local working context.
- `outputs.md`: submitted output and verification notes.
- `attachments/`: small task-local references only.

Use `events/task-events.jsonl` for daily notes and handoffs. Use task YAML for durable task state.

Submitted work should move to `In Review`. Do not mark work `Done` or `Verified` unless it has an output link, code commit when applicable, and an approved review record. If the output cannot be objectively accessed or checked, reject the PR/MR rather than merging an invalid completed state. The failed check or review comment is the footprint.

## Assets

Register important assets in `assets/assets.yaml` and `registry.yaml`. Large files should live in Git LFS, releases/packages, object storage, or implementation repos.
"""


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


def approved_review_exists(reviews: list[dict], task_id: str) -> bool:
    return any(row.get("task_id") == task_id and row.get("decision") == "approved" for row in reviews)


def normalize_repo_ref(value: str) -> str:
    clean = (value or "").strip().rstrip("/").lower()
    return clean[:-4] if clean.endswith(".git") else clean


def project_repo_keys(project: dict) -> set[str]:
    keys: set[str] = set()
    for repo_link in project.get("repos", []) or []:
        for field in ["name", "url"]:
            value = normalize_repo_ref(repo_link.get(field, ""))
            if value:
                keys.add(value)
    return keys


def project_repo_matches(project: dict, target_repo: str) -> bool:
    target = normalize_repo_ref(target_repo)
    return bool(target) and target in project_repo_keys(project)


def email_from_actor(value: str) -> str:
    clean = (value or "").strip()
    match = re.search(r"<([^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>", clean)
    if match:
        return match.group(1).lower()
    return clean.lower() if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean) else ""


def actor_has_staff_email(registry: dict, value: str) -> bool:
    clean = (value or "").strip()
    if not clean or clean.lower() in {"unknown", "system"}:
        return True
    if email_from_actor(clean):
        return True
    lower = clean.lower()
    return any(person.get("name", "").lower() == lower and email_from_actor(person.get("email", "")) for person in registry.get("people", []) or [])


def actor_identity_values(value: str, people: list[dict] | None = None) -> set[str]:
    clean = (value or "").strip()
    if not clean:
        return set()
    lower = clean.lower()
    values = {lower}
    email = email_from_actor(clean)
    if email:
        values.add(email)
    for person in people or []:
        person_name = str(person.get("name", "")).strip().lower()
        person_email = email_from_actor(person.get("email", ""))
        if lower in {person_name, person_email, f"{person_name} <{person_email}>"}:
            if person_name:
                values.add(person_name)
            if person_email:
                values.add(person_email)
    return values


def repo_state_unknown(tasks: list[dict], registry: dict) -> list[dict]:
    rows: list[dict] = []
    implementation_outputs = ["pull request", "merge request", "implementation pr", "implementation mr", "commit"]
    for task in open_tasks(tasks):
        expected = str(task.get("expected_output", "")).lower()
        target_repo = task.get("target_repo", "")
        needs_repo = bool(target_repo) or any(label in expected for label in implementation_outputs)
        if not needs_repo:
            continue
        project = registry.get("projects", {}).get(task.get("project_id", ""), {})
        reasons: list[str] = []
        if not target_repo:
            reasons.append("missing_target_repo")
        elif not project_repo_matches(project, target_repo):
            reasons.append("target_repo_not_registered")
        if task.get("status") == "In Review" and task.get("output") and target_repo and not task.get("output_commit"):
            reasons.append("missing_output_commit")
        if reasons:
            rows.append(
                {
                    "task_id": task.get("id", ""),
                    "project_id": task.get("project_id", ""),
                    "title": task.get("title", ""),
                    "assigned_to": task.get("assigned_to", ""),
                    "reviewer": task.get("reviewer", ""),
                    "status": task.get("status", ""),
                    "target_repo": target_repo,
                    "output": task.get("output", ""),
                    "output_commit": task.get("output_commit", ""),
                    "reasons": reasons,
                }
            )
    return rows


def task_folder_from_path(path: str) -> str:
    clean = path.replace("\\", "/")
    if clean.endswith("/task.yaml"):
        return clean.rsplit("/", 1)[0]
    return clean.rsplit(".", 1)[0] if clean.endswith(".yaml") else clean


def validate_repo(repo: Path) -> list[dict]:
    issues: list[dict] = []
    if not registry_path(repo).exists():
        return [issue("error", "REGISTRY_MISSING", "registry.yaml is missing", "registry.yaml")]
    try:
        registry = load_registry(repo)
    except GitPMError as exc:
        return [issue("error", "REGISTRY_PARSE", str(exc), "registry.yaml")]
    for section in ["projects", "milestones", "tasks", "docs", "people", "next_ids"]:
        if section not in registry:
            issues.append(issue("error", "REGISTRY_SECTION", f"{section} must exist", "registry.yaml"))
    for index, person in enumerate(registry.get("people", []) or []):
        if not email_from_actor(person.get("email", "")):
            issues.append(issue("warn", "PEOPLE_EMAIL_MISSING", f"people[{index}] {person.get('name', 'unnamed')} should include a staff email", "registry.yaml"))
    for kind, section in [("project", "projects"), ("milestone", "milestones"), ("task", "tasks"), ("doc", "docs")]:
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
            if not repo_link.get("name"):
                issues.append(issue("warn", "PROJECT_REPO_NAME_MISSING", f"{project_id} has repo link without name", project.get("path", "")))
            if not repo_link.get("provider"):
                issues.append(issue("warn", "PROJECT_REPO_PROVIDER_MISSING", f"{project_id} has repo link without provider", project.get("path", "")))
            if not repo_link.get("url"):
                issues.append(issue("warn", "PROJECT_REPO_URL_MISSING", f"{project_id} has repo link without url", project.get("path", "")))
        if project.get("roadmap") and not safe_repo_path(repo, project.get("roadmap", "")).exists():
            issues.append(issue("warn", "PROJECT_ROADMAP_MISSING", f"{project_id} roadmap file is missing", project.get("roadmap", "")))
    for milestone_id, milestone_ref in registry.get("milestones", {}).items():
        path = milestone_ref.get("path", "")
        try:
            milestone = read_json_subset(safe_repo_path(repo, path), {})
        except GitPMError as exc:
            issues.append(issue("error", "MILESTONE_PARSE", str(exc), path))
            continue
        if milestone.get("id") != milestone_id:
            issues.append(issue("error", "MILESTONE_ID_MISMATCH", f"{path} id is {milestone.get('id')}, expected {milestone_id}", path))
        if milestone.get("project_id") not in registry.get("projects", {}):
            issues.append(issue("error", "REL_MILESTONE_PROJECT", f"{milestone_id} references missing project {milestone.get('project_id')}", path))
        if milestone.get("status", "Planned") not in MILESTONE_STATUSES:
            issues.append(issue("warn", "MILESTONE_STATUS", f"{milestone_id} has unusual status {milestone.get('status')}", path))
        for task_id in milestone.get("linked_tasks", []) or []:
            if task_id not in registry.get("tasks", {}):
                issues.append(issue("error", "REL_MILESTONE_TASK", f"{milestone_id} links missing {task_id}", path))
    for doc_id, doc in registry.get("docs", {}).items():
        if doc.get("project_id") not in registry.get("projects", {}):
            issues.append(issue("error", "REL_DOC_PROJECT", f"{doc_id} references missing project {doc.get('project_id')}", doc.get("path", "")))
        if doc.get("doc_type") not in DOC_TYPES:
            issues.append(issue("warn", "DOC_TYPE", f"{doc_id} has unusual doc_type {doc.get('doc_type')}", doc.get("path", "")))
        if doc.get("status", "draft") not in DOC_STATUSES:
            issues.append(issue("warn", "DOC_STATUS", f"{doc_id} has unusual status {doc.get('status')}", doc.get("path", "")))
        full = safe_repo_path(repo, doc.get("path", ""))
        if full.exists():
            frontmatter, body = parse_frontmatter(read_text(full))
            if frontmatter.get("id") != doc_id:
                issues.append(issue("error", "DOC_ID_MISMATCH", f"{doc.get('path')} frontmatter id should be {doc_id}", doc.get("path", "")))
            if not markdown_title(body, ""):
                issues.append(issue("warn", "DOC_TITLE_MISSING", f"{doc.get('path')} has no H1 title", doc.get("path", "")))
            required_sections = DOC_SECTION_REQUIREMENTS.get(doc.get("doc_type", ""))
            if required_sections:
                present = markdown_h2_sections(body)
                for section in required_sections:
                    if section not in present:
                        issues.append(issue("warn", "DOC_SECTION_MISSING", f"{doc_id} is missing section '{section}'", doc.get("path", "")))
    reviews = read_jsonl(repo / "reviews/task-reviews.jsonl")
    events = read_jsonl(repo / "events/task-events.jsonl")
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
        assigned_to = task.get("assigned_to", "")
        if not assigned_to and not task.get("role"):
            issues.append(issue("warn", "TASK_ASSIGNEE_MISSING", f"{task_id} has no assignee or role placeholder", path))
        if not assigned_to and task.get("role") and task.get("status") not in {"Backlog", "Iceboxed"}:
            issues.append(issue("warn", "TASK_ROLE_ONLY_ASSIGNEE", f"{task_id} is active with only role placeholder {task.get('role')}; assign a staff email", path))
        if assigned_to and not actor_has_staff_email(registry, assigned_to):
            issues.append(issue("warn", "TASK_ASSIGNEE_STAFF_EMAIL", f"{task_id} assignee should be a staff email or a person with email in registry.people", path))
        if task.get("reviewer") and not actor_has_staff_email(registry, task.get("reviewer", "")):
            issues.append(issue("warn", "TASK_REVIEWER_STAFF_EMAIL", f"{task_id} reviewer should be a staff email or a person with email in registry.people", path))
        if task.get("status") not in {"Iceboxed", "Verified"} and not task.get("expected_output"):
            issues.append(issue("warn", "TASK_EXPECTED_OUTPUT_MISSING", f"{task_id} has no expected_output", path))
        if task.get("status") == "Blocked" and not task.get("blocker"):
            issues.append(issue("warn", "TASK_BLOCKER_MISSING", f"{task_id} is blocked without blocker detail", path))
        if task.get("status") == "In Review" and not task.get("output"):
            issues.append(issue("error", "TASK_REVIEW_OUTPUT_MISSING", f"{task_id} is In Review without output link", path))
        if task.get("status") in {"Done", "Verified"} and not task.get("output"):
            issues.append(issue("error", "TASK_OUTPUT_MISSING", f"{task_id} is {task.get('status')} without output link", path))
        if task.get("status") in {"Done", "Verified"} and not approved_review_exists(reviews, task_id):
            issues.append(issue("error", "TASK_APPROVED_REVIEW_MISSING", f"{task_id} is {task.get('status')} without an approved review record", path))
        if task.get("status") in {"Done", "Verified"} and not task.get("acceptance_criteria"):
            issues.append(issue("error", "TASK_ACCEPTANCE_MISSING", f"{task_id} is {task.get('status')} without acceptance criteria", path))
        if task.get("status") in {"Done", "Verified"} and task.get("blocker"):
            issues.append(issue("warn", "TASK_DONE_BLOCKED", f"{task_id} is {task.get('status')} but still has blocker text", path))
        target_repo = task.get("target_repo", "")
        project = registry.get("projects", {}).get(task.get("project_id", ""), {})
        if target_repo and not project_repo_matches(project, target_repo):
            issues.append(issue("warn", "TASK_TARGET_REPO_UNKNOWN", f"{task_id} target_repo {target_repo} is not listed in its project repos", path))
        if task.get("status") == "In Review" and task.get("output") and target_repo and not task.get("output_commit"):
            issues.append(issue("warn", "TASK_OUTPUT_COMMIT_MISSING", f"{task_id} is in review with target_repo but no output_commit", path))
        if task.get("status") in {"Done", "Verified"} and target_repo and not task.get("output_commit"):
            issues.append(issue("error", "TASK_OUTPUT_COMMIT_MISSING", f"{task_id} is {task.get('status')} with target_repo but no output_commit", path))
        if path.endswith("/task.yaml"):
            folder = task_folder_from_path(path)
            for rel in [f"{folder}/notes.md", f"{folder}/outputs.md", f"{folder}/attachments/README.md"]:
                if not safe_repo_path(repo, rel).exists():
                    issues.append(issue("warn", "TASK_FOLDER_FILE_MISSING", f"{task_id} task folder is missing {rel.rsplit('/', 1)[-1]}", rel))
        milestone = task.get("milestone")
        if milestone and milestone not in registry.get("milestones", {}):
            issues.append(issue("error", "REL_TASK_MILESTONE", f"{task_id} references missing {milestone}", path))
        for dep in task.get("dependencies", []) or []:
            if dep not in registry.get("tasks", {}):
                issues.append(issue("error", "REL_TASK_DEPENDENCY", f"{task_id} depends on missing {dep}", path))
    for event in events:
        if event.get("actor") and not actor_has_staff_email(registry, event.get("actor", "")):
            issues.append(issue("warn", "EVENT_ACTOR_STAFF_EMAIL", f"{event.get('id') or event.get('task_id') or 'event'} actor should be a staff email or a person with email in registry.people", "events/task-events.jsonl"))
    for review in reviews:
        if review.get("reviewer") and not actor_has_staff_email(registry, review.get("reviewer", "")):
            issues.append(issue("warn", "REVIEWER_STAFF_EMAIL", f"{review.get('id') or review.get('task_id') or 'review'} reviewer should be a staff email or a person with email in registry.people", "reviews/task-reviews.jsonl"))
    for asset_id, asset in registry.get("assets", {}).items():
        if not re.fullmatch(r"ASSET\d+", asset_id):
            issues.append(issue("error", "ASSET_ID_FORMAT", f"{asset_id} should match ASSET#", "registry.yaml"))
        if not asset.get("path") and not asset.get("source_url"):
            issues.append(issue("warn", "ASSET_LINK_MISSING", f"{asset_id} has no path or source_url", "registry.yaml"))
    for rel in [
        "policies/output-requirements.yaml",
        "policies/definition-of-ready.yaml",
        "policies/definition-of-done.yaml",
        "policies/review-gates.yaml",
        "policies/role-permissions.yaml",
        "policies/storage-policy.yaml",
        "policies/wiki-guidelines.md",
        "policies/terminology.yaml",
        "policies/branch-protection.md",
        "policies/agent-operating-rules.md",
    ]:
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
        path = safe_repo_path(repo, row.get("path", ""))
        text = read_text(path)
        frontmatter, body = parse_frontmatter(text)
        headings = [line[3:].strip() for line in body.splitlines() if line.startswith("## ")]
        title = markdown_title(body, row.get("title", doc_id))
        plain = re.sub(r"\s+", " ", " ".join(filter(None, (clean_markdown_line(line) for line in body.splitlines())))).strip()
        docs.append(
            {
                "id": doc_id,
                "project_id": row.get("project_id", ""),
                "type": row.get("doc_type") or frontmatter.get("type", ""),
                "title": title,
                "path": row.get("path", ""),
                "owner": row.get("owner", ""),
                "status": row.get("status", ""),
                "sha256": file_sha256(path),
                "headings": headings,
                "preview": markdown_preview(body, title),
                "snippet": plain[:280],
                "search_text": plain[:12000],
                "markdown": body,
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
        merged["folder"] = ref.get("folder") or task_folder_from_path(ref.get("path", ""))
        merged["sha256"] = file_sha256(safe_repo_path(repo, ref.get("path", ""))) if ref.get("path") else ""
        tasks.append(merged)
    return tasks


def collect_milestones(repo: Path, registry: dict) -> list[dict]:
    rows = []
    for milestone_id, ref in registry.get("milestones", {}).items():
        try:
            milestone = read_json_subset(safe_repo_path(repo, ref.get("path", "")), {})
        except GitPMError:
            milestone = {"id": milestone_id, "title": ref.get("title", ""), "status": "Invalid"}
        merged = {**ref, **milestone}
        merged["id"] = milestone_id
        merged["path"] = ref.get("path", "")
        merged["sha256"] = file_sha256(safe_repo_path(repo, ref.get("path", ""))) if ref.get("path") else ""
        rows.append(merged)
    return rows


def parse_iso(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def latest_attempts(events: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for event in events:
        if event.get("event_type") in ATTEMPT_EVENT_TYPES and event.get("task_id"):
            latest[event["task_id"]] = event
    return latest


def build_review_queue(tasks: list[dict], events: list[dict], reviews: list[dict]) -> list[dict]:
    latest_by_task = latest_attempts(events)
    latest_review_by_task: dict[str, dict] = {}
    for review in reviews:
        if review.get("task_id"):
            latest_review_by_task[review["task_id"]] = review
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    rows = []
    for task in tasks:
        task_id = task.get("id", "")
        latest = latest_by_task.get(task_id, {})
        event_type = latest.get("event_type", "")
        reasons = []
        age_days = None
        created_at = parse_iso(latest.get("created_at", ""))
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
            age_days = max(0, (now - created_at).days)
        if task.get("status") == "In Review":
            reasons.append("in_review")
            if age_days is not None and age_days >= 3:
                reasons.append("stale_review")
        if event_type == "verification_failed":
            reasons.append("verification_failed")
        if event_type == "output_withdrawn":
            reasons.append("output_withdrawn")
        if event_type == "review_cancelled":
            reasons.append("review_cancelled")
        if reasons:
            rows.append(
                {
                    "task_id": task_id,
                    "title": task.get("title", ""),
                    "assigned_to": task.get("assigned_to", ""),
                    "reviewer": task.get("reviewer", ""),
                    "status": task.get("status", ""),
                    "output": task.get("output", ""),
                    "reasons": reasons,
                    "age_days": age_days,
                    "latest_attempt": latest,
                    "latest_review": latest_review_by_task.get(task_id, {}),
                }
            )
    return rows


def open_tasks(tasks: list[dict]) -> list[dict]:
    return [task for task in tasks if task.get("status") not in HISTORICAL_TASK_STATUSES]


def assigned_tasks(tasks: list[dict], user: str, include_done: bool = False, people: list[dict] | None = None) -> list[dict]:
    needle = actor_identity_values(user, people)
    rows = []
    for task in tasks:
        assignee = actor_identity_values(task.get("assigned_to", ""), people)
        reviewer = actor_identity_values(task.get("reviewer", ""), people)
        if needle and not (needle & assignee or needle & reviewer):
            continue
        if not include_done and task.get("status") in HISTORICAL_TASK_STATUSES:
            continue
        rows.append(task)
    return rows


def blocked_tasks(tasks: list[dict]) -> list[dict]:
    return [task for task in tasks if task.get("status") == "Blocked" or task.get("blocker")]


def stale_work(tasks: list[dict], events: list[dict], days: int = 3) -> list[dict]:
    latest_by_task: dict[str, dict] = {}
    for event in events:
        if event.get("task_id"):
            latest_by_task[event["task_id"]] = event
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    rows = []
    for task in open_tasks(tasks):
        latest = latest_by_task.get(task.get("id", ""), {})
        created_at = parse_iso(latest.get("created_at", ""))
        age_days = None
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
            age_days = max(0, (now - created_at).days)
        if age_days is None or age_days >= days:
            rows.append({**task, "latest_event": latest, "age_days": age_days})
    return rows


def feature_proposals(docs: list[dict]) -> list[dict]:
    return [doc for doc in docs if doc.get("type") in {"feature-proposal", "feature-brief"} and doc.get("status") in LIVE_DOC_STATUSES]


def project_status_summary(data: dict, project_id: str = "") -> dict:
    projects = data.get("projects", [])
    selected = [project for project in projects if not project_id or project.get("id") == project_id]
    if project_id and not selected:
        return {
            "projects": [],
            "counts": {"projects": 0, "docs": 0, "tasks": 0, "open_tasks": 0, "blocked_tasks": 0, "review_queue": 0, "stale_work": 0, "feature_proposals": 0, "repo_state_unknown": 0, "validation_issues": len(data.get("validation", {}).get("issues", []))},
            "blocked_tasks": [],
            "review_queue": [],
            "stale_work": [],
            "feature_proposals": [],
            "repo_state_unknown": [],
        }
    selected_ids = {project.get("id") for project in selected}
    tasks = [task for task in data.get("tasks", []) if not selected_ids or task.get("project_id") in selected_ids]
    docs = [doc for doc in data.get("docs", []) if not selected_ids or doc.get("project_id") in selected_ids]
    review_queue = [row for row in data.get("review_queue", []) if any(task.get("id") == row.get("task_id") for task in tasks)]
    repo_unknown = [row for row in data.get("repo_state_unknown", []) if any(task.get("id") == row.get("task_id") for task in tasks)]
    blocked = blocked_tasks(tasks)
    stale = stale_work(tasks, data.get("events", []))
    return {
        "projects": selected,
        "counts": {
            "projects": len(selected),
            "docs": len(docs),
            "tasks": len(tasks),
            "open_tasks": len(open_tasks(tasks)),
            "blocked_tasks": len(blocked),
            "review_queue": len(review_queue),
            "stale_work": len(stale),
            "feature_proposals": len(feature_proposals(docs)),
            "repo_state_unknown": len(repo_unknown),
            "validation_issues": len(data.get("validation", {}).get("issues", [])),
        },
        "blocked_tasks": blocked,
        "review_queue": review_queue,
        "stale_work": stale,
        "feature_proposals": feature_proposals(docs),
        "repo_state_unknown": repo_unknown,
    }


def build_search_index(data: dict) -> list[dict]:
    rows = []
    for project in data.get("projects", []):
        rows.append({"kind": "project", "id": project.get("id", ""), "title": project.get("name", ""), "path": project.get("readme", ""), "text": " ".join([project.get("name", ""), project.get("summary", ""), project.get("status", "")])})
    for milestone in data.get("milestones", []):
        rows.append({"kind": "milestone", "id": milestone.get("id", ""), "title": milestone.get("title", ""), "path": milestone.get("path", ""), "text": json.dumps(milestone, ensure_ascii=False)})
    for task in data.get("tasks", []):
        rows.append({"kind": "task", "id": task.get("id", ""), "title": task.get("title", ""), "path": task.get("path", ""), "text": json.dumps(task, ensure_ascii=False)})
    for doc in data.get("docs", []):
        rows.append({"kind": "doc", "id": doc.get("id", ""), "title": doc.get("title", ""), "path": doc.get("path", ""), "text": " ".join([doc.get("title", ""), doc.get("type", ""), doc.get("owner", ""), doc.get("search_text", "")])})
    for asset in data.get("assets", []):
        rows.append({"kind": "asset", "id": asset.get("id", ""), "title": asset.get("title", ""), "path": asset.get("path", ""), "text": json.dumps(asset, ensure_ascii=False)})
    for event in data.get("events", []):
        rows.append({"kind": "event", "id": event.get("id", ""), "title": event.get("event_type", ""), "path": "events/task-events.jsonl", "text": json.dumps(event, ensure_ascii=False)})
    for review in data.get("reviews", []):
        rows.append({"kind": "review", "id": review.get("id", ""), "title": review.get("decision", ""), "path": "reviews/task-reviews.jsonl", "text": json.dumps(review, ensure_ascii=False)})
    return rows


def compile_data(repo: Path) -> dict:
    registry = load_registry(repo)
    issues = validate_repo(repo)
    events = read_jsonl(repo / "events/task-events.jsonl")
    reviews = read_jsonl(repo / "reviews/task-reviews.jsonl")
    tasks = collect_tasks(repo, registry)
    docs = collect_docs(repo, registry)
    data = {
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
        "milestones": collect_milestones(repo, registry),
        "docs": docs,
        "tasks": tasks,
        "assets": [{"id": key, **value} for key, value in registry.get("assets", {}).items()],
        "people": registry.get("people", []),
        "events": events,
        "reviews": reviews,
        "latest_attempts": latest_attempts(events),
        "review_queue": build_review_queue(tasks, events, reviews),
        "blocked_tasks": blocked_tasks(tasks),
        "stale_work": stale_work(tasks, events),
        "feature_proposals": feature_proposals(docs),
        "repo_state_unknown": repo_state_unknown(tasks, registry),
        "validation": {"issues": issues},
    }
    data["project_status"] = project_status_summary(data)
    data["search_index"] = build_search_index(data)
    return data


def cmd_compile(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    data = compile_data(repo)
    output = repo / ".project-hub/site-data/project-hub.json"
    search_output = repo / ".project-hub/site-data/search-index.json"
    write_text(output, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    write_text(search_output, json.dumps(data["search_index"], indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "search_index": str(search_output), "issues": data["validation"]["issues"]}, indent=2) if args.json else f"Wrote {output} and {search_output}")
    return 1 if any(item["level"] == "error" for item in data["validation"]["issues"]) else 0


def print_task_lines(tasks: list[dict]) -> None:
    if not tasks:
        print("No matching tasks.")
        return
    for task in tasks:
        blocker = f" blocker={task.get('blocker')}" if task.get("blocker") else ""
        output = f" output={task.get('output')}" if task.get("output") else ""
        print(f"{task.get('id')} [{task.get('status')}] {task.get('title')} owner={task.get('assigned_to') or 'Unassigned'} expected={task.get('expected_output') or 'TBD'} path={task.get('path')}{blocker}{output}")


def cmd_my_tasks(args: argparse.Namespace) -> int:
    data = compile_data(repo_arg(args.repo))
    rows = assigned_tasks(data["tasks"], args.user, args.include_done, data.get("people", []))
    if args.json:
        print(json.dumps({"user": args.user, "tasks": rows}, indent=2))
    else:
        print_task_lines(rows)
    return 0


def cmd_project_status(args: argparse.Namespace) -> int:
    data = compile_data(repo_arg(args.repo))
    summary = project_status_summary(data, args.project_id)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(summary["counts"], indent=2))
        if summary["blocked_tasks"]:
            print("\nBlocked:")
            print_task_lines(summary["blocked_tasks"])
        if summary["review_queue"]:
            print("\nReview Queue:")
            for row in summary["review_queue"]:
                print(f"{row.get('task_id')} reasons={','.join(row.get('reasons', []))} owner={row.get('assigned_to') or 'Unassigned'} output={row.get('output') or 'None'}")
        if summary["feature_proposals"]:
            print("\nFeature Proposals:")
            for doc in summary["feature_proposals"]:
                print(f"{doc.get('id')} [{doc.get('status')}] {doc.get('title')} owner={doc.get('owner')} path={doc.get('path')}")
        if summary["repo_state_unknown"]:
            print("\nRepo Verification Gaps:")
            for row in summary["repo_state_unknown"]:
                print(f"{row.get('task_id')} reasons={','.join(row.get('reasons', []))} target_repo={row.get('target_repo') or 'None'} output_commit={row.get('output_commit') or 'None'}")
    return 0


def cmd_review_queue(args: argparse.Namespace) -> int:
    data = compile_data(repo_arg(args.repo))
    rows = data.get("review_queue", [])
    if args.json:
        print(json.dumps({"review_queue": rows}, indent=2))
    else:
        if not rows:
            print("Review queue is empty.")
        for row in rows:
            print(f"{row.get('task_id')} reasons={','.join(row.get('reasons', []))} status={row.get('status')} owner={row.get('assigned_to') or 'Unassigned'} reviewer={row.get('reviewer') or 'Unassigned'} output={row.get('output') or 'None'}")
    return 0


def cmd_blocked_tasks(args: argparse.Namespace) -> int:
    data = compile_data(repo_arg(args.repo))
    rows = blocked_tasks(data["tasks"])
    if args.json:
        print(json.dumps({"blocked_tasks": rows}, indent=2))
    else:
        print_task_lines(rows)
    return 0


def cmd_stale_work(args: argparse.Namespace) -> int:
    data = compile_data(repo_arg(args.repo))
    rows = stale_work(data["tasks"], data["events"], args.days)
    if args.json:
        print(json.dumps({"days": args.days, "stale_work": rows}, indent=2))
    else:
        print_task_lines(rows)
    return 0


def live_document_paths(registry: dict) -> list[str]:
    paths = [
        "README.md",
        "START_HERE_FOR_AGENTS.md",
        "registry.yaml",
        "policies/wiki-guidelines.md",
        "policies/output-requirements.yaml",
        "policies/definition-of-ready.yaml",
        "policies/definition-of-done.yaml",
        "policies/review-gates.yaml",
        "policies/role-permissions.yaml",
        "policies/storage-policy.yaml",
        "policies/terminology.yaml",
    ]
    for project in registry.get("projects", {}).values():
        for key in ["readme", "path", "roadmap"]:
            if project.get(key):
                paths.append(project[key])
    for doc in registry.get("docs", {}).values():
        if doc.get("status", "draft") in LIVE_DOC_STATUSES and doc.get("path"):
            paths.append(doc["path"])
    return list(dict.fromkeys(paths))


def terminology_policy(repo: Path) -> dict:
    return read_json_subset(repo / "policies/terminology.yaml", {"preferred_terms": [], "skip_paths": [], "allowed_occurrences": []})


def terminology_rules(policy: dict) -> list[dict]:
    return [rule for rule in policy.get("preferred_terms", []) if rule.get("enabled", True)]


def path_matches_any(rel: str, patterns: list[str]) -> bool:
    clean = rel.replace("\\", "/").lstrip("/")
    return any(fnmatch.fnmatch(clean, pattern.replace("\\", "/").lstrip("/")) for pattern in patterns)


def occurrence_allowed(policy: dict, rel: str, term: str, text: str, start: int) -> bool:
    for item in policy.get("allowed_occurrences", []) or []:
        if str(item.get("term", "")).lower() != str(term).lower() or not path_matches_any(rel, [str(item.get("path", ""))]):
            continue
        exact = str(item.get("text", "")).strip()
        if not exact:
            return True
        for match in re.finditer(re.escape(exact), text, re.IGNORECASE):
            if match.start() <= start < match.end():
                return True
    return False


def audit_docs(repo: Path) -> list[dict]:
    issues = validate_repo(repo)
    if not registry_path(repo).exists():
        return issues
    registry = load_registry(repo)
    for rel in live_document_paths(registry):
        if not safe_repo_path(repo, rel).exists():
            issues.append(issue("warn", "MASTER_FILE_MISSING", f"expected live/master file is missing: {rel}", rel))
    policy = terminology_policy(repo)
    skip_paths = list(policy.get("skip_paths", []) or []) + ["registry.yaml", "policies/terminology.yaml"]
    scan_paths = [rel for rel in live_document_paths(registry) if not path_matches_any(rel, skip_paths)]
    for rule in terminology_rules(policy):
        preferred = rule.get("preferred", "")
        for avoid in rule.get("avoid", []) or []:
            pattern = re.compile(rf"\b{re.escape(str(avoid))}\b", re.IGNORECASE)
            for rel in scan_paths:
                path = safe_repo_path(repo, rel)
                if not path.exists() or path.is_dir():
                    continue
                text = read_text(path)
                if any(not occurrence_allowed(policy, rel, str(avoid), text, match.start()) for match in pattern.finditer(text)):
                    issues.append(issue("warn", "TERMINOLOGY_DRIFT", f"use '{preferred}' instead of '{avoid}' in live/master file", rel))
    for task_id, ref in registry.get("tasks", {}).items():
        if ref.get("status") in HISTORICAL_TASK_STATUSES:
            continue
        path = ref.get("path", "")
        if path:
            task = read_json_subset(safe_repo_path(repo, path), {})
            if task.get("status") == "Blocked" and not task.get("blocker"):
                issues.append(issue("warn", "BLOCKED_TASK_DETAIL", f"{task_id} is blocked without blocker detail", path))
    return issues


def cmd_audit_docs(args: argparse.Namespace) -> int:
    issues = audit_docs(repo_arg(args.repo))
    if args.json:
        print(json.dumps({"issues": issues}, indent=2))
    else:
        if not issues:
            print("Document audit passed.")
        for item in issues:
            location = f" [{item['path']}]" if item.get("path") else ""
            print(f"{item['level'].upper()} {item['code']}: {item['message']}{location}")
    return 1 if any(item["level"] == "error" for item in issues) else 0


def cmd_create_project(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    project_id = allocate_id(registry, "project")
    project = make_project_record(project_id, args.name, args.owner, args.type, args.status)
    registry.setdefault("projects", {})[project_id] = project
    write_text(repo / project["path"], dump(project))
    write_text(repo / project["readme"], markdown_doc({"id": project_id, "type": "project", "owner": args.owner, "status": args.status}, f"{project_id} - {args.name}", project_readme_body(project)))
    write_text(repo / project["roadmap"], dump(default_roadmap(project)))
    write_text(repo / f"projects/{project_folder(project_id, args.name)}/assets/assets.yaml", dump({"assets": {}}))
    save_registry(repo, registry)
    print(f"Created {project_id} at {project['readme']}")
    return 0


def create_task_payload(registry: dict, project_id: str, title: str, assigned_to: str, role: str, expected_output: str, target_repo: str = "") -> tuple[str, str, dict]:
    projects = registry.get("projects", {})
    if project_id not in projects:
        raise GitPMError(f"missing project {project_id}")
    task_id = allocate_id(registry, "task")
    path, task, ref = make_task(task_id, project_id, projects[project_id]["name"], title, assigned_to, role, expected_output)
    if target_repo:
        task["target_repo"] = target_repo
        ref["target_repo"] = target_repo
    registry.setdefault("tasks", {})[task_id] = ref
    return task_id, path, task


def cmd_create_task(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    task_id, path, task = create_task_payload(registry, args.project_id, args.title, args.assigned_to, args.role, args.expected_output, args.target_repo)
    write_text(repo / path, dump(task))
    for rel, text in task_support_files(path, task).items():
        write_text(repo / rel, text)
    save_registry(repo, registry)
    print(f"Created {task_id} at {path}")
    return 0


def cmd_create_milestone(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    registry = load_registry(repo)
    project = registry.get("projects", {}).get(args.project_id)
    if not project:
        raise GitPMError(f"missing project {args.project_id}")
    milestone_id = allocate_id(registry, "milestone")
    path, milestone, ref = make_milestone(milestone_id, args.project_id, project["name"], args.title, args.owner, args.status)
    registry.setdefault("milestones", {})[milestone_id] = ref
    project.setdefault("milestones", []).append(milestone_id)
    write_text(repo / project["path"], dump(project))
    roadmap_path = project.get("roadmap", "")
    if roadmap_path:
        roadmap = read_json_subset(safe_repo_path(repo, roadmap_path), default_roadmap(project))
        roadmap.setdefault("milestones", []).append(milestone_id)
        write_text(repo / roadmap_path, dump(roadmap))
    write_text(repo / path, dump(milestone))
    save_registry(repo, registry)
    print(f"Created {milestone_id} at {path}")
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


def propose_feature_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    project = registry.get("projects", {}).get(payload.get("project_id", ""))
    if not project:
        raise GitPMError(f"missing project {payload.get('project_id')}")
    doc_id = allocate_id(registry, "doc")
    rel, text, ref = make_feature_proposal_doc(doc_id, project, payload)
    registry.setdefault("docs", {})[doc_id] = ref
    title = f"Propose feature {doc_id}: {payload.get('title', '')}"
    return title, title, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "create", "file_path": rel, "content": text},
    ]


def cmd_propose_feature(args: argparse.Namespace) -> int:
    payload = {
        "type": "propose_feature",
        "project_id": args.project_id,
        "title": args.title,
        "owner": args.owner,
        "problem": args.problem,
        "value": args.value,
        "scope": args.scope,
        "non_goals": args.non_goals,
        "risks": args.risks,
        "task_breakdown": args.task_breakdown,
        "decision_needed": args.decision_needed,
    }
    result = apply_payload(repo_arg(args.repo), payload)
    print(json.dumps(result, indent=2))
    return 0


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def append_jsonl(existing: str, record: dict) -> str:
    prefix = existing.rstrip("\n")
    line = json.dumps(record, ensure_ascii=False)
    return f"{prefix}\n{line}\n" if prefix else f"{line}\n"


def load_task_record(repo: Path, registry: dict, task_id: str) -> tuple[str, dict]:
    ref = registry.get("tasks", {}).get(task_id)
    if not ref:
        raise GitPMError(f"missing task {task_id}")
    path = ref.get("path", "")
    task = read_json_subset(safe_repo_path(repo, path), {})
    if task.get("id") != task_id:
        raise GitPMError(f"{path} id is {task.get('id')}, expected {task_id}")
    return path, task


def historical_edit_reason(registry: dict, rel: str) -> str:
    clean = rel.replace("\\", "/").lstrip("/")
    if clean in {"events/task-events.jsonl", "reviews/task-reviews.jsonl"}:
        return f"{clean} is append-only; use add-event or review-task"
    for task_id, ref in registry.get("tasks", {}).items():
        if ref.get("path") == clean:
            status = ref.get("status", "")
            if status in HISTORICAL_TASK_STATUSES:
                return f"{task_id} is {status}; completed task records are historical"
    for doc_id, doc in registry.get("docs", {}).items():
        if doc.get("path") == clean:
            status = doc.get("status", "draft")
            if status in HISTORICAL_DOC_STATUSES:
                return f"{doc_id} is {status}; finalized docs are historical"
    return ""


def ensure_edit_allowed(registry: dict, rel: str, payload: dict) -> None:
    reason = historical_edit_reason(registry, rel)
    if reason and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to edit historical record: {reason}. Create a project-note/decision/errata or reopen through review workflow instead.")


def sync_task_ref(registry: dict, task_id: str, path: str, task: dict) -> None:
    registry.setdefault("tasks", {})[task_id] = {
        "project_id": task.get("project_id", ""),
        "path": path,
        "folder": task_folder_from_path(path),
        "title": task.get("title", ""),
        "assigned_to": task.get("assigned_to", ""),
        "status": task.get("status", "Backlog"),
        "milestone": task.get("milestone", ""),
        "feature_area": task.get("feature_area", ""),
        "expected_output": task.get("expected_output", ""),
        "target_repo": task.get("target_repo", ""),
        "output_commit": task.get("output_commit", ""),
    }


def make_event(registry: dict, task: dict, actor: str, event_type: str, message: str, extra: dict | None = None) -> dict:
    event_id = allocate_id(registry, "event")
    record = {
        "id": event_id,
        "task_id": task.get("id", ""),
        "project_id": task.get("project_id", ""),
        "actor": actor or "Unknown",
        "event_type": event_type or "update",
        "message": message or "",
        "created_at": now_iso(),
    }
    for key, value in (extra or {}).items():
        if value is not None:
            record[key] = value
    return record


def event_action(repo: Path, record: dict) -> dict:
    rel = "events/task-events.jsonl"
    return {"action": "update" if (repo / rel).exists() else "create", "file_path": rel, "content": append_jsonl(read_text(repo / rel), record)}


def review_action(repo: Path, record: dict) -> dict:
    rel = "reviews/task-reviews.jsonl"
    return {"action": "update" if (repo / rel).exists() else "create", "file_path": rel, "content": append_jsonl(read_text(repo / rel), record)}


def update_task_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to update {task_id}; {task.get('status')} tasks are historical. Use review-task to request changes or create a project-note/decision for later context.")
    if payload.get("commit") and not payload.get("output_commit"):
        payload["output_commit"] = payload["commit"]
    for field in ["status", "checkpoint", "priority", "assigned_to", "deadline", "milestone", "feature_area", "release_target", "estimate", "risk", "reviewer", "expected_output", "target_repo", "output", "output_commit", "blocker", "ai_update", "user_update"]:
        value = payload.get(field)
        if value not in (None, ""):
            task[field] = value
    if payload.get("acceptance_criteria"):
        task["acceptance_criteria"] = split_csv(payload.get("acceptance_criteria"))
    if payload.get("dependencies"):
        task["dependencies"] = split_csv(payload.get("dependencies"))
    sync_task_ref(registry, task_id, path, task)
    title = f"Update {task_id}: {task.get('title', '')}"
    actions = [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
    ]
    message = payload.get("event_message") or payload.get("user_update") or payload.get("ai_update") or f"Updated {task_id}"
    if not payload.get("suppress_event") and (payload.get("actor") or payload.get("event_message") or payload.get("user_update") or payload.get("status")):
        actions.append(event_action(repo, make_event(registry, task, payload.get("actor", ""), "task_update", message)))
        actions[0]["content"] = dump(registry)
    return title, message, actions


def submit_output_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    if payload.get("commit") and not payload.get("output_commit"):
        payload["output_commit"] = payload["commit"]
    payload = {**payload, "status": payload.get("status") or "In Review", "checkpoint": payload.get("checkpoint") or "Review", "suppress_event": True}
    title, _message, actions = update_task_actions(repo, registry, payload)
    task_id = payload.get("task_id", "")
    _path, task = load_task_record(repo, registry, task_id)
    event = make_event(
        registry,
        task,
        payload.get("actor", ""),
        "submitted_output",
        payload.get("message") or payload.get("output") or f"Submitted output for {task_id}",
        {"output": payload.get("output", ""), "target_repo": task.get("target_repo", ""), "output_commit": task.get("output_commit", "")},
    )
    actions[0]["content"] = dump(registry)
    actions.append(event_action(repo, event))
    return title.replace("Update", "Submit output for", 1), event["message"], actions


def review_task_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to review {task_id}; {task.get('status')} tasks are historical. Create a follow-up task, decision, project-note, or errata instead.")
    decision = payload.get("decision", "changes_requested")
    if decision == "approved":
        task["status"] = "Verified"
        task["checkpoint"] = "Ready"
    elif decision in {"changes_requested", "rejected", "verification_failed", "cancelled"}:
        task["status"] = "In Progress"
        task["checkpoint"] = "Revising"
    sync_task_ref(registry, task_id, path, task)
    review_id = allocate_id(registry, "review")
    review = {
        "id": review_id,
        "task_id": task_id,
        "project_id": task.get("project_id", ""),
        "reviewer": payload.get("reviewer", ""),
        "decision": decision,
        "notes": payload.get("notes", ""),
        "created_at": now_iso(),
    }
    event_type = {"verification_failed": "verification_failed", "cancelled": "review_cancelled"}.get(decision, f"review_{decision}")
    event = make_event(
        registry,
        task,
        payload.get("reviewer", ""),
        event_type,
        payload.get("notes", "") or f"{decision} review for {task_id}",
        {"review_id": review_id, "decision": decision, "output": task.get("output", ""), "target_repo": task.get("target_repo", ""), "output_commit": task.get("output_commit", "")},
    )
    title = f"Review {task_id}: {decision}"
    return title, event["message"], [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        review_action(repo, review),
        event_action(repo, event),
    ]


def record_attempt_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to record a new attempt for {task_id}; {task.get('status')} tasks are historical. Reopen through review workflow or create a follow-up task.")
    output = payload.get("output", "")
    task["status"] = "In Review"
    task["checkpoint"] = "Review"
    if payload.get("target_repo"):
        task["target_repo"] = payload["target_repo"]
    output_commit = payload.get("output_commit") or payload.get("commit", "")
    if output_commit:
        task["output_commit"] = output_commit
    if output:
        task["output"] = output
    message = payload.get("message") or output or f"Output attempt recorded for {task_id}"
    task["user_update"] = message
    sync_task_ref(registry, task_id, path, task)
    event = make_event(
        registry,
        task,
        payload.get("actor", ""),
        "output_attempted",
        message,
        {"output": output or task.get("output", ""), "target_repo": task.get("target_repo", ""), "output_commit": task.get("output_commit", "")},
    )
    return f"Record attempt for {task_id}", message, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        event_action(repo, event),
    ]


def record_verification_failed_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to record failed verification for {task_id}; {task.get('status')} tasks are historical. Create a follow-up task, decision, project-note, or errata instead.")
    reason = payload.get("reason") or payload.get("notes") or "Output could not be objectively verified."
    reviewer = payload.get("reviewer", "")
    task["status"] = "In Progress"
    task["checkpoint"] = "Revising"
    task["user_update"] = f"Verification failed: {reason}"
    sync_task_ref(registry, task_id, path, task)
    review_id = allocate_id(registry, "review")
    review = {
        "id": review_id,
        "task_id": task_id,
        "project_id": task.get("project_id", ""),
        "reviewer": reviewer,
        "decision": "verification_failed",
        "notes": reason,
        "created_at": now_iso(),
    }
    event = make_event(
        registry,
        task,
        reviewer,
        "verification_failed",
        reason,
        {"review_id": review_id, "decision": "verification_failed", "output": payload.get("output") or task.get("output", ""), "target_repo": task.get("target_repo", ""), "output_commit": task.get("output_commit", "")},
    )
    return f"Verification failed for {task_id}", reason, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        review_action(repo, review),
        event_action(repo, event),
    ]


def withdraw_output_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to withdraw output for {task_id}; {task.get('status')} tasks are historical. Create a follow-up task, decision, project-note, or errata instead.")
    reason = payload.get("reason") or "Output withdrawn."
    previous_output = payload.get("output") or task.get("output", "")
    task["status"] = "In Progress"
    task["checkpoint"] = "Revising"
    task["output"] = ""
    task["user_update"] = f"Output withdrawn: {reason}"
    sync_task_ref(registry, task_id, path, task)
    event = make_event(registry, task, payload.get("actor", ""), "output_withdrawn", reason, {"previous_output": previous_output})
    return f"Withdraw output for {task_id}", reason, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        event_action(repo, event),
    ]


def supersede_output_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to supersede output for {task_id}; {task.get('status')} tasks are historical. Create a follow-up task, decision, project-note, or errata instead.")
    new_output = payload.get("new_output") or payload.get("output", "")
    if not new_output:
        raise GitPMError("supersede_output requires new_output")
    reason = payload.get("reason") or "Output superseded."
    old_output = payload.get("old_output") or task.get("output", "")
    task["status"] = "In Review"
    task["checkpoint"] = "Review"
    task["output"] = new_output
    task["user_update"] = f"Output superseded: {reason}"
    sync_task_ref(registry, task_id, path, task)
    event = make_event(registry, task, payload.get("actor", ""), "output_superseded", reason, {"old_output": old_output, "new_output": new_output})
    return f"Supersede output for {task_id}", reason, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        event_action(repo, event),
    ]


def cancel_review_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    if task.get("status") in HISTORICAL_TASK_STATUSES and not payload.get("allow_historical_edit"):
        raise GitPMError(f"refusing to cancel review for {task_id}; {task.get('status')} tasks are historical. Create a follow-up task, decision, project-note, or errata instead.")
    reason = payload.get("reason") or payload.get("notes") or "Review cancelled."
    actor = payload.get("actor") or payload.get("reviewer", "")
    task["status"] = "In Progress"
    task["checkpoint"] = "Revising"
    task["user_update"] = f"Review cancelled: {reason}"
    sync_task_ref(registry, task_id, path, task)
    review_id = allocate_id(registry, "review")
    review = {
        "id": review_id,
        "task_id": task_id,
        "project_id": task.get("project_id", ""),
        "reviewer": actor,
        "decision": "cancelled",
        "notes": reason,
        "created_at": now_iso(),
    }
    event = make_event(registry, task, actor, "review_cancelled", reason, {"review_id": review_id, "output": task.get("output", "")})
    return f"Cancel review for {task_id}", reason, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        review_action(repo, review),
        event_action(repo, event),
    ]


def register_repo_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    project_id = payload.get("project_id", "")
    project = registry.get("projects", {}).get(project_id)
    if not project:
        raise GitPMError(f"missing project {project_id}")
    name = payload.get("name", "").strip()
    url = payload.get("url", "").strip()
    if not name:
        raise GitPMError("register_repo requires name")
    if not url:
        raise GitPMError("register_repo requires url")
    repo_link = {
        "name": name,
        "provider": payload.get("provider", "").strip() or "github",
        "url": url,
        "default_branch": payload.get("default_branch", "").strip() or "main",
        "role": payload.get("role", "").strip(),
    }
    existing = project.setdefault("repos", [])
    project["repos"] = [row for row in existing if normalize_repo_ref(row.get("name", "")) != normalize_repo_ref(name)]
    project["repos"].append(repo_link)
    registry.setdefault("projects", {})[project_id] = project
    title = f"Register repo {name} for {project_id}"
    return title, title, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": project["path"], "content": dump(project)},
    ]


def register_asset_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    project_id = payload.get("project_id", "")
    project = registry.get("projects", {}).get(project_id)
    if not project:
        raise GitPMError(f"missing project {project_id}")
    asset_id = allocate_id(registry, "asset")
    asset = {
        "title": payload.get("title", ""),
        "type": payload.get("asset_type") or payload.get("type", "asset"),
        "storage": payload.get("storage", "external-link"),
        "path": payload.get("path", ""),
        "source_url": payload.get("source_url", ""),
        "used_by": split_csv(payload.get("used_by")) or [project_id],
        "owner": payload.get("owner", ""),
        "status": payload.get("status", "draft"),
    }
    registry.setdefault("assets", {})[asset_id] = asset
    folder = project_folder(project_id, project["name"])
    rel = f"projects/{folder}/assets/assets.yaml"
    manifest = read_json_subset(repo / rel, {"assets": {}})
    manifest.setdefault("assets", {})[asset_id] = asset
    title = f"Register {asset_id}: {asset['title']}"
    return title, title, [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update" if (repo / rel).exists() else "create", "file_path": rel, "content": dump(manifest)},
    ]


def apply_actions(repo: Path, actions: list[dict]) -> None:
    for action in actions:
        write_text(repo / action["file_path"], action["content"])


def apply_payload(repo: Path, payload: dict) -> dict:
    title, message, actions = proposal_actions(repo, payload)
    apply_actions(repo, actions)
    return {"title": title, "message": message, "actions": len(actions)}


def cmd_update_task(args: argparse.Namespace) -> int:
    payload = {key: value for key, value in vars(args).items() if value not in (None, "")}
    payload["type"] = "update_task"
    result = apply_payload(repo_arg(args.repo), payload)
    print(json.dumps(result, indent=2))
    return 0


def cmd_add_event(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "add_event", "task_id": args.task_id, "actor": args.actor, "event_type": args.event_type, "message": args.message})
    print(json.dumps(result, indent=2))
    return 0


def cmd_submit_output(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "submit_output", "task_id": args.task_id, "actor": args.actor, "output": args.output, "message": args.message, "target_repo": args.target_repo, "output_commit": args.output_commit})
    print(json.dumps(result, indent=2))
    return 0


def cmd_review_task(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "review_task", "task_id": args.task_id, "reviewer": args.reviewer, "decision": args.decision, "notes": args.notes})
    print(json.dumps(result, indent=2))
    return 0


def cmd_record_attempt(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "record_attempt", "task_id": args.task_id, "actor": args.actor, "output": args.output, "message": args.message, "target_repo": args.target_repo, "output_commit": args.output_commit})
    print(json.dumps(result, indent=2))
    return 0


def cmd_record_verification_failed(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "record_verification_failed", "task_id": args.task_id, "reviewer": args.reviewer, "reason": args.reason, "output": args.output})
    print(json.dumps(result, indent=2))
    return 0


def cmd_withdraw_output(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "withdraw_output", "task_id": args.task_id, "actor": args.actor, "reason": args.reason, "output": args.output})
    print(json.dumps(result, indent=2))
    return 0


def cmd_supersede_output(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "supersede_output", "task_id": args.task_id, "actor": args.actor, "old_output": args.old_output, "new_output": args.new_output, "reason": args.reason})
    print(json.dumps(result, indent=2))
    return 0


def cmd_cancel_review(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "cancel_review", "task_id": args.task_id, "actor": args.actor, "reason": args.reason})
    print(json.dumps(result, indent=2))
    return 0


def cmd_register_repo(args: argparse.Namespace) -> int:
    result = apply_payload(
        repo_arg(args.repo),
        {
            "type": "register_repo",
            "project_id": args.project_id,
            "name": args.name,
            "provider": args.provider,
            "url": args.url,
            "default_branch": args.default_branch,
            "role": args.role,
        },
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_register_asset(args: argparse.Namespace) -> int:
    result = apply_payload(
        repo_arg(args.repo),
        {
            "type": "register_asset",
            "project_id": args.project_id,
            "title": args.title,
            "asset_type": args.asset_type,
            "storage": args.storage,
            "path": args.path,
            "source_url": args.source_url,
            "used_by": args.used_by,
            "owner": args.owner,
            "status": args.status,
        },
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    repo = repo_arg(args.repo)
    if registry_path(repo).exists() and not args.force:
        raise GitPMError(f"{registry_path(repo)} already exists; pass --force to refresh generated demo files")
    init_args = argparse.Namespace(
        repo=str(repo),
        name=args.name,
        owner=args.owner,
        provider=args.provider,
        github_repo=args.github_repo,
        gitlab_url=args.gitlab_url,
        gitlab_project=args.gitlab_project,
        git_init=args.git_init,
        force=args.force,
    )
    cmd_init(init_args)
    registry = load_registry(repo)
    project = registry["projects"]["PROJ1"]
    project["summary"] = "Demo game project showing daily workflows for design, art, engineering, production, and review."
    project["repos"] = [
        {"name": "game-client", "provider": "github", "url": "https://github.com/example/game-client", "default_branch": "main", "role": "client/gameplay"},
        {"name": "game-backend", "provider": "github", "url": "https://github.com/example/game-backend", "default_branch": "main", "role": "backend"},
        {"name": "web-portal", "provider": "github", "url": "https://github.com/example/web-portal", "default_branch": "main", "role": "frontend"},
    ]
    owner_email = email_from_actor(args.owner) or f"{slugify(args.owner).replace('-', '.')}@example.com"
    registry["people"] = [
        {"name": args.owner, "role": "Project Manager", "email": owner_email},
        {"name": "Gina", "role": "Game Designer", "email": "gina@example.com"},
        {"name": "Paul", "role": "Programmer", "email": "paul@example.com"},
        {"name": "Anika", "role": "Artist", "email": "anika@example.com"},
        {"name": "Tara", "role": "3D Artist", "email": "tara@example.com"},
        {"name": "Mo", "role": "Modeller", "email": "mo@example.com"},
        {"name": "Bao", "role": "Backend Engineer", "email": "bao@example.com"},
        {"name": "Fern", "role": "Frontend Engineer", "email": "fern@example.com"},
    ]
    write_text(repo / project["path"], dump(project))
    write_text(
        repo / project["readme"],
        markdown_doc(
            {"id": "PROJ1", "type": "project", "owner": args.owner, "status": project["status"]},
            f"PROJ1 - {project['name']}",
            """
## State

- Status: Active
- Current focus: playable vertical slice with instrumented onboarding.
- Next review: Friday playtest review.

## Repositories

- `game-client`: gameplay, UI, local tooling.
- `game-backend`: accounts, matchmaking, telemetry ingestion.
- `web-portal`: community page and playtest signup flow.

## Documents

Generated demo docs include design, engineering, art, mockup, playtest, and release-planning examples.

## Tasks

Use `git_pm.py update-task`, `submit-output`, `review-task`, and `register-asset` to simulate daily collaboration.
""",
        ),
    )
    for doc_type, title, owner in [
        ("game-design", "Core Loop Design", "Gina"),
        ("frontend-spec", "Playtest Signup Flow", "Fern"),
        ("backend-spec", "Telemetry Ingestion API", "Bao"),
        ("technical-spec", "Vertical Slice Architecture", "Paul"),
        ("3d-asset-brief", "Arena Props Blockout", "Tara"),
        ("asset-brief", "UI Icon Pass", "Anika"),
        ("mockup-review", "HUD Mockup Review", args.owner),
        ("playtest-report", "First Internal Playtest", args.owner),
    ]:
        doc_id = allocate_id(registry, "doc")
        rel, text, ref = make_doc(doc_id, project, doc_type, title, owner)
        registry.setdefault("docs", {})[doc_id] = ref
        write_text(repo / rel, text)
    task_specs = [
        ("Finalize core loop tuning questions", "Gina", "Game Designer", "Game Design", "game-client"),
        ("Implement player ability prototype", "Paul", "Programmer", "Pull Request", "game-client"),
        ("Paint first-pass HUD icons", "Anika", "Artist", "Asset", ""),
        ("Block out arena prop kit", "Tara", "3D Artist", "Asset", ""),
        ("Retopology pass for arena props", "Mo", "Modeller", "Asset", ""),
        ("Add telemetry ingestion endpoint", "Bao", "Backend Engineer", "Pull Request", "game-backend"),
        ("Build playtest signup page", "Fern", "Frontend Engineer", "Pull Request", "web-portal"),
        ("Prepare Friday playtest checklist", args.owner, "Project Manager", "Playtest Plan", ""),
    ]
    created_tasks: list[str] = []
    for title, assignee, role, output, target_repo in task_specs:
        task_id, path, task = create_task_payload(registry, "PROJ1", title, assignee, role, output)
        task["target_repo"] = target_repo
        task["acceptance_criteria"] = [f"{output} is linked in task output", "Task has a current user_update"]
        sync_task_ref(registry, task_id, path, task)
        write_text(repo / path, dump(task))
        for rel, text in task_support_files(path, task).items():
            write_text(repo / rel, text)
        created_tasks.append(task_id)
    save_registry(repo, registry)
    apply_payload(repo, {"type": "register_asset", "project_id": "PROJ1", "title": "HUD mockup v1", "asset_type": "mockup", "storage": "external-link", "source_url": "https://example.com/figma/hud-v1", "used_by": "PROJ1,TASK7", "owner": "Fern", "status": "review"})
    apply_payload(repo, {"type": "register_asset", "project_id": "PROJ1", "title": "Arena prop blockout", "asset_type": "3d-model", "storage": "external-link", "source_url": "https://example.com/assets/arena-props-blockout.glb", "used_by": "PROJ1,TASK4,TASK5", "owner": "Tara", "status": "draft"})
    apply_payload(repo, {"type": "update_task", "task_id": created_tasks[0], "actor": "Gina", "status": "In Progress", "user_update": "Reviewing playtest clips and tightening core loop questions."})
    apply_payload(repo, {"type": "submit_output", "task_id": created_tasks[1], "actor": "Paul", "output": "https://github.com/example/game-client/pull/42", "message": "Ability prototype ready for review."})
    apply_payload(repo, {"type": "review_task", "task_id": created_tasks[1], "reviewer": args.owner, "decision": "changes_requested", "notes": "Prototype works, but needs tuning notes linked from the design doc."})
    print(json.dumps({"ok": True, "repo": str(repo), "project": "PROJ1", "tasks": len(task_specs) + 1, "scenario": args.scenario}, indent=2))
    return 0


def proposal_actions(repo: Path, payload: dict) -> tuple[str, str, list[dict]]:
    change_type = payload.get("type")
    title = payload.get("title") or payload.get("message") or change_type or "Project change"
    message = payload.get("message") or title
    if change_type == "edit_file":
        rel = payload.get("path", "").replace("\\", "/").lstrip("/")
        if not rel:
            raise GitPMError("edit_file requires path")
        full = safe_repo_path(repo, rel)
        ensure_edit_allowed(load_registry(repo), rel, payload)
        base_sha = payload.get("base_sha256") or payload.get("base_sha")
        if base_sha and full.exists() and file_sha256(full) != base_sha:
            raise GitPMError(f"stale edit for {rel}: base_sha256 does not match current file")
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
            payload.get("target_repo", ""),
        )
        title = f"Create {task_id}: {payload.get('title', '')}"
        actions = [
            {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
            {"action": "create", "file_path": path, "content": dump(task)},
        ]
        for rel, text in task_support_files(path, task).items():
            actions.append({"action": "create", "file_path": rel, "content": text})
        return title, title, actions
    if change_type == "create_milestone":
        registry = load_registry(repo)
        project = registry.get("projects", {}).get(payload.get("project_id", ""))
        if not project:
            raise GitPMError(f"missing project {payload.get('project_id')}")
        milestone_id = allocate_id(registry, "milestone")
        path, milestone, ref = make_milestone(milestone_id, payload.get("project_id", ""), project["name"], payload.get("title", ""), payload.get("owner", ""), payload.get("status", "Planned"))
        registry.setdefault("milestones", {})[milestone_id] = ref
        project.setdefault("milestones", []).append(milestone_id)
        actions = [
            {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
            {"action": "update", "file_path": project["path"], "content": dump(project)},
            {"action": "create", "file_path": path, "content": dump(milestone)},
        ]
        roadmap_path = project.get("roadmap", "")
        if roadmap_path:
            roadmap = read_json_subset(safe_repo_path(repo, roadmap_path), default_roadmap(project))
            roadmap.setdefault("milestones", []).append(milestone_id)
            actions.append({"action": "update", "file_path": roadmap_path, "content": dump(roadmap)})
        title = f"Create {milestone_id}: {payload.get('title', '')}"
        return title, title, actions
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
    if change_type == "propose_feature":
        registry = load_registry(repo)
        return propose_feature_actions(repo, registry, payload)
    if change_type == "update_task":
        registry = load_registry(repo)
        return update_task_actions(repo, registry, payload)
    if change_type == "add_event":
        registry = load_registry(repo)
        task_id = payload.get("task_id", "")
        _path, task = load_task_record(repo, registry, task_id)
        record = make_event(registry, task, payload.get("actor", ""), payload.get("event_type", "update"), payload.get("message", ""))
        title = f"Add event to {task_id}"
        return title, record["message"], [{"action": "update", "file_path": "registry.yaml", "content": dump(registry)}, event_action(repo, record)]
    if change_type == "submit_output":
        registry = load_registry(repo)
        return submit_output_actions(repo, registry, payload)
    if change_type == "review_task":
        registry = load_registry(repo)
        return review_task_actions(repo, registry, payload)
    if change_type == "record_attempt":
        registry = load_registry(repo)
        return record_attempt_actions(repo, registry, payload)
    if change_type == "record_verification_failed":
        registry = load_registry(repo)
        return record_verification_failed_actions(repo, registry, payload)
    if change_type == "withdraw_output":
        registry = load_registry(repo)
        return withdraw_output_actions(repo, registry, payload)
    if change_type == "supersede_output":
        registry = load_registry(repo)
        return supersede_output_actions(repo, registry, payload)
    if change_type == "cancel_review":
        registry = load_registry(repo)
        return cancel_review_actions(repo, registry, payload)
    if change_type == "register_repo":
        registry = load_registry(repo)
        return register_repo_actions(repo, registry, payload)
    if change_type == "register_asset":
        registry = load_registry(repo)
        return register_asset_actions(repo, registry, payload)
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
        target = (STATIC_DIR / path[len("/static/") :]).resolve()
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

    p = sub.add_parser("my-tasks")
    add_common_repo(p)
    p.add_argument("--user", required=True)
    p.add_argument("--include-done", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_my_tasks)

    p = sub.add_parser("project-status")
    add_common_repo(p)
    p.add_argument("--project-id", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_project_status)

    p = sub.add_parser("review-queue")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_review_queue)

    p = sub.add_parser("blocked-tasks")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_blocked_tasks)

    p = sub.add_parser("stale-work")
    add_common_repo(p)
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stale_work)

    p = sub.add_parser("audit-docs")
    add_common_repo(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit_docs)

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
    p.add_argument("--assigned-to", default="")
    p.add_argument("--role", default="")
    p.add_argument("--expected-output", required=True)
    p.add_argument("--target-repo", default="")
    p.set_defaults(func=cmd_create_task)

    p = sub.add_parser("create-milestone")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--status", choices=sorted(MILESTONE_STATUSES), default="Planned")
    p.set_defaults(func=cmd_create_milestone)

    p = sub.add_parser("create-doc")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--doc-type", default="proposal")
    p.set_defaults(func=cmd_create_doc)

    p = sub.add_parser("propose-feature")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--problem", default="")
    p.add_argument("--value", default="")
    p.add_argument("--scope", default="")
    p.add_argument("--non-goals", default="")
    p.add_argument("--risks", default="")
    p.add_argument("--task-breakdown", default="")
    p.add_argument("--decision-needed", default="")
    p.set_defaults(func=cmd_propose_feature)

    p = sub.add_parser("update-task")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", default="")
    p.add_argument("--status", choices=sorted(TASK_STATUSES), default="")
    p.add_argument("--checkpoint", choices=sorted(CHECKPOINTS), default="")
    p.add_argument("--priority", default="")
    p.add_argument("--assigned-to", default="")
    p.add_argument("--deadline", default="")
    p.add_argument("--milestone", default="")
    p.add_argument("--feature-area", default="")
    p.add_argument("--release-target", default="")
    p.add_argument("--estimate", default="")
    p.add_argument("--risk", default="")
    p.add_argument("--reviewer", default="")
    p.add_argument("--expected-output", default="")
    p.add_argument("--acceptance-criteria", default="")
    p.add_argument("--dependencies", default="")
    p.add_argument("--target-repo", default="")
    p.add_argument("--output", default="")
    p.add_argument("--output-commit", default="")
    p.add_argument("--blocker", default="")
    p.add_argument("--ai-update", default="")
    p.add_argument("--user-update", default="")
    p.add_argument("--event-message", default="")
    p.set_defaults(func=cmd_update_task)

    p = sub.add_parser("add-event")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--event-type", default="update")
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_add_event)

    p = sub.add_parser("submit-output")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--target-repo", default="")
    p.add_argument("--output-commit", default="")
    p.add_argument("--message", default="")
    p.set_defaults(func=cmd_submit_output)

    p = sub.add_parser("review-task")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--decision", choices=sorted(REVIEW_DECISIONS), required=True)
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_review_task)

    p = sub.add_parser("record-attempt")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--target-repo", default="")
    p.add_argument("--output-commit", default="")
    p.add_argument("--message", default="")
    p.set_defaults(func=cmd_record_attempt)

    p = sub.add_parser("record-verification-failed")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--output", default="")
    p.set_defaults(func=cmd_record_verification_failed)

    p = sub.add_parser("withdraw-output")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--output", default="")
    p.set_defaults(func=cmd_withdraw_output)

    p = sub.add_parser("supersede-output")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--new-output", required=True)
    p.add_argument("--old-output", default="")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_supersede_output)

    p = sub.add_parser("cancel-review")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_cancel_review)

    p = sub.add_parser("register-repo")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--provider", default="github", choices=["github", "gitlab", "other"])
    p.add_argument("--url", required=True)
    p.add_argument("--default-branch", default="main")
    p.add_argument("--role", default="")
    p.set_defaults(func=cmd_register_repo)

    p = sub.add_parser("register-asset")
    add_common_repo(p)
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--asset-type", default="asset")
    p.add_argument("--storage", default="external-link")
    p.add_argument("--path", default="")
    p.add_argument("--source-url", default="")
    p.add_argument("--used-by", default="")
    p.add_argument("--owner", required=True)
    p.add_argument("--status", default="draft")
    p.set_defaults(func=cmd_register_asset)

    p = sub.add_parser("demo")
    add_common_repo(p)
    p.add_argument("--scenario", default="game", choices=["game"])
    p.add_argument("--name", default="Demo Game Hub")
    p.add_argument("--owner", default="Maya")
    p.add_argument("--provider", default=os.environ.get("GPM_PROVIDER", "github"), choices=["github", "gitlab"])
    p.add_argument("--github-repo", default=os.environ.get("GPM_GITHUB_REPO", ""))
    p.add_argument("--gitlab-url", default=os.environ.get("GPM_GITLAB_URL", ""))
    p.add_argument("--gitlab-project", default=os.environ.get("GPM_GITLAB_PROJECT", ""))
    p.add_argument("--git-init", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_demo)

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
