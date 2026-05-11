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
DOC_TYPES = {
    "proposal",
    "brief",
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


def file_sha256(path: Path) -> str:
    if not path.exists() or path.is_dir():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "next_ids": {"project": 2, "task": 2, "doc": 2, "asset": 1, "event": 1, "review": 1, "milestone": 1},
        "people": [{"name": owner, "role": "Owner", "email": ""}],
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
- Daily execution updates should use task events or task-local notes.
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
""",
    )
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
    return files


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


def default_definition_of_ready_policy() -> dict:
    return {
        "schema_version": 1,
        "ready_task_requires": ["assigned_to", "expected_output", "acceptance_criteria"],
        "ready_task_recommends": ["target_repo", "milestone", "reviewer"],
        "ready_doc_requires": ["owner", "status", "required_sections"],
    }


def default_definition_of_done_policy() -> dict:
    return {
        "schema_version": 1,
        "done_requires": ["output", "acceptance_criteria", "approved_review"],
        "verified_requires": ["output", "acceptance_criteria", "approved_review"],
        "objective_failures_block_merge": True,
        "subjective_failures_create_review": True,
    }


def default_review_gates_policy() -> dict:
    return {
        "schema_version": 1,
        "submit_output_status": "In Review",
        "approved_review_status": "Verified",
        "changes_requested_status": "In Progress",
        "reject_done_without_output": True,
        "reject_done_without_approved_review": True,
        "reject_verified_without_approved_review": True,
        "allow_failed_subjective_review_history": True,
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
- If output cannot be accessed or parsed, reject the PR/MR instead of merging an invalid completed state.
"""


def agent_operating_rules_doc() -> str:
    return """# Agent Operating Rules

Agents should:

- Pull latest Git state before reading tasks or docs.
- Read the project README, roadmap, task folder, linked docs, and linked implementation repos before changing work.
- Use controller commands for IDs, task updates, docs, assets, events, reviews, and milestones.
- Prefer `In Review` plus a submitted output over directly marking work `Done`.
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

Every task should have an owner, status, expected output, acceptance criteria, and an output link before it can be verified.

Use one folder per task:

- `task.yaml`: durable state and acceptance criteria.
- `notes.md`: task-local working context.
- `outputs.md`: submitted output and verification notes.
- `attachments/`: small task-local references only.

Use `events/task-events.jsonl` for daily notes and handoffs. Use task YAML for durable task state.

Submitted work should move to `In Review`. Do not mark work `Done` or `Verified` unless it has an output link and an approved review record. If the output cannot be objectively accessed or checked, reject the PR/MR rather than merging an invalid completed state. The failed check or review comment is the footprint.

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
        plain = re.sub(r"\s+", " ", re.sub(r"`([^`]*)`", r"\1", body)).strip()
        docs.append(
            {
                "id": doc_id,
                "project_id": row.get("project_id", ""),
                "type": row.get("doc_type") or frontmatter.get("type", ""),
                "title": markdown_title(body, row.get("title", doc_id)),
                "path": row.get("path", ""),
                "owner": row.get("owner", ""),
                "status": row.get("status", ""),
                "sha256": file_sha256(path),
                "headings": headings,
                "snippet": plain[:280],
                "search_text": plain[:12000],
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
    return rows


def compile_data(repo: Path) -> dict:
    registry = load_registry(repo)
    issues = validate_repo(repo)
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
        "docs": collect_docs(repo, registry),
        "tasks": collect_tasks(repo, registry),
        "assets": [{"id": key, **value} for key, value in registry.get("assets", {}).items()],
        "people": registry.get("people", []),
        "events": read_jsonl(repo / "events/task-events.jsonl"),
        "reviews": read_jsonl(repo / "reviews/task-reviews.jsonl"),
        "validation": {"issues": issues},
    }
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


def live_document_paths(registry: dict) -> list[str]:
    paths = [
        "README.md",
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
    }


def make_event(registry: dict, task: dict, actor: str, event_type: str, message: str) -> dict:
    event_id = allocate_id(registry, "event")
    return {
        "id": event_id,
        "task_id": task.get("id", ""),
        "project_id": task.get("project_id", ""),
        "actor": actor or "Unknown",
        "event_type": event_type or "update",
        "message": message or "",
        "created_at": now_iso(),
    }


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
    for field in ["status", "checkpoint", "priority", "assigned_to", "deadline", "milestone", "feature_area", "release_target", "estimate", "risk", "reviewer", "expected_output", "target_repo", "output", "blocker", "ai_update", "user_update"]:
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
    payload = {**payload, "status": payload.get("status") or "In Review", "checkpoint": payload.get("checkpoint") or "Review", "suppress_event": True}
    title, _message, actions = update_task_actions(repo, registry, payload)
    task_id = payload.get("task_id", "")
    _path, task = load_task_record(repo, registry, task_id)
    event = make_event(registry, task, payload.get("actor", ""), "submitted_output", payload.get("message") or payload.get("output") or f"Submitted output for {task_id}")
    actions[0]["content"] = dump(registry)
    actions.append(event_action(repo, event))
    return title.replace("Update", "Submit output for", 1), event["message"], actions


def review_task_actions(repo: Path, registry: dict, payload: dict) -> tuple[str, str, list[dict]]:
    task_id = payload.get("task_id", "")
    path, task = load_task_record(repo, registry, task_id)
    decision = payload.get("decision", "changes_requested")
    if decision == "approved":
        task["status"] = "Verified"
        task["checkpoint"] = "Ready"
    elif decision in {"changes_requested", "rejected"}:
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
    event = make_event(registry, task, payload.get("reviewer", ""), f"review_{decision}", payload.get("notes", "") or f"{decision} review for {task_id}")
    title = f"Review {task_id}: {decision}"
    return title, event["message"], [
        {"action": "update", "file_path": "registry.yaml", "content": dump(registry)},
        {"action": "update", "file_path": path, "content": dump(task)},
        review_action(repo, review),
        event_action(repo, event),
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
    result = apply_payload(repo_arg(args.repo), {"type": "submit_output", "task_id": args.task_id, "actor": args.actor, "output": args.output, "message": args.message})
    print(json.dumps(result, indent=2))
    return 0


def cmd_review_task(args: argparse.Namespace) -> int:
    result = apply_payload(repo_arg(args.repo), {"type": "review_task", "task_id": args.task_id, "reviewer": args.reviewer, "decision": args.decision, "notes": args.notes})
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
    registry["people"] = [
        {"name": args.owner, "role": "Project Manager", "email": ""},
        {"name": "Gina", "role": "Game Designer", "email": ""},
        {"name": "Paul", "role": "Programmer", "email": ""},
        {"name": "Anika", "role": "Artist", "email": ""},
        {"name": "Tara", "role": "3D Artist", "email": ""},
        {"name": "Mo", "role": "Modeller", "email": ""},
        {"name": "Bao", "role": "Backend Engineer", "email": ""},
        {"name": "Fern", "role": "Frontend Engineer", "email": ""},
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
    p.add_argument("--assigned-to", required=True)
    p.add_argument("--role", default="")
    p.add_argument("--expected-output", required=True)
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
    p.add_argument("--message", default="")
    p.set_defaults(func=cmd_submit_output)

    p = sub.add_parser("review-task")
    add_common_repo(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--decision", choices=["approved", "changes_requested", "rejected"], required=True)
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_review_task)

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
