#!/usr/bin/env python3
"""End-to-end smoke test for the Git-based project management skill."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib import error, request


SCRIPT = Path(__file__).resolve().with_name("git_pm.py")


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def run_expect_fail(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)
    if result.returncode == 0:
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(args)}\nSTDOUT:\n{result.stdout}")
    return result


def http_json(url: str, body: dict | None = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="gpm-smoke-")).resolve()
    repo = root / "demo-hub"
    server = None
    try:
        run(["init", "--repo", str(repo), "--name", "Demo Project Hub", "--owner", "Terence"])
        run(["update-task", "--repo", str(repo), "--task-id", "TASK1", "--actor", "Terence", "--status", "In Progress", "--user-update", "Smoke test update"])
        run(["submit-output", "--repo", str(repo), "--task-id", "TASK1", "--actor", "Terence", "--output", "https://example.com/output", "--message", "Smoke output"])
        in_review = json.loads((repo / "projects" / "PROJ1-demo-project-hub" / "tasks" / "TASK1" / "task.yaml").read_text(encoding="utf-8"))
        if in_review.get("status") != "In Review":
            raise RuntimeError(f"submit-output should move TASK1 to In Review: {in_review.get('status')}")
        run(["review-task", "--repo", str(repo), "--task-id", "TASK1", "--reviewer", "Terence", "--decision", "approved", "--notes", "Smoke review"])
        historical = run_expect_fail(["update-task", "--repo", str(repo), "--task-id", "TASK1", "--actor", "Terence", "--status", "In Progress", "--user-update", "Should be blocked"])
        if "historical" not in (historical.stderr + historical.stdout).lower():
            raise RuntimeError(f"historical update guard did not explain the failure:\n{historical.stderr}")
        run(["create-milestone", "--repo", str(repo), "--project-id", "PROJ1", "--title", "Smoke milestone", "--owner", "Terence"])
        run(["create-task", "--repo", str(repo), "--project-id", "PROJ1", "--title", "Smoke editable task", "--assigned-to", "Terence", "--role", "PM", "--expected-output", "Setup Confirmation"])
        if not (repo / "projects" / "PROJ1-demo-project-hub" / "tasks" / "TASK2" / "notes.md").exists():
            raise RuntimeError("task folder notes.md was not created")
        run(["register-asset", "--repo", str(repo), "--project-id", "PROJ1", "--title", "Smoke mockup", "--asset-type", "mockup", "--source-url", "https://example.com/mockup", "--used-by", "PROJ1,TASK1", "--owner", "Terence"])
        validate = run(["validate", "--repo", str(repo), "--json"])
        issues = json.loads(validate.stdout)["issues"]
        errors = [item for item in issues if item["level"] == "error"]
        if errors:
            raise RuntimeError(f"validation errors: {errors}")
        run(["audit-docs", "--repo", str(repo)])
        run(["compile", "--repo", str(repo)])
        if not (repo / ".project-hub" / "site-data" / "search-index.json").exists():
            raise RuntimeError("search index was not generated")
        port = free_port()
        env = os.environ.copy()
        for key in ["GPM_LIVE_PROPOSALS", "GPM_PROVIDER", "GPM_GITHUB_REPO", "GPM_GITHUB_TOKEN", "GPM_GITLAB_PROJECT", "GPM_GITLAB_TOKEN"]:
            env.pop(key, None)
        server = subprocess.Popen(
            [sys.executable, str(SCRIPT), "website", "--repo", str(repo), "--port", str(port)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                health = http_json(base + "/healthz")
                if health.get("ok") and Path(health.get("repo", "")).resolve() == repo:
                    break
            except Exception:
                time.sleep(0.15)
        else:
            raise RuntimeError("website did not become ready")
        data = http_json(base + "/api/data")
        if not data.get("tasks"):
            raise RuntimeError("website API returned no tasks")
        proposal = http_json(
            base + "/api/proposals",
            {
                "type": "create_task",
                "project_id": "PROJ1",
                "title": "Smoke-test proposed task",
                "assigned_to": "Terence",
                "role": "PM",
                "expected_output": "Setup Confirmation",
            },
        )
        update_proposal = http_json(
            base + "/api/proposals",
            {
                "type": "update_task",
                "task_id": "TASK2",
                "actor": "Terence",
                "status": "In Progress",
                "user_update": "Website smoke update",
            },
        )
        proposal_dir = Path(proposal.get("proposal_dir", ""))
        if not proposal_dir.exists():
            raise RuntimeError(f"proposal directory was not created: {proposal}")
        if not Path(update_proposal.get("proposal_dir", "")).exists():
            raise RuntimeError(f"update proposal directory was not created: {update_proposal}")
        with request.urlopen(base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        if "Project Workspace" not in html:
            raise RuntimeError("website HTML did not include dashboard")
        print(json.dumps({"ok": True, "repo": str(repo), "proposal_dir": str(proposal_dir), "tasks": len(data["tasks"])}, indent=2))
        return 0
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        if "--keep" not in sys.argv:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
