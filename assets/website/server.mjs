import { createServer } from "node:http";
import { readFile, writeFile, mkdir, access } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = path.resolve(process.env.PROJECT_OS_STATIC_DIR || path.join(__dirname, "static"));
const REPO = path.resolve(process.env.PROJECT_OS_REPO || process.cwd());
const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 8787);

const TASK_STATUSES = new Set(["Backlog", "In Progress", "Blocked", "Done", "Verified", "Iceboxed"]);
const CHECKPOINTS = new Set(["", "Drafting", "Pending Approval", "Revising", "Ready"]);
const ID_PREFIX = {
  initiative: "INIT",
  project: "PROJ",
  ew: "EW",
  task: "TASK",
  event: "EVENT"
};

function nowIso() {
  const now = new Date();
  const offsetMs = 8 * 60 * 60 * 1000;
  const sg = new Date(now.getTime() + offsetMs);
  return `${sg.toISOString().replace("Z", "")}+08:00`;
}

function slugify(value) {
  return String(value || "change").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "change";
}

function safeRepoPath(relPath) {
  const clean = String(relPath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  const full = path.resolve(REPO, clean);
  if (full !== REPO && !full.startsWith(REPO + path.sep)) {
    throw new Error(`path escapes repo: ${relPath}`);
  }
  return full;
}

function safeStaticPath(relPath) {
  const clean = String(relPath || "index.html").replaceAll("\\", "/").replace(/^\/+/, "");
  const full = path.resolve(STATIC_DIR, clean);
  if (full !== STATIC_DIR && !full.startsWith(STATIC_DIR + path.sep)) {
    throw new Error(`path escapes static dir: ${relPath}`);
  }
  return full;
}

async function readText(filePath, fallback = "") {
  try {
    return await readFile(filePath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return fallback;
    throw error;
  }
}

async function readJsonSubset(filePath, fallback = null) {
  const text = (await readText(filePath, "")).trim();
  if (!text) return structuredClone(fallback);
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${filePath} must use JSON-subset YAML: ${error.message}`);
  }
}

function dump(data) {
  return JSON.stringify(data, null, 2) + "\n";
}

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function parseFrontmatter(text) {
  if (!text.startsWith("---\n")) return [{}, text];
  const end = text.indexOf("\n---", 4);
  if (end === -1) return [{}, text];
  const raw = text.slice(4, end).trim();
  const body = text.slice(end + 4).replace(/^\n+/, "");
  const data = {};
  for (const line of raw.split(/\r?\n/)) {
    const index = line.indexOf(":");
    if (index === -1) continue;
    data[line.slice(0, index).trim()] = line.slice(index + 1).trim().replace(/^"|"$/g, "");
  }
  return [data, body];
}

function markdownTitle(text, fallback) {
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("# ")) return line.slice(2).trim();
  }
  return fallback;
}

async function loadRegistry() {
  return readJsonSubset(path.join(REPO, "registry.yaml"), {});
}

function maxSuffix(ids, prefix) {
  let max = 0;
  const matcher = new RegExp(`^${prefix}(\\d+)$`);
  for (const id of ids) {
    const match = matcher.exec(id);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return max;
}

function allocateId(registry, kind) {
  const prefix = ID_PREFIX[kind];
  const section = kind === "project" ? "projects" : kind === "initiative" ? "initiatives" : kind === "ew" ? "ews" : kind === "task" ? "tasks" : null;
  const existing = section ? Object.keys(registry.entities?.[section] || {}) : [];
  registry.next_ids ||= {};
  let number = Number(registry.next_ids[kind] || 1);
  while (existing.includes(`${prefix}${number}`)) number += 1;
  registry.next_ids[kind] = number + 1;
  return `${prefix}${number}`;
}

async function validateRepo(registry) {
  const issues = [];
  const entities = registry.entities || {};
  for (const section of ["initiatives", "projects", "ews", "tasks"]) {
    if (!entities[section] || typeof entities[section] !== "object") {
      issues.push({ level: "error", code: "REGISTRY_SECTION", message: `entities.${section} must exist`, path: "registry.yaml" });
    }
  }
  const kinds = [
    ["initiative", "initiatives"],
    ["project", "projects"],
    ["ew", "ews"],
    ["task", "tasks"]
  ];
  for (const [kind, section] of kinds) {
    const prefix = ID_PREFIX[kind];
    const rows = entities[section] || {};
    const expectedMin = maxSuffix(Object.keys(rows), prefix) + 1;
    if (Number(registry.next_ids?.[kind] || 1) < expectedMin) {
      issues.push({ level: "error", code: "NEXT_ID_STALE", message: `next_ids.${kind} should be at least ${expectedMin}`, path: "registry.yaml" });
    }
    for (const [id, row] of Object.entries(rows)) {
      if (!new RegExp(`^${prefix}\\d+$`).test(id)) {
        issues.push({ level: "error", code: "ID_FORMAT", message: `${id} should match ${prefix}#`, path: "registry.yaml" });
      }
      if (!row.path) {
        issues.push({ level: "error", code: "PATH_MISSING", message: `${id} has no path`, path: "registry.yaml" });
      } else if (!(await fileExists(safeRepoPath(row.path)))) {
        issues.push({ level: "error", code: "PATH_MISSING", message: `${id} path does not exist`, path: row.path });
      }
    }
  }
  for (const [projectId, project] of Object.entries(entities.projects || {})) {
    if (!entities.initiatives?.[project.initiative_id]) {
      issues.push({ level: "error", code: "REL_PROJECT_INITIATIVE", message: `${projectId} references missing ${project.initiative_id}`, path: project.path || "" });
    }
  }
  for (const [ewId, ew] of Object.entries(entities.ews || {})) {
    const project = entities.projects?.[ew.project_id];
    if (!project) {
      issues.push({ level: "error", code: "REL_EW_PROJECT", message: `${ewId} references missing ${ew.project_id}`, path: ew.path || "" });
    } else if (ew.initiative_id && ew.initiative_id !== project.initiative_id) {
      issues.push({ level: "error", code: "REL_EW_INITIATIVE", message: `${ewId} initiative does not match parent project`, path: ew.path || "" });
    }
  }
  for (const [taskId, ref] of Object.entries(entities.tasks || {})) {
    let task = {};
    try {
      task = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch (error) {
      issues.push({ level: "error", code: "TASK_PARSE", message: error.message, path: ref.path || "" });
      continue;
    }
    if (task.id !== taskId) {
      issues.push({ level: "error", code: "TASK_ID_MISMATCH", message: `${taskId} file id is ${task.id}`, path: ref.path || "" });
    }
    const ewId = task.ew_id || ref.ew_id;
    if (!entities.ews?.[ewId]) {
      issues.push({ level: "error", code: "REL_TASK_EW", message: `${taskId} references missing ${ewId}`, path: ref.path || "" });
    }
    if (task.status && !TASK_STATUSES.has(task.status)) {
      issues.push({ level: "error", code: "TASK_STATUS", message: `${taskId} has invalid status ${task.status}`, path: ref.path || "" });
    }
    if (!CHECKPOINTS.has(task.checkpoint || "")) {
      issues.push({ level: "warn", code: "TASK_CHECKPOINT", message: `${taskId} has unusual checkpoint ${task.checkpoint}`, path: ref.path || "" });
    }
    if (!task.assigned_to) {
      issues.push({ level: "warn", code: "TASK_ASSIGNEE_MISSING", message: `${taskId} has no assignee`, path: ref.path || "" });
    }
    if (!["Iceboxed", "Verified"].includes(task.status) && !task.expected_output) {
      issues.push({ level: "warn", code: "TASK_EXPECTED_OUTPUT_MISSING", message: `${taskId} has no expected_output`, path: ref.path || "" });
    }
    for (const dep of task.dependencies || []) {
      if (!entities.tasks?.[dep]) {
        issues.push({ level: "error", code: "REL_TASK_DEPENDENCY", message: `${taskId} depends on missing ${dep}`, path: ref.path || "" });
      }
    }
  }
  return issues;
}

async function collectDocs(registry) {
  const docs = [];
  for (const section of ["initiatives", "projects", "ews"]) {
    for (const [id, row] of Object.entries(registry.entities?.[section] || {})) {
      const text = await readText(safeRepoPath(row.path), "");
      const [frontmatter, body] = parseFrontmatter(text);
      docs.push({
        id,
        type: frontmatter.type || section.replace(/s$/, ""),
        title: markdownTitle(body, row.name || id),
        path: row.path,
        owner: row.owner || "",
        status: row.status || ""
      });
    }
  }
  return docs;
}

async function collectTasks(registry) {
  const tasks = [];
  const projects = registry.entities?.projects || {};
  const ews = registry.entities?.ews || {};
  for (const [taskId, ref] of Object.entries(registry.entities?.tasks || {})) {
    let task = {};
    try {
      task = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch {
      task = { id: taskId, title: ref.title || "", status: "Invalid" };
    }
    const ew = ews[task.ew_id || ref.ew_id] || {};
    const project = projects[task.project_id || ref.project_id || ew.project_id] || {};
    tasks.push({
      ...ref,
      ...task,
      id: taskId,
      path: ref.path,
      ew_name: ew.name || "",
      project_name: project.name || ""
    });
  }
  return tasks;
}

async function readJsonl(relPath) {
  const text = await readText(path.join(REPO, relPath), "");
  return text.split(/\r?\n/).filter(Boolean).map((line) => {
    try {
      return JSON.parse(line);
    } catch {
      return { error: `invalid jsonl in ${relPath}`, raw: line };
    }
  });
}

async function compileData() {
  const registry = await loadRegistry();
  const issues = await validateRepo(registry);
  return {
    schema_version: registry.schema_version || 1,
    repo_name: registry.name || path.basename(REPO),
    repo_path: REPO,
    provider: registry.provider || "",
    github_repo: registry.github?.repo || "",
    gitlab_url: registry.gitlab?.url || "",
    gitlab_project: registry.gitlab?.project_path || "",
    git_commit: "",
    generated_at: nowIso(),
    projects: Object.entries(registry.entities?.projects || {}).map(([id, value]) => ({ id, ...value })),
    ews: Object.entries(registry.entities?.ews || {}).map(([id, value]) => ({ id, ...value })),
    tasks: await collectTasks(registry),
    docs: await collectDocs(registry),
    people: registry.people || [],
    events: await readJsonl("events/task-events.jsonl"),
    reviews: await readJsonl("reviews/task-reviews.jsonl"),
    validation: { issues }
  };
}

function createTaskPayload(registry, payload) {
  const ew = registry.entities?.ews?.[payload.ew_id];
  if (!ew) throw new Error(`missing EW ${payload.ew_id}`);
  const taskId = allocateId(registry, "task");
  const projectId = ew.project_id;
  const taskPath = `projects/${projectId}/tasks/${taskId}.yaml`;
  const task = {
    id: taskId,
    ew_id: payload.ew_id,
    project_id: projectId,
    title: payload.title || "",
    assigned_to: payload.assigned_to || "",
    role: payload.role || "",
    status: "Backlog",
    checkpoint: "Drafting",
    deadline: "",
    expected_output: payload.expected_output || "",
    acceptance_criteria: [],
    dependencies: [],
    target_repo: "",
    output: "",
    ai_update: "",
    user_update: ""
  };
  registry.entities.tasks[taskId] = {
    ew_id: payload.ew_id,
    project_id: projectId,
    path: taskPath,
    title: task.title,
    assigned_to: task.assigned_to,
    status: "Backlog",
    expected_output: task.expected_output
  };
  return { taskId, taskPath, task };
}

async function proposalActions(payload) {
  if (payload.type === "edit_file") {
    const filePath = String(payload.path || "").replaceAll("\\", "/").replace(/^\/+/, "");
    if (!filePath) throw new Error("edit_file requires path");
    const full = safeRepoPath(filePath);
    const action = existsSync(full) ? "update" : "create";
    return {
      title: payload.message || `Edit ${filePath}`,
      message: payload.message || `Edit ${filePath}`,
      actions: [{ action, file_path: filePath, content: payload.content || "" }]
    };
  }
  if (payload.type === "create_task") {
    const registry = await loadRegistry();
    const { taskId, taskPath, task } = createTaskPayload(registry, payload);
    return {
      title: `Create ${taskId}: ${payload.title || ""}`,
      message: `Create ${taskId}: ${payload.title || ""}`,
      actions: [
        { action: "update", file_path: "registry.yaml", content: dump(registry) },
        { action: "create", file_path: taskPath, content: dump(task) }
      ]
    };
  }
  throw new Error(`unknown proposal type: ${payload.type}`);
}

async function localProposal(title, message, actions) {
  const proposalId = `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${slugify(title).slice(0, 40)}`;
  const dir = path.join(REPO, ".project-os", "proposals", proposalId);
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "proposal.json"), dump({ title, message, actions, created_at: nowIso() }), "utf8");
  let index = 0;
  for (const action of actions) {
    index += 1;
    const safeName = action.file_path.replace(/[^a-zA-Z0-9._-]+/g, "_");
    await writeFile(path.join(dir, `${String(index).padStart(2, "0")}-${action.action}-${safeName}`), action.content, "utf8");
  }
  return { mode: "dry-run", proposal_dir: dir, title, actions: actions.length };
}

async function gitlabApi(method, endpoint, body) {
  const gitlabUrl = process.env.PROJECT_OS_GITLAB_URL || "";
  const token = process.env.PROJECT_OS_GITLAB_TOKEN || "";
  if (!gitlabUrl || !token) throw new Error("GitLab API requires PROJECT_OS_GITLAB_URL and PROJECT_OS_GITLAB_TOKEN");
  const response = await fetch(`${gitlabUrl.replace(/\/$/, "")}${endpoint}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "PRIVATE-TOKEN": token
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`GitLab API ${response.status}: ${text}`);
  return text ? JSON.parse(text) : {};
}

async function gitlabProposal(title, message, actions) {
  const registry = await loadRegistry();
  const projectPath = process.env.PROJECT_OS_GITLAB_PROJECT || registry.gitlab?.project_path || "";
  if (!projectPath) throw new Error("GitLab MR mode requires PROJECT_OS_GITLAB_PROJECT");
  const targetBranch = process.env.PROJECT_OS_TARGET_BRANCH || registry.gitlab?.default_branch || "main";
  const sourceBranch = `project-os/${slugify(title).slice(0, 48)}-${Date.now()}`;
  const encodedProject = encodeURIComponent(projectPath);
  const commit = await gitlabApi("POST", `/api/v4/projects/${encodedProject}/repository/commits`, {
    branch: sourceBranch,
    start_branch: targetBranch,
    commit_message: message,
    actions
  });
  const mr = await gitlabApi("POST", `/api/v4/projects/${encodedProject}/merge_requests`, {
    source_branch: sourceBranch,
    target_branch: targetBranch,
    title,
    description: "Created by GitLab Project OS website.",
    remove_source_branch: true
  });
  return { mode: "gitlab", branch: sourceBranch, commit: commit.id || "", merge_request: mr.web_url || "" };
}

async function githubApi(method, endpoint, body) {
  const apiUrl = process.env.PROJECT_OS_GITHUB_API_URL || "https://api.github.com";
  const token = process.env.PROJECT_OS_GITHUB_TOKEN || process.env.GH_TOKEN || "";
  if (!token) throw new Error("GitHub API requires PROJECT_OS_GITHUB_TOKEN or GH_TOKEN");
  const response = await fetch(`${apiUrl.replace(/\/$/, "")}${endpoint}`, {
    method,
    headers: {
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "git-based-project-management",
      "X-GitHub-Api-Version": "2022-11-28",
      "Authorization": `Bearer ${token}`
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`GitHub API ${response.status}: ${text}`);
  return text ? JSON.parse(text) : {};
}

async function githubProposal(title, message, actions) {
  const registry = await loadRegistry();
  const repoName = process.env.PROJECT_OS_GITHUB_REPO || registry.github?.repo || "";
  if (!repoName) throw new Error("GitHub PR mode requires PROJECT_OS_GITHUB_REPO");
  const targetBranch = process.env.PROJECT_OS_TARGET_BRANCH || registry.github?.default_branch || "main";
  const sourceBranch = `project-os/${slugify(title).slice(0, 48)}-${Date.now()}`;
  const encodedRepo = repoName.split("/").map(encodeURIComponent).join("/");
  const ref = await githubApi("GET", `/repos/${encodedRepo}/git/ref/heads/${encodeURIComponent(targetBranch)}`);
  await githubApi("POST", `/repos/${encodedRepo}/git/refs`, {
    ref: `refs/heads/${sourceBranch}`,
    sha: ref.object.sha
  });
  for (const action of actions) {
    const endpoint = `/repos/${encodedRepo}/contents/${action.file_path.split("/").map(encodeURIComponent).join("/")}`;
    let sha = undefined;
    if (action.action === "update") {
      try {
        const existing = await githubApi("GET", `${endpoint}?ref=${encodeURIComponent(sourceBranch)}`);
        sha = existing.sha;
      } catch {
        sha = undefined;
      }
    }
    await githubApi("PUT", endpoint, {
      message,
      content: Buffer.from(action.content, "utf8").toString("base64"),
      branch: sourceBranch,
      ...(sha ? { sha } : {})
    });
  }
  const pr = await githubApi("POST", `/repos/${encodedRepo}/pulls`, {
    title,
    head: sourceBranch,
    base: targetBranch,
    body: "Created by Git-Based Project Management website."
  });
  return { mode: "github", branch: sourceBranch, pull_request: pr.html_url || "" };
}

async function handleProposal(payload) {
  const { title, message, actions } = await proposalActions(payload);
  const live = process.env.PROJECT_OS_LIVE_PROPOSALS === "1" || process.env.PROJECT_OS_LIVE_PROPOSALS === "true";
  const provider = (process.env.PROJECT_OS_PROVIDER || "").toLowerCase();
  if (live && provider === "github") return githubProposal(title, message, actions);
  if (live && provider === "gitlab") return gitlabProposal(title, message, actions);
  if (process.env.PROJECT_OS_GITLAB_MR === "1" || process.env.PROJECT_OS_GITLAB_MR === "true") return gitlabProposal(title, message, actions);
  return localProposal(title, message, actions);
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filePath.endsWith(".svg")) return "image/svg+xml";
  if (filePath.endsWith(".json")) return "application/json; charset=utf-8";
  return "application/octet-stream";
}

function sendJson(res, status, body) {
  const text = JSON.stringify(body, null, 2);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(text) });
  res.end(text);
}

async function readRequestJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString("utf8");
  return text ? JSON.parse(text) : {};
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    if (req.method === "GET" && url.pathname === "/healthz") {
      sendJson(res, 200, { ok: true, repo: REPO, runtime: "node" });
      return;
    }
    if (req.method === "GET" && url.pathname === "/api/data") {
      sendJson(res, 200, await compileData());
      return;
    }
    if (req.method === "POST" && url.pathname === "/api/proposals") {
      sendJson(res, 200, await handleProposal(await readRequestJson(req)));
      return;
    }
    if (req.method === "GET") {
      const requestPath = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/static\//, "");
      const filePath = safeStaticPath(requestPath);
      const body = await readFile(filePath);
      res.writeHead(200, { "Content-Type": contentType(filePath), "Content-Length": body.length });
      res.end(body);
      return;
    }
    sendJson(res, 404, { error: "not found" });
  } catch (error) {
    sendJson(res, 500, { error: error.message });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Project OS website listening on http://${HOST}:${PORT}/`);
  console.log(`Repo: ${REPO}`);
  console.log(`Proposal mode: ${process.env.PROJECT_OS_LIVE_PROPOSALS ? `${process.env.PROJECT_OS_PROVIDER || "live"} PR/MR` : "dry-run"}`);
});
