import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir, access } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = path.resolve(process.env.GPM_STATIC_DIR || path.join(__dirname, "static"));
const REPO = path.resolve(process.env.GPM_REPO || process.cwd());
const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 8787);
const TASK_STATUSES = new Set(["Backlog", "In Progress", "Blocked", "Done", "Verified", "Iceboxed"]);
const PROJECT_STATUSES = new Set(["Planning", "Active", "Paused", "Shipped", "Archived"]);
const DOC_TYPES = new Set(["proposal", "brief", "game-design", "technical-spec", "frontend-spec", "backend-spec", "playtest-plan", "playtest-report", "qa-report", "research-report", "asset-brief", "3d-asset-brief", "video-brief", "mockup-review", "build-note", "release-plan", "postmortem", "decision", "meeting-notes"]);
const DOC_SECTION_REQUIREMENTS = {
  proposal: ["Problem", "Proposed Direction", "Risks", "Decision Needed"],
  brief: ["Goal", "Audience", "Scope", "Success Criteria"],
  "game-design": ["Player Fantasy", "Core Loop", "Systems", "UX Notes", "Tuning Questions"],
  "technical-spec": ["Goal", "Architecture", "Interfaces", "Test Plan", "Rollout"],
  "frontend-spec": ["User Flow", "State", "Components", "API Contract", "Test Plan"],
  "backend-spec": ["Goal", "Data Model", "API", "Operations", "Test Plan"],
  "playtest-plan": ["Build", "Participants", "Test Goals", "Tasks", "Capture Plan"],
  "playtest-report": ["Build", "Participants", "Findings", "Evidence", "Recommended Changes"],
  "qa-report": ["Build", "Scope", "Defects", "Risks", "Release Recommendation"],
  "asset-brief": ["Purpose", "References", "Requirements", "Format", "Delivery"],
  "3d-asset-brief": ["Purpose", "References", "Model Requirements", "Texture Requirements", "Delivery"],
  "mockup-review": ["Context", "Mockups", "Feedback", "Decision", "Follow-up Tasks"]
};

function nowIso() {
  const now = new Date();
  const sg = new Date(now.getTime() + 8 * 60 * 60 * 1000);
  return `${sg.toISOString().replace("Z", "")}+08:00`;
}

function slugify(value) {
  return String(value || "change").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "change";
}

function safeRepoPath(relPath) {
  const clean = String(relPath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  const full = path.resolve(REPO, clean);
  if (full !== REPO && !full.startsWith(REPO + path.sep)) throw new Error(`path escapes repo: ${relPath}`);
  return full;
}

function safeStaticPath(relPath) {
  const clean = String(relPath || "index.html").replaceAll("\\", "/").replace(/^\/+/, "");
  const full = path.resolve(STATIC_DIR, clean);
  if (full !== STATIC_DIR && !full.startsWith(STATIC_DIR + path.sep)) throw new Error(`path escapes static dir: ${relPath}`);
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
  return JSON.parse(text);
}

function dump(data) {
  return JSON.stringify(data, null, 2) + "\n";
}

async function exists(filePath) {
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
    if (index !== -1) data[line.slice(0, index).trim()] = line.slice(index + 1).trim().replace(/^"|"$/g, "");
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
  const prefix = kind === "project" ? "PROJ" : kind === "task" ? "TASK" : kind === "doc" ? "DOC" : kind === "asset" ? "ASSET" : kind === "event" ? "EVENT" : kind === "review" ? "REVIEW" : "ITEM";
  const section = kind === "doc" ? "docs" : `${kind}s`;
  const existing = Object.keys(registry[section] || {});
  registry.next_ids ||= {};
  let number = Number(registry.next_ids[kind] || 1);
  while (existing.includes(`${prefix}${number}`)) number += 1;
  registry.next_ids[kind] = number + 1;
  return `${prefix}${number}`;
}

function projectFolder(projectId, name) {
  return `${projectId}-${slugify(name)}`;
}

function docFolder(docType) {
  if (["proposal", "brief"].includes(docType)) return "proposals";
  if (["game-design", "technical-spec", "frontend-spec", "backend-spec"].includes(docType)) return "design";
  if (["playtest-plan", "playtest-report", "qa-report", "research-report"].includes(docType)) return "reports";
  if (["asset-brief", "3d-asset-brief", "video-brief", "mockup-review", "build-note"].includes(docType)) return "production";
  if (["release-plan", "postmortem"].includes(docType)) return "release";
  if (["decision", "meeting-notes"].includes(docType)) return "notes";
  return "docs";
}

function docBodyTemplate(docType) {
  const sections = DOC_SECTION_REQUIREMENTS[docType] || ["Purpose", "Context", "Content", "Open Questions"];
  return sections.map((section) => `## ${section}\n\nTBD`).join("\n\n");
}

function splitCsv(value) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function appendJsonl(existing, record) {
  const prefix = String(existing || "").replace(/\n+$/g, "");
  const line = JSON.stringify(record);
  return prefix ? `${prefix}\n${line}\n` : `${line}\n`;
}

async function validateRepo(registry) {
  const issues = [];
  for (const section of ["projects", "tasks", "docs", "people", "next_ids"]) {
    if (!(section in registry)) issues.push({ level: "error", code: "REGISTRY_SECTION", message: `${section} must exist`, path: "registry.yaml" });
  }
  for (const [kind, section, prefix] of [["project", "projects", "PROJ"], ["task", "tasks", "TASK"], ["doc", "docs", "DOC"]]) {
    const rows = registry[section] || {};
    const expected = maxSuffix(Object.keys(rows), prefix) + 1;
    if (Number(registry.next_ids?.[kind] || 1) < expected) issues.push({ level: "error", code: "NEXT_ID_STALE", message: `next_ids.${kind} should be at least ${expected}`, path: "registry.yaml" });
    for (const [id, row] of Object.entries(rows)) {
      if (!new RegExp(`^${prefix}\\d+$`).test(id)) issues.push({ level: "error", code: "ID_FORMAT", message: `${id} should match ${prefix}#`, path: "registry.yaml" });
      const rel = row.path || row.readme;
      if (rel && !(await exists(safeRepoPath(rel)))) issues.push({ level: "error", code: "PATH_MISSING", message: `${id} path does not exist`, path: rel });
    }
  }
  for (const [projectId, project] of Object.entries(registry.projects || {})) {
    if (!PROJECT_STATUSES.has(project.status)) issues.push({ level: "warn", code: "PROJECT_STATUS", message: `${projectId} status is unusual: ${project.status}`, path: project.path || "" });
    if (!project.owners?.length) issues.push({ level: "warn", code: "PROJECT_OWNER_MISSING", message: `${projectId} has no owners`, path: project.path || "" });
  }
  for (const [docId, doc] of Object.entries(registry.docs || {})) {
    if (!registry.projects?.[doc.project_id]) issues.push({ level: "error", code: "REL_DOC_PROJECT", message: `${docId} references missing project ${doc.project_id}`, path: doc.path || "" });
    if (!DOC_TYPES.has(doc.doc_type)) issues.push({ level: "warn", code: "DOC_TYPE", message: `${docId} has unusual doc_type ${doc.doc_type}`, path: doc.path || "" });
  }
  for (const [taskId, ref] of Object.entries(registry.tasks || {})) {
    let task = {};
    try {
      task = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch (error) {
      issues.push({ level: "error", code: "TASK_PARSE", message: error.message, path: ref.path || "" });
      continue;
    }
    if (task.id !== taskId) issues.push({ level: "error", code: "TASK_ID_MISMATCH", message: `${taskId} file id is ${task.id}`, path: ref.path || "" });
    if (!registry.projects?.[task.project_id]) issues.push({ level: "error", code: "REL_TASK_PROJECT", message: `${taskId} references missing project ${task.project_id}`, path: ref.path || "" });
    if (!TASK_STATUSES.has(task.status)) issues.push({ level: "error", code: "TASK_STATUS", message: `${taskId} has invalid status ${task.status}`, path: ref.path || "" });
    for (const dep of task.dependencies || []) {
      if (!registry.tasks?.[dep]) issues.push({ level: "error", code: "REL_TASK_DEPENDENCY", message: `${taskId} depends on missing ${dep}`, path: ref.path || "" });
    }
  }
  return issues;
}

async function collectDocs(registry) {
  const docs = [];
  for (const [docId, row] of Object.entries(registry.docs || {})) {
    const text = await readText(safeRepoPath(row.path), "");
    const [frontmatter, body] = parseFrontmatter(text);
    docs.push({ id: docId, project_id: row.project_id || "", type: row.doc_type || frontmatter.type || "", title: markdownTitle(body, row.title || docId), path: row.path || "", owner: row.owner || "", status: row.status || "" });
  }
  return docs;
}

async function collectTasks(registry) {
  const tasks = [];
  for (const [taskId, ref] of Object.entries(registry.tasks || {})) {
    let task = {};
    try {
      task = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch {
      task = { id: taskId, title: ref.title || "", status: "Invalid" };
    }
    const project = registry.projects?.[task.project_id || ref.project_id] || {};
    tasks.push({ ...ref, ...task, id: taskId, path: ref.path, project_name: project.name || "" });
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
    schema_version: registry.schema_version || 2,
    repo_name: registry.name || path.basename(REPO),
    repo_path: REPO,
    provider: registry.provider || "",
    github_repo: registry.github?.repo || "",
    gitlab_url: registry.gitlab?.url || "",
    gitlab_project: registry.gitlab?.project_path || "",
    git_commit: "",
    generated_at: nowIso(),
    projects: Object.entries(registry.projects || {}).map(([id, value]) => ({ id, ...value })),
    docs: await collectDocs(registry),
    tasks: await collectTasks(registry),
    assets: Object.entries(registry.assets || {}).map(([id, value]) => ({ id, ...value })),
    people: registry.people || [],
    events: await readJsonl("events/task-events.jsonl"),
    reviews: await readJsonl("reviews/task-reviews.jsonl"),
    validation: { issues }
  };
}

function createTaskPayload(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const taskId = allocateId(registry, "task");
  const taskPath = `projects/${projectFolder(payload.project_id, project.name)}/tasks/${taskId}.yaml`;
  const task = { id: taskId, project_id: payload.project_id, title: payload.title || "", assigned_to: payload.assigned_to || "", role: payload.role || "", status: "Backlog", checkpoint: "Drafting", priority: "Medium", deadline: "", expected_output: payload.expected_output || "", acceptance_criteria: [], dependencies: [], target_repo: "", output: "", blocker: "", ai_update: "", user_update: "" };
  registry.tasks[taskId] = { project_id: payload.project_id, path: taskPath, title: task.title, assigned_to: task.assigned_to, status: "Backlog", expected_output: task.expected_output };
  return { taskId, taskPath, task };
}

function createDocPayload(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const docId = allocateId(registry, "doc");
  const docType = payload.doc_type || "proposal";
  const rel = `projects/${projectFolder(payload.project_id, project.name)}/docs/${docFolder(docType)}/${docId}-${slugify(payload.title || "document")}.md`;
  const text = `---\nid: ${docId}\nproject_id: ${payload.project_id}\ntype: ${docType}\nowner: ${payload.owner || ""}\nstatus: draft\n---\n\n# ${docId} - ${payload.title || "Document"}\n\n${docBodyTemplate(docType)}\n`;
  registry.docs[docId] = { project_id: payload.project_id, doc_type: docType, title: payload.title || "", owner: payload.owner || "", path: rel, status: "draft" };
  return { docId, rel, text };
}

async function loadTaskRecord(registry, taskId) {
  const ref = registry.tasks?.[taskId];
  if (!ref) throw new Error(`missing task ${taskId}`);
  const task = await readJsonSubset(safeRepoPath(ref.path), {});
  if (task.id !== taskId) throw new Error(`${ref.path} id is ${task.id}, expected ${taskId}`);
  return { path: ref.path, task };
}

function syncTaskRef(registry, taskId, taskPath, task) {
  registry.tasks ||= {};
  registry.tasks[taskId] = { project_id: task.project_id || "", path: taskPath, title: task.title || "", assigned_to: task.assigned_to || "", status: task.status || "Backlog", expected_output: task.expected_output || "" };
}

function makeEvent(registry, task, actor, eventType, message) {
  const eventId = allocateId(registry, "event");
  return { id: eventId, task_id: task.id || "", project_id: task.project_id || "", actor: actor || "Unknown", event_type: eventType || "update", message: message || "", created_at: nowIso() };
}

async function eventAction(record) {
  const rel = "events/task-events.jsonl";
  return { action: existsSync(safeRepoPath(rel)) ? "update" : "create", file_path: rel, content: appendJsonl(await readText(safeRepoPath(rel), ""), record) };
}

async function reviewAction(record) {
  const rel = "reviews/task-reviews.jsonl";
  return { action: existsSync(safeRepoPath(rel)) ? "update" : "create", file_path: rel, content: appendJsonl(await readText(safeRepoPath(rel), ""), record) };
}

async function updateTaskActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  for (const field of ["status", "checkpoint", "priority", "assigned_to", "deadline", "expected_output", "target_repo", "output", "blocker", "ai_update", "user_update"]) {
    if (payload[field]) task[field] = payload[field];
  }
  if (payload.acceptance_criteria) task.acceptance_criteria = splitCsv(payload.acceptance_criteria);
  if (payload.dependencies) task.dependencies = splitCsv(payload.dependencies);
  syncTaskRef(registry, taskId, taskPath, task);
  const title = `Update ${taskId}: ${task.title || ""}`;
  const actions = [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }];
  const message = payload.event_message || payload.user_update || payload.ai_update || `Updated ${taskId}`;
  if (!payload.suppress_event && (payload.actor || payload.event_message || payload.user_update || payload.status)) {
    actions.push(await eventAction(makeEvent(registry, task, payload.actor || "", "task_update", message)));
    actions[0].content = dump(registry);
  }
  return { title, message, actions };
}

async function submitOutputActions(registry, payload) {
  const result = await updateTaskActions(registry, { ...payload, status: payload.status || "Done", checkpoint: payload.checkpoint || "Review", suppress_event: true });
  const { task } = await loadTaskRecord(registry, payload.task_id || "");
  const event = makeEvent(registry, { ...task, id: payload.task_id }, payload.actor || "", "submitted_output", payload.message || payload.output || `Submitted output for ${payload.task_id}`);
  result.actions[0].content = dump(registry);
  result.actions.push(await eventAction(event));
  result.title = result.title.replace("Update", "Submit output for");
  result.message = event.message;
  return result;
}

async function reviewTaskActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  const decision = payload.decision || "changes_requested";
  if (decision === "approved") {
    task.status = "Verified";
    task.checkpoint = "Ready";
  } else {
    task.status = "In Progress";
    task.checkpoint = "Revising";
  }
  syncTaskRef(registry, taskId, taskPath, task);
  const review = { id: allocateId(registry, "review"), task_id: taskId, project_id: task.project_id || "", reviewer: payload.reviewer || "", decision, notes: payload.notes || "", created_at: nowIso() };
  const event = makeEvent(registry, task, payload.reviewer || "", `review_${decision}`, payload.notes || `${decision} review for ${taskId}`);
  return { title: `Review ${taskId}: ${decision}`, message: event.message, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await reviewAction(review), await eventAction(event)] };
}

async function registerAssetActions(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const assetId = allocateId(registry, "asset");
  const asset = { title: payload.title || "", type: payload.asset_type || payload.type || "asset", storage: payload.storage || "external-link", path: payload.path || "", source_url: payload.source_url || "", used_by: splitCsv(payload.used_by).length ? splitCsv(payload.used_by) : [payload.project_id], owner: payload.owner || "", status: payload.status || "draft" };
  registry.assets ||= {};
  registry.assets[assetId] = asset;
  const rel = `projects/${projectFolder(payload.project_id, project.name)}/assets/assets.yaml`;
  const manifest = await readJsonSubset(safeRepoPath(rel), { assets: {} });
  manifest.assets ||= {};
  manifest.assets[assetId] = asset;
  const title = `Register ${assetId}: ${asset.title}`;
  return { title, message: title, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: existsSync(safeRepoPath(rel)) ? "update" : "create", file_path: rel, content: dump(manifest) }] };
}

async function proposalActions(payload) {
  if (payload.type === "edit_file") {
    const filePath = String(payload.path || "").replaceAll("\\", "/").replace(/^\/+/, "");
    if (!filePath) throw new Error("edit_file requires path");
    const full = safeRepoPath(filePath);
    return { title: payload.message || `Edit ${filePath}`, message: payload.message || `Edit ${filePath}`, actions: [{ action: existsSync(full) ? "update" : "create", file_path: filePath, content: payload.content || "" }] };
  }
  if (payload.type === "create_task") {
    const registry = await loadRegistry();
    const { taskId, taskPath, task } = createTaskPayload(registry, payload);
    const title = `Create ${taskId}: ${payload.title || ""}`;
    return { title, message: title, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "create", file_path: taskPath, content: dump(task) }] };
  }
  if (payload.type === "create_doc") {
    const registry = await loadRegistry();
    const { docId, rel, text } = createDocPayload(registry, payload);
    const title = `Create ${docId}: ${payload.title || ""}`;
    return { title, message: title, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "create", file_path: rel, content: text }] };
  }
  if (payload.type === "update_task") {
    return updateTaskActions(await loadRegistry(), payload);
  }
  if (payload.type === "add_event") {
    const registry = await loadRegistry();
    const { task } = await loadTaskRecord(registry, payload.task_id || "");
    const record = makeEvent(registry, task, payload.actor || "", payload.event_type || "update", payload.message || "");
    return { title: `Add event to ${payload.task_id}`, message: record.message, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, await eventAction(record)] };
  }
  if (payload.type === "submit_output") {
    return submitOutputActions(await loadRegistry(), payload);
  }
  if (payload.type === "review_task") {
    return reviewTaskActions(await loadRegistry(), payload);
  }
  if (payload.type === "register_asset") {
    return registerAssetActions(await loadRegistry(), payload);
  }
  throw new Error(`unknown proposal type: ${payload.type}`);
}

async function localProposal(title, message, actions) {
  const proposalId = `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${slugify(title).slice(0, 40)}`;
  const dir = path.join(REPO, ".project-hub", "proposals", proposalId);
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "proposal.json"), dump({ title, message, actions, created_at: nowIso() }), "utf8");
  let index = 0;
  for (const action of actions) {
    index += 1;
    let safeName = action.file_path.replace(/[^a-zA-Z0-9._-]+/g, "_");
    if (safeName.length > 90) {
      const digest = createHash("sha1").update(action.file_path).digest("hex").slice(0, 10);
      const ext = path.extname(action.file_path).slice(0, 12);
      safeName = `${safeName.slice(0, 70).replace(/[._-]+$/g, "")}-${digest}${ext}`;
    }
    await writeFile(path.join(dir, `${String(index).padStart(2, "0")}-${action.action}-${safeName}`), action.content, "utf8");
  }
  return { mode: "dry-run", proposal_dir: dir, title, actions: actions.length };
}

async function providerApi(provider, method, endpoint, body) {
  if (provider === "github") {
    const apiUrl = process.env.GPM_GITHUB_API_URL || "https://api.github.com";
    const token = process.env.GPM_GITHUB_TOKEN || process.env.GH_TOKEN || "";
    if (!token) throw new Error("GitHub API requires GPM_GITHUB_TOKEN or GH_TOKEN");
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}${endpoint}`, { method, headers: { "Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "git-based-project-management", "X-GitHub-Api-Version": "2022-11-28", "Authorization": `Bearer ${token}` }, body: body ? JSON.stringify(body) : undefined });
    const text = await response.text();
    if (!response.ok) throw new Error(`GitHub API ${response.status}: ${text}`);
    return text ? JSON.parse(text) : {};
  }
  const gitlabUrl = process.env.GPM_GITLAB_URL || "";
  const token = process.env.GPM_GITLAB_TOKEN || "";
  if (!gitlabUrl || !token) throw new Error("GitLab API requires GPM_GITLAB_URL and GPM_GITLAB_TOKEN");
  const response = await fetch(`${gitlabUrl.replace(/\/$/, "")}${endpoint}`, { method, headers: { "Content-Type": "application/json", "PRIVATE-TOKEN": token }, body: body ? JSON.stringify(body) : undefined });
  const text = await response.text();
  if (!response.ok) throw new Error(`GitLab API ${response.status}: ${text}`);
  return text ? JSON.parse(text) : {};
}

async function githubProposal(registry, title, message, actions) {
  const repoName = process.env.GPM_GITHUB_REPO || registry.github?.repo || "";
  if (!repoName) throw new Error("GitHub PR mode requires GPM_GITHUB_REPO");
  const target = process.env.GPM_TARGET_BRANCH || registry.github?.default_branch || "main";
  const source = `project-hub/${slugify(title).slice(0, 48)}-${Date.now()}`;
  const encoded = repoName.split("/").map(encodeURIComponent).join("/");
  const ref = await providerApi("github", "GET", `/repos/${encoded}/git/ref/heads/${encodeURIComponent(target)}`);
  await providerApi("github", "POST", `/repos/${encoded}/git/refs`, { ref: `refs/heads/${source}`, sha: ref.object.sha });
  for (const action of actions) {
    const endpoint = `/repos/${encoded}/contents/${action.file_path.split("/").map(encodeURIComponent).join("/")}`;
    let sha = undefined;
    if (action.action === "update") {
      try {
        sha = (await providerApi("github", "GET", `${endpoint}?ref=${encodeURIComponent(source)}`)).sha;
      } catch {
        sha = undefined;
      }
    }
    await providerApi("github", "PUT", endpoint, { message, content: Buffer.from(action.content, "utf8").toString("base64"), branch: source, ...(sha ? { sha } : {}) });
  }
  const pr = await providerApi("github", "POST", `/repos/${encoded}/pulls`, { title, head: source, base: target, body: "Created by Git-Based Project Management website." });
  return { mode: "github", branch: source, pull_request: pr.html_url || "" };
}

async function gitlabProposal(registry, title, message, actions) {
  const projectPath = process.env.GPM_GITLAB_PROJECT || registry.gitlab?.project_path || "";
  if (!projectPath) throw new Error("GitLab MR mode requires GPM_GITLAB_PROJECT");
  const target = process.env.GPM_TARGET_BRANCH || registry.gitlab?.default_branch || "main";
  const source = `project-hub/${slugify(title).slice(0, 48)}-${Date.now()}`;
  const encoded = encodeURIComponent(projectPath);
  await providerApi("gitlab", "POST", `/api/v4/projects/${encoded}/repository/commits`, { branch: source, start_branch: target, commit_message: message, actions });
  const mr = await providerApi("gitlab", "POST", `/api/v4/projects/${encoded}/merge_requests`, { source_branch: source, target_branch: target, title, description: "Created by Git-Based Project Management website.", remove_source_branch: true });
  return { mode: "gitlab", branch: source, merge_request: mr.web_url || "" };
}

async function handleProposal(payload) {
  const registry = await loadRegistry();
  const { title, message, actions } = await proposalActions(payload);
  const live = ["1", "true"].includes(String(process.env.GPM_LIVE_PROPOSALS || "").toLowerCase());
  const provider = (process.env.GPM_PROVIDER || registry.provider || "").toLowerCase();
  if (live && provider === "github") return githubProposal(registry, title, message, actions);
  if (live && provider === "gitlab") return gitlabProposal(registry, title, message, actions);
  return localProposal(title, message, actions);
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filePath.endsWith(".svg")) return "image/svg+xml";
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
    if (req.method === "GET" && url.pathname === "/healthz") return sendJson(res, 200, { ok: true, repo: REPO, runtime: "node" });
    if (req.method === "GET" && url.pathname === "/api/data") return sendJson(res, 200, await compileData());
    if (req.method === "POST" && url.pathname === "/api/proposals") return sendJson(res, 200, await handleProposal(await readRequestJson(req)));
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
  console.log(`Project website listening on http://${HOST}:${PORT}/`);
  console.log(`Repo: ${REPO}`);
  console.log(`Proposal mode: ${process.env.GPM_LIVE_PROPOSALS ? `${process.env.GPM_PROVIDER || "live"} PR/MR` : "dry-run"}`);
});
