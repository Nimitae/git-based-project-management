const state = {
  data: null,
  query: "",
  status: ""
};

const $ = (id) => document.getElementById(id);

function statusClass(status) {
  const value = (status || "").toLowerCase();
  if (value.includes("blocked")) return "blocked";
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
      <td><strong>${task.id}</strong></td>
      <td>${task.title || ""}<br><small>${task.project_name || ""} / ${task.ew_name || ""}</small></td>
      <td>${task.assigned_to || ""}</td>
      <td><span class="badge ${statusClass(task.status)}">${task.status || "Backlog"}</span></td>
      <td>${task.expected_output || ""}</td>
    </tr>
  `).join("") || `<tr><td colspan="5">No matching tasks.</td></tr>`;
}

function renderTaskBoard() {
  const tasks = filteredTasks();
  $("taskBoard").innerHTML = tasks.map((task) => `
    <article class="task-card">
      <strong>${task.id} - ${task.title || "Untitled task"}</strong>
      <span>${task.assigned_to || "Unassigned"} / ${task.expected_output || "No expected output"}</span>
      <p><span class="badge ${statusClass(task.status)}">${task.status || "Backlog"}</span></p>
    </article>
  `).join("") || `<div class="task-card"><strong>No tasks</strong><span>Adjust search or filters.</span></div>`;
}

function renderDocs() {
  const docs = state.data ? state.data.docs.filter(matchesQuery) : [];
  $("docList").innerHTML = docs.map((doc) => `
    <article class="doc-row">
      <strong>${doc.id} - ${doc.title || doc.type}</strong>
      <span>${doc.path}</span>
    </article>
  `).join("") || `<div class="doc-row"><strong>No docs found</strong><span>Run compile or initialize the repo.</span></div>`;
}

function renderEvents() {
  const events = state.data ? state.data.events.slice(-8).reverse() : [];
  $("eventList").innerHTML = events.map((event) => `
    <article class="event">
      <strong>${event.task_id || ""} ${event.event_type || "event"}</strong>
      <span>${event.actor || "system"} / ${event.created_at || ""}</span>
      <p>${event.message || ""}</p>
    </article>
  `).join("") || `<div class="event"><strong>No recent events</strong><span>Task activity will appear here.</span></div>`;
}

function renderSummary() {
  const data = state.data;
  if (!data) return;
  $("repoLabel").textContent = data.repo_name || "Project OS";
  $("sourceMode").textContent = data.gitlab_project || "Git local";
  $("generatedAt").textContent = data.generated_at || "";
  $("summaryLine").textContent = `${data.projects.length} projects, ${data.ews.length} workstreams, ${data.tasks.length} tasks`;
  $("projectCount").textContent = data.projects.length;
  $("ewCount").textContent = data.ews.length;
  $("openTaskCount").textContent = data.tasks.filter((task) => !["Done", "Verified", "Iceboxed"].includes(task.status)).length;
  $("issueCount").textContent = data.validation.issues.length;
}

function render() {
  renderSummary();
  renderTasksTable();
  renderTaskBoard();
  renderDocs();
  renderEvents();
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

$("createTaskForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "create_task",
    ew_id: form.get("ew_id"),
    title: form.get("title"),
    assigned_to: form.get("assigned_to"),
    role: form.get("role"),
    expected_output: form.get("expected_output")
  });
});

$("editFileForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "edit_file",
    path: form.get("path"),
    content: form.get("content"),
    message: form.get("message")
  });
});

loadData().catch((error) => {
  $("summaryLine").textContent = `Unable to load Project OS data: ${error.message}`;
});
