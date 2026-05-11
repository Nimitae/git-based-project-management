#!/usr/bin/env python3
"""Smoke test the deployable Node.js website runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib import request


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = SKILL_ROOT / "scripts" / "project_os.py"
WEBSITE_DIR = SKILL_ROOT / "assets" / "website"


def find_node() -> str:
    env_node = os.environ.get("NODE")
    if env_node:
        return env_node
    node = shutil.which("node")
    if node:
        return node
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
    if bundled.exists():
        return str(bundled)
    raise RuntimeError("Node.js not found. Set NODE to the node executable.")


def run(args: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, env=env)
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
    node = find_node()
    root = (Path.cwd() / ".project-os-node-smoke").resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "demo-os"
    server = None
    try:
        run([sys.executable, str(CONTROLLER), "init", "--repo", str(repo), "--name", "Node Demo OS", "--owner", "Terence"])
        run([sys.executable, str(CONTROLLER), "validate", "--repo", str(repo)])
        env = os.environ.copy()
        env["PROJECT_OS_REPO"] = str(repo)
        env["HOST"] = "127.0.0.1"
        env["PORT"] = "8798"
        server = subprocess.Popen(
            [node, "server.mjs"],
            cwd=str(WEBSITE_DIR),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        base = "http://127.0.0.1:8798"
        for _ in range(50):
            try:
                health = http_json(base + "/healthz")
                if health.get("ok") and health.get("runtime") == "node":
                    break
            except Exception:
                time.sleep(0.2)
        else:
            out, err = server.communicate(timeout=1) if server.poll() is not None else ("", "")
            raise RuntimeError(f"Node website did not become ready\nOUT={out}\nERR={err}")
        data = http_json(base + "/api/data")
        if not data.get("tasks"):
            raise RuntimeError("Node website returned no tasks")
        proposal = http_json(
            base + "/api/proposals",
            {
                "type": "create_task",
                "ew_id": "EW1",
                "title": "Node smoke-test proposed task",
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
            raise RuntimeError("Node website HTML did not include dashboard")
        print(json.dumps({"ok": True, "runtime": "node", "repo": str(repo), "proposal_dir": str(proposal_dir), "tasks": len(data["tasks"])}, indent=2))
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
