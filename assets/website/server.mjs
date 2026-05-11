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
const TASK_STATUSES = new Set(["Backlog", "In Progress", "Blocked", "In Review", "Done", "Verified", "Iceboxed"]);
const PROJECT_STATUSES = new Set(["Planning", "Active", "Paused", "Shipped", "Archived"]);
const MILESTONE_STATUSES = new Set(["Planned", "Active", "At Risk", "Done", "Archived"]);
const ATTEMPT_EVENT_TYPES = new Set(["submitted_output", "output_attempted", "verification_failed", "output_withdrawn", "output_superseded", "review_cancelled"]);
const DOC_TYPES = new Set(["proposal", "brief", "feature-proposal", "feature-brief", "game-design", "technical-spec", "frontend-spec", "backend-spec", "telemetry-spec", "api-contract", "playtest-plan", "playtest-session", "playtest-report", "qa-report", "qa-bug-report", "research-report", "asset-brief", "3d-asset-brief", "art-handoff", "3d-model-handoff", "video-brief", "mockup-review", "build-note", "release-plan", "postmortem", "decision", "meeting-notes", "project-note", "weekly-update", "risk-log", "retro-notes"]);
const HISTORICAL_TASK_STATUSES = new Set(["Done", "Verified", "Iceboxed"]);
const HISTORICAL_DOC_STATUSES = new Set(["final", "archived", "historical"]);
const DOC_SECTION_REQUIREMENTS = {
  proposal: ["Problem", "Proposed Direction", "Risks", "Decision Needed"],
  brief: ["Goal", "Audience", "Scope", "Success Criteria"],
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
  "asset-brief": ["Purpose", "References", "Requirements", "Format", "Delivery"],
  "3d-asset-brief": ["Purpose", "References", "Model Requirements", "Texture Requirements", "Delivery"],
  "art-handoff": ["Source Files", "Export Format", "Style References", "Acceptance", "Integration Notes"],
  "3d-model-handoff": ["Scale", "Geometry", "Materials", "LODs", "Collision", "Export"],
  "mockup-review": ["Context", "Mockups", "Feedback", "Decision", "Follow-up Tasks"],
  "decision": ["Context", "Decision", "Options Considered", "Consequences"],
  "meeting-notes": ["Attendees", "Discussion", "Decisions", "Actions"],
  "project-note": ["Context", "Note", "Links", "Follow-up"],
  "weekly-update": ["Highlights", "Progress", "Risks", "Next Week"],
  "risk-log": ["Risk", "Impact", "Mitigation", "Owner"],
  "retro-notes": ["What Worked", "What Did Not", "Actions", "Owners"]
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

async function fileSha256(filePath) {
  try {
    const bytes = await readFile(filePath);
    return createHash("sha256").update(bytes).digest("hex");
  } catch {
    return "";
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
  const prefix = kind === "project" ? "PROJ" : kind === "milestone" ? "MILESTONE" : kind === "task" ? "TASK" : kind === "doc" ? "DOC" : kind === "asset" ? "ASSET" : kind === "event" ? "EVENT" : kind === "review" ? "REVIEW" : "ITEM";
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
  if (["proposal", "brief", "feature-proposal"].includes(docType)) return "proposals";
  if (["game-design", "feature-brief"].includes(docType)) return "design";
  if (["technical-spec", "frontend-spec", "backend-spec", "telemetry-spec", "api-contract"].includes(docType)) return "engineering";
  if (["playtest-plan", "playtest-session", "playtest-report", "qa-report", "qa-bug-report", "research-report"].includes(docType)) return "reports";
  if (["asset-brief", "3d-asset-brief", "art-handoff", "3d-model-handoff", "video-brief", "mockup-review", "build-note"].includes(docType)) return "production";
  if (["release-plan", "postmortem"].includes(docType)) return "release";
  if (docType === "decision") return "decisions";
  if (["meeting-notes", "project-note", "weekly-update", "risk-log", "retro-notes"].includes(docType)) return "notes";
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

function approvedReviewExists(reviews, taskId) {
  return reviews.some((row) => row.task_id === taskId && row.decision === "approved");
}

function normalizeRepoRef(value) {
  const clean = String(value || "").trim().replace(/\/+$/g, "").toLowerCase();
  return clean.endsWith(".git") ? clean.slice(0, -4) : clean;
}

function projectRepoKeys(project) {
  const keys = new Set();
  for (const repoLink of project?.repos || []) {
    for (const field of ["name", "url"]) {
      const value = normalizeRepoRef(repoLink[field] || "");
      if (value) keys.add(value);
    }
  }
  return keys;
}

function projectRepoMatches(project, targetRepo) {
  const target = normalizeRepoRef(targetRepo);
  return Boolean(target) && projectRepoKeys(project).has(target);
}

function emailFromActor(value) {
  const clean = String(value || "").trim();
  const angle = /<([^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>/.exec(clean);
  if (angle) return angle[1].toLowerCase();
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(clean) ? clean.toLowerCase() : "";
}

function actorHasStaffEmail(registry, value) {
  const clean = String(value || "").trim();
  if (!clean || ["unknown", "system"].includes(clean.toLowerCase())) return true;
  if (emailFromActor(clean)) return true;
  const lower = clean.toLowerCase();
  return (registry.people || []).some((person) => String(person.name || "").toLowerCase() === lower && emailFromActor(person.email || ""));
}

function taskFolderFromPath(taskPath) {
  const clean = String(taskPath || "").replaceAll("\\", "/");
  if (clean.endsWith("/task.yaml")) return clean.split("/").slice(0, -1).join("/");
  return clean.endsWith(".yaml") ? clean.replace(/\.yaml$/, "") : clean;
}

async function validateRepo(registry) {
  const issues = [];
  for (const section of ["projects", "milestones", "tasks", "docs", "people", "next_ids"]) {
    if (!(section in registry)) issues.push({ level: "error", code: "REGISTRY_SECTION", message: `${section} must exist`, path: "registry.yaml" });
  }
  for (const [index, person] of (registry.people || []).entries()) {
    if (!emailFromActor(person.email || "")) issues.push({ level: "warn", code: "PEOPLE_EMAIL_MISSING", message: `people[${index}] ${person.name || "unnamed"} should include a staff email`, path: "registry.yaml" });
  }
  for (const [kind, section, prefix] of [["project", "projects", "PROJ"], ["milestone", "milestones", "MILESTONE"], ["task", "tasks", "TASK"], ["doc", "docs", "DOC"]]) {
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
    for (const repoLink of project.repos || []) {
      if (!repoLink.name) issues.push({ level: "warn", code: "PROJECT_REPO_NAME_MISSING", message: `${projectId} has repo link without name`, path: project.path || "" });
      if (!repoLink.provider) issues.push({ level: "warn", code: "PROJECT_REPO_PROVIDER_MISSING", message: `${projectId} has repo link without provider`, path: project.path || "" });
      if (!repoLink.url) issues.push({ level: "warn", code: "PROJECT_REPO_URL_MISSING", message: `${projectId} has repo link without url`, path: project.path || "" });
    }
    if (project.roadmap && !(await exists(safeRepoPath(project.roadmap)))) issues.push({ level: "warn", code: "PROJECT_ROADMAP_MISSING", message: `${projectId} roadmap file is missing`, path: project.roadmap });
  }
  for (const [milestoneId, ref] of Object.entries(registry.milestones || {})) {
    let milestone = {};
    try {
      milestone = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch (error) {
      issues.push({ level: "error", code: "MILESTONE_PARSE", message: error.message, path: ref.path || "" });
      continue;
    }
    if (milestone.id !== milestoneId) issues.push({ level: "error", code: "MILESTONE_ID_MISMATCH", message: `${milestoneId} file id is ${milestone.id}`, path: ref.path || "" });
    if (!registry.projects?.[milestone.project_id]) issues.push({ level: "error", code: "REL_MILESTONE_PROJECT", message: `${milestoneId} references missing project ${milestone.project_id}`, path: ref.path || "" });
    if (!MILESTONE_STATUSES.has(milestone.status || "Planned")) issues.push({ level: "warn", code: "MILESTONE_STATUS", message: `${milestoneId} has unusual status ${milestone.status}`, path: ref.path || "" });
  }
  for (const [docId, doc] of Object.entries(registry.docs || {})) {
    if (!registry.projects?.[doc.project_id]) issues.push({ level: "error", code: "REL_DOC_PROJECT", message: `${docId} references missing project ${doc.project_id}`, path: doc.path || "" });
    if (!DOC_TYPES.has(doc.doc_type)) issues.push({ level: "warn", code: "DOC_TYPE", message: `${docId} has unusual doc_type ${doc.doc_type}`, path: doc.path || "" });
  }
  const reviews = await readJsonl("reviews/task-reviews.jsonl");
  const events = await readJsonl("events/task-events.jsonl");
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
    if (!task.assigned_to && !task.role) issues.push({ level: "warn", code: "TASK_ASSIGNEE_MISSING", message: `${taskId} has no assignee or role placeholder`, path: ref.path || "" });
    if (!task.assigned_to && task.role && !["Backlog", "Iceboxed"].includes(task.status || "")) issues.push({ level: "warn", code: "TASK_ROLE_ONLY_ASSIGNEE", message: `${taskId} is active with only role placeholder ${task.role}; assign a staff email`, path: ref.path || "" });
    if (task.assigned_to && !actorHasStaffEmail(registry, task.assigned_to)) issues.push({ level: "warn", code: "TASK_ASSIGNEE_STAFF_EMAIL", message: `${taskId} assignee should be a staff email or a person with email in registry.people`, path: ref.path || "" });
    if (task.reviewer && !actorHasStaffEmail(registry, task.reviewer)) issues.push({ level: "warn", code: "TASK_REVIEWER_STAFF_EMAIL", message: `${taskId} reviewer should be a staff email or a person with email in registry.people`, path: ref.path || "" });
    if (task.status === "In Review" && !task.output) issues.push({ level: "error", code: "TASK_REVIEW_OUTPUT_MISSING", message: `${taskId} is In Review without output link`, path: ref.path || "" });
    if (["Done", "Verified"].includes(task.status) && !task.output) issues.push({ level: "error", code: "TASK_OUTPUT_MISSING", message: `${taskId} is ${task.status} without output link`, path: ref.path || "" });
    if (["Done", "Verified"].includes(task.status) && !approvedReviewExists(reviews, taskId)) issues.push({ level: "error", code: "TASK_APPROVED_REVIEW_MISSING", message: `${taskId} is ${task.status} without an approved review record`, path: ref.path || "" });
    const targetRepo = task.target_repo || "";
    const project = registry.projects?.[task.project_id] || {};
    if (targetRepo && !projectRepoMatches(project, targetRepo)) issues.push({ level: "warn", code: "TASK_TARGET_REPO_UNKNOWN", message: `${taskId} target_repo ${targetRepo} is not listed in its project repos`, path: ref.path || "" });
    if (task.status === "In Review" && task.output && targetRepo && !task.output_commit) issues.push({ level: "warn", code: "TASK_OUTPUT_COMMIT_MISSING", message: `${taskId} is in review with target_repo but no output_commit`, path: ref.path || "" });
    if (["Done", "Verified"].includes(task.status) && targetRepo && !task.output_commit) issues.push({ level: "error", code: "TASK_OUTPUT_COMMIT_MISSING", message: `${taskId} is ${task.status} with target_repo but no output_commit`, path: ref.path || "" });
    if (task.milestone && !registry.milestones?.[task.milestone]) issues.push({ level: "error", code: "REL_TASK_MILESTONE", message: `${taskId} references missing ${task.milestone}`, path: ref.path || "" });
    for (const dep of task.dependencies || []) {
      if (!registry.tasks?.[dep]) issues.push({ level: "error", code: "REL_TASK_DEPENDENCY", message: `${taskId} depends on missing ${dep}`, path: ref.path || "" });
    }
  }
  for (const event of events) {
    if (event.actor && !actorHasStaffEmail(registry, event.actor)) issues.push({ level: "warn", code: "EVENT_ACTOR_STAFF_EMAIL", message: `${event.id || event.task_id || "event"} actor should be a staff email or a person with email in registry.people`, path: "events/task-events.jsonl" });
  }
  for (const review of reviews) {
    if (review.reviewer && !actorHasStaffEmail(registry, review.reviewer)) issues.push({ level: "warn", code: "REVIEWER_STAFF_EMAIL", message: `${review.id || review.task_id || "review"} reviewer should be a staff email or a person with email in registry.people`, path: "reviews/task-reviews.jsonl" });
  }
  for (const rel of ["policies/output-requirements.yaml", "policies/definition-of-ready.yaml", "policies/definition-of-done.yaml", "policies/review-gates.yaml", "policies/role-permissions.yaml", "policies/storage-policy.yaml", "policies/wiki-guidelines.md", "policies/terminology.yaml", "policies/branch-protection.md", "policies/agent-operating-rules.md"]) {
    if (!(await exists(safeRepoPath(rel)))) issues.push({ level: "warn", code: "POLICY_MISSING", message: `${rel} is missing`, path: rel });
  }
  return issues;
}

async function collectDocs(registry) {
  const docs = [];
  for (const [docId, row] of Object.entries(registry.docs || {})) {
    const full = safeRepoPath(row.path);
    const text = await readText(full, "");
    const [frontmatter, body] = parseFrontmatter(text);
    const headings = body.split(/\r?\n/).filter((line) => line.startsWith("## ")).map((line) => line.slice(3).trim());
    const plain = body.replace(/`([^`]*)`/g, "$1").replace(/\s+/g, " ").trim();
    docs.push({ id: docId, project_id: row.project_id || "", type: row.doc_type || frontmatter.type || "", title: markdownTitle(body, row.title || docId), path: row.path || "", owner: row.owner || "", status: row.status || "", sha256: await fileSha256(full), headings, snippet: plain.slice(0, 280), search_text: plain.slice(0, 12000) });
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
    tasks.push({ ...ref, ...task, id: taskId, path: ref.path, folder: ref.folder || taskFolderFromPath(ref.path), project_name: project.name || "", sha256: ref.path ? await fileSha256(safeRepoPath(ref.path)) : "" });
  }
  return tasks;
}

async function collectMilestones(registry) {
  const rows = [];
  for (const [milestoneId, ref] of Object.entries(registry.milestones || {})) {
    let milestone = {};
    try {
      milestone = await readJsonSubset(safeRepoPath(ref.path), {});
    } catch {
      milestone = { id: milestoneId, title: ref.title || "", status: "Invalid" };
    }
    rows.push({ ...ref, ...milestone, id: milestoneId, path: ref.path, sha256: ref.path ? await fileSha256(safeRepoPath(ref.path)) : "" });
  }
  return rows;
}

function buildSearchIndex(data) {
  const rows = [];
  for (const project of data.projects || []) rows.push({ kind: "project", id: project.id || "", title: project.name || "", path: project.readme || "", text: [project.name || "", project.summary || "", project.status || ""].join(" ") });
  for (const milestone of data.milestones || []) rows.push({ kind: "milestone", id: milestone.id || "", title: milestone.title || "", path: milestone.path || "", text: JSON.stringify(milestone) });
  for (const task of data.tasks || []) rows.push({ kind: "task", id: task.id || "", title: task.title || "", path: task.path || "", text: JSON.stringify(task) });
  for (const doc of data.docs || []) rows.push({ kind: "doc", id: doc.id || "", title: doc.title || "", path: doc.path || "", text: [doc.title || "", doc.type || "", doc.owner || "", doc.search_text || ""].join(" ") });
  for (const asset of data.assets || []) rows.push({ kind: "asset", id: asset.id || "", title: asset.title || "", path: asset.path || "", text: JSON.stringify(asset) });
  for (const event of data.events || []) rows.push({ kind: "event", id: event.id || "", title: event.event_type || "", path: "events/task-events.jsonl", text: JSON.stringify(event) });
  for (const review of data.reviews || []) rows.push({ kind: "review", id: review.id || "", title: review.decision || "", path: "reviews/task-reviews.jsonl", text: JSON.stringify(review) });
  return rows;
}

function latestAttempts(events) {
  const latest = {};
  for (const event of events || []) {
    if (ATTEMPT_EVENT_TYPES.has(event.event_type) && event.task_id) latest[event.task_id] = event;
  }
  return latest;
}

function buildReviewQueue(tasks, events, reviews) {
  const latestByTask = latestAttempts(events);
  const latestReviewByTask = {};
  for (const review of reviews || []) {
    if (review.task_id) latestReviewByTask[review.task_id] = review;
  }
  const now = Date.now();
  const rows = [];
  for (const task of tasks || []) {
    const latest = latestByTask[task.id] || {};
    const reasons = [];
    let ageDays = null;
    if (latest.created_at) {
      const time = Date.parse(latest.created_at);
      if (!Number.isNaN(time)) ageDays = Math.max(0, Math.floor((now - time) / 86400000));
    }
    if (task.status === "In Review") {
      reasons.push("in_review");
      if (ageDays !== null && ageDays >= 3) reasons.push("stale_review");
    }
    if (latest.event_type === "verification_failed") reasons.push("verification_failed");
    if (latest.event_type === "output_withdrawn") reasons.push("output_withdrawn");
    if (latest.event_type === "review_cancelled") reasons.push("review_cancelled");
    if (reasons.length) {
      rows.push({
        task_id: task.id || "",
        title: task.title || "",
        assigned_to: task.assigned_to || "",
        reviewer: task.reviewer || "",
        status: task.status || "",
        output: task.output || "",
        reasons,
        age_days: ageDays,
        latest_attempt: latest,
        latest_review: latestReviewByTask[task.id] || {}
      });
    }
  }
  return rows;
}

function openTasks(tasks) {
  return (tasks || []).filter((task) => !HISTORICAL_TASK_STATUSES.has(task.status || ""));
}

function blockedTasks(tasks) {
  return (tasks || []).filter((task) => task.status === "Blocked" || task.blocker);
}

function staleWork(tasks, events, days = 3) {
  const latestByTask = {};
  for (const event of events || []) {
    if (event.task_id) latestByTask[event.task_id] = event;
  }
  const now = Date.now();
  return openTasks(tasks).map((task) => {
    const latest = latestByTask[task.id] || {};
    let ageDays = null;
    if (latest.created_at) {
      const time = Date.parse(latest.created_at);
      if (!Number.isNaN(time)) ageDays = Math.max(0, Math.floor((now - time) / 86400000));
    }
    return { ...task, latest_event: latest, age_days: ageDays };
  }).filter((task) => task.age_days === null || task.age_days >= days);
}

function featureProposals(docs) {
  return (docs || []).filter((doc) => ["feature-proposal", "feature-brief"].includes(doc.type || "") && ["draft", "live", "review"].includes(doc.status || "draft"));
}

function repoStateUnknown(tasks, registry) {
  const outputLabels = ["pull request", "merge request", "implementation pr", "implementation mr", "commit"];
  const rows = [];
  for (const task of openTasks(tasks || [])) {
    const expected = String(task.expected_output || "").toLowerCase();
    const targetRepo = task.target_repo || "";
    const needsRepo = Boolean(targetRepo) || outputLabels.some((label) => expected.includes(label));
    if (!needsRepo) continue;
    const project = registry.projects?.[task.project_id] || {};
    const reasons = [];
    if (!targetRepo) reasons.push("missing_target_repo");
    else if (!projectRepoMatches(project, targetRepo)) reasons.push("target_repo_not_registered");
    if (task.status === "In Review" && task.output && targetRepo && !task.output_commit) reasons.push("missing_output_commit");
    if (reasons.length) {
      rows.push({ task_id: task.id || "", project_id: task.project_id || "", title: task.title || "", assigned_to: task.assigned_to || "", reviewer: task.reviewer || "", status: task.status || "", target_repo: targetRepo, output: task.output || "", output_commit: task.output_commit || "", reasons });
    }
  }
  return rows;
}

function projectStatusSummary(data) {
  return {
    counts: {
      projects: (data.projects || []).length,
      docs: (data.docs || []).length,
      tasks: (data.tasks || []).length,
      open_tasks: openTasks(data.tasks).length,
      blocked_tasks: blockedTasks(data.tasks).length,
      review_queue: (data.review_queue || []).length,
      stale_work: (data.stale_work || []).length,
      feature_proposals: (data.feature_proposals || []).length,
      repo_state_unknown: (data.repo_state_unknown || []).length,
      validation_issues: (data.validation?.issues || []).length
    }
  };
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
  const events = await readJsonl("events/task-events.jsonl");
  const reviews = await readJsonl("reviews/task-reviews.jsonl");
  const tasks = await collectTasks(registry);
  const docs = await collectDocs(registry);
  const data = {
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
    milestones: await collectMilestones(registry),
    docs,
    tasks,
    assets: Object.entries(registry.assets || {}).map(([id, value]) => ({ id, ...value })),
    people: registry.people || [],
    events,
    reviews,
    latest_attempts: latestAttempts(events),
    review_queue: buildReviewQueue(tasks, events, reviews),
    blocked_tasks: blockedTasks(tasks),
    stale_work: staleWork(tasks, events),
    feature_proposals: featureProposals(docs),
    repo_state_unknown: repoStateUnknown(tasks, registry),
    validation: { issues }
  };
  data.project_status = projectStatusSummary(data);
  data.search_index = buildSearchIndex(data);
  return data;
}

function createTaskPayload(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const taskId = allocateId(registry, "task");
  const taskFolder = `projects/${projectFolder(payload.project_id, project.name)}/tasks/${taskId}`;
  const taskPath = `${taskFolder}/task.yaml`;
  const task = { id: taskId, project_id: payload.project_id, title: payload.title || "", assigned_to: payload.assigned_to || "", role: payload.role || "", status: "Backlog", checkpoint: "Drafting", priority: "Medium", deadline: "", milestone: "", feature_area: "", release_target: "", estimate: "", risk: "", reviewer: "", expected_output: payload.expected_output || "", acceptance_criteria: [], dependencies: [], target_repo: payload.target_repo || "", output: "", output_commit: "", blocker: "", ai_update: "", user_update: "", artifacts: { notes: `${taskFolder}/notes.md`, outputs: `${taskFolder}/outputs.md`, attachments: `${taskFolder}/attachments/` } };
  registry.tasks[taskId] = { project_id: payload.project_id, path: taskPath, folder: taskFolder, title: task.title, assigned_to: task.assigned_to, status: "Backlog", milestone: "", feature_area: "", expected_output: task.expected_output, target_repo: task.target_repo, output_commit: "" };
  return { taskId, taskPath, task };
}

function taskSupportFiles(taskPath, task) {
  const folder = taskFolderFromPath(taskPath);
  const taskId = task.id || "TASK#";
  const title = task.title || "Task";
  return {
    [`${folder}/notes.md`]: `# ${taskId} Notes - ${title}\n\n## Context\n\nLink relevant docs, decisions, assets, repos, and prior discussion.\n\n## Working Notes\n\nUse this for task-local notes that should travel with the task.\n`,
    [`${folder}/outputs.md`]: `# ${taskId} Outputs - ${title}\n\n## Submitted Output\n\nLink the PR/MR, build, asset, report, document, capture, or release package.\n\n## Verification Notes\n\nRecord objective checks and reviewer observations.\n`,
    [`${folder}/attachments/README.md`]: `# ${taskId} Attachments\n\nStore only small task-local references here. Large files should use Git LFS, releases/packages, object storage, or implementation repos, then be registered in the asset manifest.\n`
  };
}

function createMilestonePayload(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const milestoneId = allocateId(registry, "milestone");
  const rel = `projects/${projectFolder(payload.project_id, project.name)}/planning/milestones/${milestoneId}.yaml`;
  const milestone = { id: milestoneId, project_id: payload.project_id, title: payload.title || "", owner: payload.owner || "", status: payload.status || "Planned", start: "", target: "", goals: [], scope: [], exit_criteria: [], risks: [], linked_tasks: [], linked_docs: [] };
  registry.milestones ||= {};
  registry.milestones[milestoneId] = { project_id: payload.project_id, path: rel, title: milestone.title, owner: milestone.owner, status: milestone.status };
  project.milestones ||= [];
  project.milestones.push(milestoneId);
  return { milestoneId, rel, milestone, project };
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

function createFeatureProposalPayload(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const docId = allocateId(registry, "doc");
  const rel = `projects/${projectFolder(payload.project_id, project.name)}/docs/proposals/${docId}-${slugify(payload.title || "feature-proposal")}.md`;
  const body = `## Problem\n\n${payload.problem || "TBD"}\n\n## Player/User Value\n\n${payload.value || "TBD"}\n\n## Proposed Scope\n\n${payload.scope || "TBD"}\n\n## Non-Goals\n\n${payload.non_goals || "TBD"}\n\n## Risks\n\n${payload.risks || "TBD"}\n\n## Task Breakdown\n\n${payload.task_breakdown || "TBD"}\n\n## Decision Needed\n\n${payload.decision_needed || "Approve, reject, or defer this feature proposal."}\n`;
  const text = `---\nid: ${docId}\nproject_id: ${payload.project_id}\ntype: feature-proposal\nowner: ${payload.owner || ""}\nstatus: review\n---\n\n# ${docId} - ${payload.title || "Feature Proposal"}\n\n${body}`;
  registry.docs[docId] = { project_id: payload.project_id, doc_type: "feature-proposal", title: payload.title || "", owner: payload.owner || "", path: rel, status: "review" };
  return { docId, rel, text };
}

function historicalEditReason(registry, relPath) {
  const clean = String(relPath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (["events/task-events.jsonl", "reviews/task-reviews.jsonl"].includes(clean)) return `${clean} is append-only; use add event or review task`;
  for (const [taskId, ref] of Object.entries(registry.tasks || {})) {
    if (ref.path === clean && HISTORICAL_TASK_STATUSES.has(ref.status || "")) return `${taskId} is ${ref.status}; completed task records are historical`;
  }
  for (const [docId, doc] of Object.entries(registry.docs || {})) {
    if (doc.path === clean && HISTORICAL_DOC_STATUSES.has(doc.status || "draft")) return `${docId} is ${doc.status}; finalized docs are historical`;
  }
  return "";
}

function ensureEditAllowed(registry, relPath, payload) {
  const reason = historicalEditReason(registry, relPath);
  if (reason && !payload.allow_historical_edit) throw new Error(`refusing to edit historical record: ${reason}. Create a project note, decision, or errata instead.`);
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
  registry.tasks[taskId] = { project_id: task.project_id || "", path: taskPath, folder: taskFolderFromPath(taskPath), title: task.title || "", assigned_to: task.assigned_to || "", status: task.status || "Backlog", milestone: task.milestone || "", feature_area: task.feature_area || "", expected_output: task.expected_output || "", target_repo: task.target_repo || "", output_commit: task.output_commit || "" };
}

function makeEvent(registry, task, actor, eventType, message, extra = {}) {
  const eventId = allocateId(registry, "event");
  const record = { id: eventId, task_id: task.id || "", project_id: task.project_id || "", actor: actor || "Unknown", event_type: eventType || "update", message: message || "", created_at: nowIso() };
  for (const [key, value] of Object.entries(extra || {})) {
    if (value !== undefined && value !== null) record[key] = value;
  }
  return record;
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
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to update ${taskId}; ${task.status} tasks are historical. Use review workflow or create a project note/decision for later context.`);
  if (payload.commit && !payload.output_commit) payload.output_commit = payload.commit;
  for (const field of ["status", "checkpoint", "priority", "assigned_to", "deadline", "milestone", "feature_area", "release_target", "estimate", "risk", "reviewer", "expected_output", "target_repo", "output", "output_commit", "blocker", "ai_update", "user_update"]) {
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
  if (payload.commit && !payload.output_commit) payload.output_commit = payload.commit;
  const result = await updateTaskActions(registry, { ...payload, status: payload.status || "In Review", checkpoint: payload.checkpoint || "Review", suppress_event: true });
  const { task } = await loadTaskRecord(registry, payload.task_id || "");
  const event = makeEvent(registry, { ...task, id: payload.task_id }, payload.actor || "", "submitted_output", payload.message || payload.output || `Submitted output for ${payload.task_id}`, { output: payload.output || "", target_repo: task.target_repo || "", output_commit: task.output_commit || "" });
  result.actions[0].content = dump(registry);
  result.actions.push(await eventAction(event));
  result.title = result.title.replace("Update", "Submit output for");
  result.message = event.message;
  return result;
}

async function reviewTaskActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to review ${taskId}; ${task.status} tasks are historical. Create a follow-up task, decision, project note, or errata instead.`);
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
  const eventType = decision === "verification_failed" ? "verification_failed" : decision === "cancelled" ? "review_cancelled" : `review_${decision}`;
  const event = makeEvent(registry, task, payload.reviewer || "", eventType, payload.notes || `${decision} review for ${taskId}`, { review_id: review.id, decision, output: task.output || "", target_repo: task.target_repo || "", output_commit: task.output_commit || "" });
  return { title: `Review ${taskId}: ${decision}`, message: event.message, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await reviewAction(review), await eventAction(event)] };
}

async function recordAttemptActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to record a new attempt for ${taskId}; ${task.status} tasks are historical. Reopen through review workflow or create a follow-up task.`);
  const output = payload.output || "";
  task.status = "In Review";
  task.checkpoint = "Review";
  if (payload.target_repo) task.target_repo = payload.target_repo;
  const outputCommit = payload.output_commit || payload.commit || "";
  if (outputCommit) task.output_commit = outputCommit;
  if (output) task.output = output;
  const message = payload.message || output || `Output attempt recorded for ${taskId}`;
  task.user_update = message;
  syncTaskRef(registry, taskId, taskPath, task);
  const event = makeEvent(registry, task, payload.actor || "", "output_attempted", message, { output: output || task.output || "", target_repo: task.target_repo || "", output_commit: task.output_commit || "" });
  return { title: `Record attempt for ${taskId}`, message, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await eventAction(event)] };
}

async function recordVerificationFailedActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to record failed verification for ${taskId}; ${task.status} tasks are historical. Create a follow-up task, decision, project note, or errata instead.`);
  const reason = payload.reason || payload.notes || "Output could not be objectively verified.";
  task.status = "In Progress";
  task.checkpoint = "Revising";
  task.user_update = `Verification failed: ${reason}`;
  syncTaskRef(registry, taskId, taskPath, task);
  const reviewId = allocateId(registry, "review");
  const review = { id: reviewId, task_id: taskId, project_id: task.project_id || "", reviewer: payload.reviewer || "", decision: "verification_failed", notes: reason, created_at: nowIso() };
  const event = makeEvent(registry, task, payload.reviewer || "", "verification_failed", reason, { review_id: reviewId, decision: "verification_failed", output: payload.output || task.output || "", target_repo: task.target_repo || "", output_commit: task.output_commit || "" });
  return { title: `Verification failed for ${taskId}`, message: reason, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await reviewAction(review), await eventAction(event)] };
}

async function withdrawOutputActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to withdraw output for ${taskId}; ${task.status} tasks are historical. Create a follow-up task, decision, project note, or errata instead.`);
  const reason = payload.reason || "Output withdrawn.";
  const previousOutput = payload.output || task.output || "";
  task.status = "In Progress";
  task.checkpoint = "Revising";
  task.output = "";
  task.user_update = `Output withdrawn: ${reason}`;
  syncTaskRef(registry, taskId, taskPath, task);
  const event = makeEvent(registry, task, payload.actor || "", "output_withdrawn", reason, { previous_output: previousOutput });
  return { title: `Withdraw output for ${taskId}`, message: reason, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await eventAction(event)] };
}

async function supersedeOutputActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to supersede output for ${taskId}; ${task.status} tasks are historical. Create a follow-up task, decision, project note, or errata instead.`);
  const newOutput = payload.new_output || payload.output || "";
  if (!newOutput) throw new Error("supersede_output requires new_output");
  const reason = payload.reason || "Output superseded.";
  const oldOutput = payload.old_output || task.output || "";
  task.status = "In Review";
  task.checkpoint = "Review";
  task.output = newOutput;
  task.user_update = `Output superseded: ${reason}`;
  syncTaskRef(registry, taskId, taskPath, task);
  const event = makeEvent(registry, task, payload.actor || "", "output_superseded", reason, { old_output: oldOutput, new_output: newOutput });
  return { title: `Supersede output for ${taskId}`, message: reason, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await eventAction(event)] };
}

async function cancelReviewActions(registry, payload) {
  const taskId = payload.task_id || "";
  const { path: taskPath, task } = await loadTaskRecord(registry, taskId);
  if (HISTORICAL_TASK_STATUSES.has(task.status || "") && !payload.allow_historical_edit) throw new Error(`refusing to cancel review for ${taskId}; ${task.status} tasks are historical. Create a follow-up task, decision, project note, or errata instead.`);
  const reason = payload.reason || payload.notes || "Review cancelled.";
  const actor = payload.actor || payload.reviewer || "";
  task.status = "In Progress";
  task.checkpoint = "Revising";
  task.user_update = `Review cancelled: ${reason}`;
  syncTaskRef(registry, taskId, taskPath, task);
  const reviewId = allocateId(registry, "review");
  const review = { id: reviewId, task_id: taskId, project_id: task.project_id || "", reviewer: actor, decision: "cancelled", notes: reason, created_at: nowIso() };
  const event = makeEvent(registry, task, actor, "review_cancelled", reason, { review_id: reviewId, output: task.output || "" });
  return { title: `Cancel review for ${taskId}`, message: reason, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: taskPath, content: dump(task) }, await reviewAction(review), await eventAction(event)] };
}

async function registerRepoActions(registry, payload) {
  const project = registry.projects?.[payload.project_id];
  if (!project) throw new Error(`missing project ${payload.project_id}`);
  const name = String(payload.name || "").trim();
  const url = String(payload.url || "").trim();
  if (!name) throw new Error("register_repo requires name");
  if (!url) throw new Error("register_repo requires url");
  const repoLink = { name, provider: String(payload.provider || "github").trim() || "github", url, default_branch: String(payload.default_branch || "main").trim() || "main", role: String(payload.role || "").trim() };
  project.repos ||= [];
  project.repos = project.repos.filter((row) => normalizeRepoRef(row.name || "") !== normalizeRepoRef(name));
  project.repos.push(repoLink);
  registry.projects[payload.project_id] = project;
  const title = `Register repo ${name} for ${payload.project_id}`;
  return { title, message: title, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: project.path, content: dump(project) }] };
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
    ensureEditAllowed(await loadRegistry(), filePath, payload);
    const baseSha = payload.base_sha256 || payload.base_sha;
    if (baseSha && existsSync(full) && (await fileSha256(full)) !== baseSha) throw new Error(`stale edit for ${filePath}: base_sha256 does not match current file`);
    return { title: payload.message || `Edit ${filePath}`, message: payload.message || `Edit ${filePath}`, actions: [{ action: existsSync(full) ? "update" : "create", file_path: filePath, content: payload.content || "" }] };
  }
  if (payload.type === "create_task") {
    const registry = await loadRegistry();
    const { taskId, taskPath, task } = createTaskPayload(registry, payload);
    const title = `Create ${taskId}: ${payload.title || ""}`;
    const actions = [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "create", file_path: taskPath, content: dump(task) }];
    for (const [rel, content] of Object.entries(taskSupportFiles(taskPath, task))) actions.push({ action: "create", file_path: rel, content });
    return { title, message: title, actions };
  }
  if (payload.type === "create_milestone") {
    const registry = await loadRegistry();
    const { milestoneId, rel, milestone, project } = createMilestonePayload(registry, payload);
    const actions = [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "update", file_path: project.path, content: dump(project) }, { action: "create", file_path: rel, content: dump(milestone) }];
    if (project.roadmap) {
      const roadmap = await readJsonSubset(safeRepoPath(project.roadmap), { project_id: project.id, milestones: [] });
      roadmap.milestones ||= [];
      roadmap.milestones.push(milestoneId);
      actions.push({ action: "update", file_path: project.roadmap, content: dump(roadmap) });
    }
    const title = `Create ${milestoneId}: ${payload.title || ""}`;
    return { title, message: title, actions };
  }
  if (payload.type === "create_doc") {
    const registry = await loadRegistry();
    const { docId, rel, text } = createDocPayload(registry, payload);
    const title = `Create ${docId}: ${payload.title || ""}`;
    return { title, message: title, actions: [{ action: "update", file_path: "registry.yaml", content: dump(registry) }, { action: "create", file_path: rel, content: text }] };
  }
  if (payload.type === "propose_feature") {
    const registry = await loadRegistry();
    const { docId, rel, text } = createFeatureProposalPayload(registry, payload);
    const title = `Propose feature ${docId}: ${payload.title || ""}`;
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
  if (payload.type === "record_attempt") {
    return recordAttemptActions(await loadRegistry(), payload);
  }
  if (payload.type === "record_verification_failed") {
    return recordVerificationFailedActions(await loadRegistry(), payload);
  }
  if (payload.type === "withdraw_output") {
    return withdrawOutputActions(await loadRegistry(), payload);
  }
  if (payload.type === "supersede_output") {
    return supersedeOutputActions(await loadRegistry(), payload);
  }
  if (payload.type === "cancel_review") {
    return cancelReviewActions(await loadRegistry(), payload);
  }
  if (payload.type === "register_repo") {
    return registerRepoActions(await loadRegistry(), payload);
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
