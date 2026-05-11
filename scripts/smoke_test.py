#!/usr/bin/env python3
"""End-to-end smoke test for the GitLab Project OS skill."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib import request


SCRIPT = Path(__file__).resolve().with_name("project_os.py")


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def http_json(url: str, body: dict | None = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers)
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    root = (Path.cwd() / ".project-os-smoke").resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "demo-os"
    server = None
    try:
        run(["init", "--repo", str(repo), "--name", "Demo Project OS", "--owner", "Terence"])
        validate = run(["validate", "--repo", str(repo), "--json"])
        issues = json.loads(validate.stdout)["issues"]
        errors = [item for item in issues if item["level"] == "error"]
        if errors:
            raise RuntimeError(f"validation errors: {errors}")
        run(["compile", "--repo", str(repo)])
        port = 8797
        server = subprocess.Popen(
            [sys.executable, str(SCRIPT), "website", "--repo", str(repo), "--port", str(port)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                health = http_json(base + "/healthz")
                if health.get("ok"):
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
                "ew_id": "EW1",
                "title": "Smoke-test proposed task",
                "assigned_to": "Terence",
                "role": "PM",
                "expected_output": "Setup Confirmation",
            },
        )
        proposal_dir = Path(proposal.get("proposal_dir", ""))
        if not proposal_dir.exists():
            raise RuntimeError(f"proposal directory was not created: {proposal}")
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
