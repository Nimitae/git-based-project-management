const state = {
  data: null,
  query: "",
  status: "",
  myWorkOwner: ""
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}

function statusClass(status) {
  const value = (status || "").toLowerCase();
  if (value.includes("blocked")) return "blocked";
  if (value.includes("review")) return "progress";
  if (value.includes("verified")) return "verified";
  if (value.includes("done")) return "done";
  if (value.includes("progress")) return "progress";
  return "";
}

function matchesQuery(item) {
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  return JSON.stringify(item).toLowerCase().includes(query);
}

function filteredTasks() {
  if (!state.data) return [];
  return state.data.tasks.filter((task) => {
    const statusOk = !state.status || task.status === state.status;
    return statusOk && matchesQuery(task);
  });
}

function renderTasksTable() {
  const tasks = filteredTasks().slice(0, 18);
  $("taskResultCount").textContent = `${filteredTasks().length} shown`;
  $("taskRows").innerHTML = tasks.map((task) => `
    <tr>
      <td><strong>${escapeHtml(task.id)}</strong></td>
      <td>${escapeHtml(task.title || "")}<br><small>${escapeHtml(task.project_name || "")}</small></td>
      <td>${escapeHtml(task.assigned_to || "")}</td>
      <td><span class="badge ${statusClass(task.status)}">${escapeHtml(task.status || "Backlog")}</span></td>
      <td>${escapeHtml(task.expected_output || "")}</td>
    </tr>
  `).join("") || `<tr><td colspan="5">No matching tasks.</td></tr>`;
}

function renderTaskBoard() {
  const tasks = filteredTasks();
  $("taskBoard").innerHTML = tasks.map((task) => `
    <article class="task-card">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "Untitled task")}</strong>
      <span>${escapeHtml(task.assigned_to || "Unassigned")} / ${escapeHtml(task.expected_output || "No expected output")}</span>
      <p><span class="badge ${statusClass(task.status)}">${escapeHtml(task.status || "Backlog")}</span></p>
    </article>
  `).join("") || `<div class="task-card"><strong>No tasks</strong><span>Adjust search or filters.</span></div>`;
}

function renderDocs() {
  const docs = state.data ? state.data.docs.filter(matchesQuery) : [];
  $("docList").innerHTML = docs.map((doc) => `
    <article class="doc-row">
      <strong>${escapeHtml(doc.id)} - ${escapeHtml(doc.title || doc.type)}</strong>
      <span>${escapeHtml(doc.path)}${doc.sha256 ? ` / ${escapeHtml(doc.sha256.slice(0, 12))}` : ""}</span>
    </article>
  `).join("") || `<div class="doc-row"><strong>No docs found</strong><span>Run compile or initialize the repo.</span></div>`;
}

function renderAssets() {
  const assets = state.data ? (state.data.assets || []).filter(matchesQuery) : [];
  $("assetList").innerHTML = assets.map((asset) => `
    <article class="doc-row">
      <strong>${escapeHtml(asset.id)} - ${escapeHtml(asset.title || asset.type)}</strong>
      <span>${escapeHtml(asset.type || "asset")} / ${escapeHtml(asset.owner || "Unowned")} / ${escapeHtml(asset.source_url || asset.path || "No link")}</span>
    </article>
  `).join("") || `<div class="doc-row"><strong>No assets found</strong><span>Register mockups, videos, builds, art, and external files.</span></div>`;
}

function renderEvents() {
  const events = state.data ? state.data.events.slice(-8).reverse() : [];
  $("eventList").innerHTML = events.map((event) => `
    <article class="event">
      <strong>${escapeHtml(event.task_id || "")} ${escapeHtml(event.event_type || "event")}</strong>
      <span>${escapeHtml(event.actor || "system")} / ${escapeHtml(event.created_at || "")}</span>
      <p>${escapeHtml(event.message || "")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No recent events</strong><span>Task activity will appear here.</span></div>`;
}

function renderReviewQueue() {
  const queue = state.data ? (state.data.review_queue || []) : [];
  $("reviewQueueList").innerHTML = queue.map((item) => `
    <article class="event">
      <strong>${escapeHtml(item.task_id || "")} ${escapeHtml((item.reasons || []).join(", "))}</strong>
      <span>${escapeHtml(item.assigned_to || "Unassigned")} / ${escapeHtml(item.reviewer || "No reviewer")} / ${escapeHtml(item.status || "")}</span>
      <p>${escapeHtml(item.title || "")}${item.output ? ` / ${escapeHtml(item.output)}` : ""}</p>
    </article>
  `).join("") || `<div class="event"><strong>No review queue items</strong><span>Submitted, failed, withdrawn, and cancelled reviews will appear here.</span></div>`;
}

function renderMyWork() {
  const owner = state.myWorkOwner.trim().toLowerCase();
  const tasks = state.data ? state.data.tasks.filter((task) => {
    if (!owner) return !["Done", "Verified", "Iceboxed"].includes(task.status);
    return [task.assigned_to, task.reviewer].some((value) => String(value || "").toLowerCase() === owner) && !["Done", "Verified", "Iceboxed"].includes(task.status);
  }) : [];
  $("myWorkList").innerHTML = tasks.map((task) => `
    <article class="task-card">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "Untitled task")}</strong>
      <span>${escapeHtml(task.assigned_to || "Unassigned")} / ${escapeHtml(task.status || "Backlog")} / ${escapeHtml(task.expected_output || "No expected output")}</span>
      <p>${escapeHtml(task.user_update || task.blocker || task.path || "")}</p>
    </article>
  `).join("") || `<div class="task-card"><strong>No matching work</strong><span>Enter an assignee or reviewer name.</span></div>`;
}

function renderHealth() {
  const blocked = state.data ? (state.data.blocked_tasks || []) : [];
  $("blockedTaskList").innerHTML = blocked.map((task) => `
    <article class="event">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "")}</strong>
      <span>${escapeHtml(task.assigned_to || "Unassigned")} / ${escapeHtml(task.status || "")}</span>
      <p>${escapeHtml(task.blocker || task.user_update || "No blocker detail")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No blocked tasks</strong><span>Blocked tasks with blocker text will appear here.</span></div>`;

  const stale = state.data ? (state.data.stale_work || []) : [];
  $("staleWorkList").innerHTML = stale.map((task) => `
    <article class="event">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "")}</strong>
      <span>${escapeHtml(task.assigned_to || "Unassigned")} / ${escapeHtml(task.status || "")} / ${task.age_days === null ? "no events" : `${escapeHtml(task.age_days)} days`}</span>
      <p>${escapeHtml(task.latest_event?.message || task.user_update || task.path || "")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No stale work</strong><span>Open tasks without recent events will appear here.</span></div>`;

  const features = state.data ? (state.data.feature_proposals || []) : [];
  $("featureProposalList").innerHTML = features.map((doc) => `
    <article class="doc-row">
      <strong>${escapeHtml(doc.id)} - ${escapeHtml(doc.title || "Feature proposal")}</strong>
      <span>${escapeHtml(doc.status || "draft")} / ${escapeHtml(doc.owner || "Unowned")} / ${escapeHtml(doc.path || "")}</span>
    </article>
  `).join("") || `<div class="doc-row"><strong>No active feature proposals</strong><span>Use Create > Feature Proposal PR/MR to start one.</span></div>`;
}

function renderSummary() {
  const data = state.data;
  if (!data) return;
  $("repoLabel").textContent = data.repo_name || "Project Hub";
  $("sourceMode").textContent = data.github_repo || data.gitlab_project || "Git local";
  $("generatedAt").textContent = data.generated_at || "";
  $("summaryLine").textContent = `${data.projects.length} projects, ${data.docs.length} docs, ${data.tasks.length} tasks, ${(data.assets || []).length} assets`;
  $("projectCount").textContent = data.projects.length;
  $("docCount").textContent = data.docs.length;
  $("assetCount").textContent = (data.assets || []).length;
  $("openTaskCount").textContent = data.tasks.filter((task) => !["Done", "Verified", "Iceboxed"].includes(task.status)).length;
  $("issueCount").textContent = data.validation.issues.length;
}

function render() {
  renderSummary();
  renderTasksTable();
  renderTaskBoard();
  renderDocs();
  renderAssets();
  renderEvents();
  renderReviewQueue();
  renderMyWork();
  renderHealth();
}

async function loadData() {
  const response = await fetch("/api/data");
  state.data = await response.json();
  render();
}

async function submitProposal(payload) {
  const response = await fetch("/api/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  $("proposalResult").textContent = JSON.stringify(result, null, 2);
}

async function submitUpdate(payload) {
  const response = await fetch("/api/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  $("updateResult").textContent = JSON.stringify(result, null, 2);
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    $(`${button.dataset.view}View`).classList.add("active");
  });
});

$("refreshButton").addEventListener("click", loadData);
$("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});
$("statusFilter").addEventListener("change", (event) => {
  state.status = event.target.value;
  render();
});
$("myWorkOwner").addEventListener("input", (event) => {
  state.myWorkOwner = event.target.value;
  renderMyWork();
});

$("createTaskForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "create_task",
    project_id: form.get("project_id"),
    title: form.get("title"),
    assigned_to: form.get("assigned_to"),
    role: form.get("role"),
    expected_output: form.get("expected_output")
  });
});

$("createDocForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "create_doc",
    project_id: form.get("project_id"),
    title: form.get("title"),
    owner: form.get("owner"),
    doc_type: form.get("doc_type")
  });
});

$("featureProposalForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "propose_feature",
    project_id: form.get("project_id"),
    title: form.get("title"),
    owner: form.get("owner"),
    problem: form.get("problem"),
    value: form.get("value"),
    scope: form.get("scope"),
    non_goals: form.get("non_goals"),
    risks: form.get("risks"),
    task_breakdown: form.get("task_breakdown"),
    decision_needed: form.get("decision_needed")
  });
});

$("createMilestoneForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "create_milestone",
    project_id: form.get("project_id"),
    title: form.get("title"),
    owner: form.get("owner"),
    status: form.get("status")
  });
});

$("registerAssetForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "register_asset",
    project_id: form.get("project_id"),
    title: form.get("title"),
    asset_type: form.get("asset_type"),
    storage: form.get("storage"),
    path: form.get("path"),
    source_url: form.get("source_url"),
    used_by: form.get("used_by"),
    owner: form.get("owner")
  });
});

$("editFileForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "edit_file",
    path: form.get("path"),
    content: form.get("content"),
    message: form.get("message"),
    base_sha256: form.get("base_sha256")
  });
});

$("updateTaskForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "update_task",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    status: form.get("status"),
    checkpoint: form.get("checkpoint"),
    output: form.get("output"),
    blocker: form.get("blocker"),
    milestone: form.get("milestone"),
    feature_area: form.get("feature_area"),
    reviewer: form.get("reviewer"),
    user_update: form.get("user_update")
  });
});

$("submitOutputForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "submit_output",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    output: form.get("output"),
    message: form.get("message")
  });
});

$("reviewTaskForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "review_task",
    task_id: form.get("task_id"),
    reviewer: form.get("reviewer"),
    decision: form.get("decision"),
    notes: form.get("notes")
  });
});

$("recordAttemptForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "record_attempt",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    output: form.get("output"),
    message: form.get("message")
  });
});

$("verificationFailedForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "record_verification_failed",
    task_id: form.get("task_id"),
    reviewer: form.get("reviewer"),
    output: form.get("output"),
    reason: form.get("reason")
  });
});

$("withdrawOutputForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "withdraw_output",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    output: form.get("output"),
    reason: form.get("reason")
  });
});

$("supersedeOutputForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "supersede_output",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    old_output: form.get("old_output"),
    new_output: form.get("new_output"),
    reason: form.get("reason")
  });
});

$("cancelReviewForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "cancel_review",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    reason: form.get("reason")
  });
});

$("addEventForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitUpdate({
    type: "add_event",
    task_id: form.get("task_id"),
    actor: form.get("actor"),
    event_type: form.get("event_type"),
    message: form.get("message")
  });
});

loadData().catch((error) => {
  $("summaryLine").textContent = `Unable to load Project Hub data: ${error.message}`;
});
