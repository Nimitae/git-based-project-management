const state = {
  data: null,
  query: "",
  status: "",
  myWorkOwner: "",
  selectedTaskId: "",
  selectedDocId: ""
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

function people() {
  return state.data ? (state.data.people || []) : [];
}

function taskById(taskId) {
  return (state.data?.tasks || []).find((task) => task.id === taskId) || null;
}

function docById(docId) {
  return (state.data?.docs || []).find((doc) => doc.id === docId) || null;
}

function personLabel(value) {
  const clean = String(value || "").trim();
  if (!clean) return "";
  const lower = clean.toLowerCase();
  const person = people().find((item) => {
    const email = String(item.email || "").toLowerCase();
    const name = String(item.name || "").toLowerCase();
    return lower === email || lower === name || lower === `${name} <${email}>`;
  });
  if (!person) return clean;
  return person.email ? `${person.name || person.email} <${person.email}>` : (person.name || clean);
}

function identityValues(value) {
  const clean = String(value || "").trim();
  if (!clean) return new Set();
  const lower = clean.toLowerCase();
  const values = new Set([lower]);
  const emailMatch = /<([^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>/.exec(clean) || (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(clean) ? [clean, clean] : null);
  if (emailMatch) values.add(emailMatch[1].toLowerCase());
  for (const person of people()) {
    const email = String(person.email || "").toLowerCase();
    const name = String(person.name || "").toLowerCase();
    if (lower === email || lower === name || lower === `${name} <${email}>`) {
      if (email) values.add(email);
      if (name) values.add(name);
    }
  }
  return values;
}

function identityMatches(candidate, query) {
  const queryValues = identityValues(query);
  if (!queryValues.size) return true;
  const candidateValues = identityValues(candidate);
  return [...queryValues].some((value) => candidateValues.has(value));
}

function taskOwnerLabel(task) {
  if (task.assigned_to) return personLabel(task.assigned_to);
  if (task.role) return `Role needed: ${task.role}`;
  return "Unassigned";
}

function compactMeta(items) {
  return items.filter((item) => item && item.value).map((item) => `
    <span class="meta-pill"><span>${escapeHtml(item.label)}</span>${escapeHtml(item.value)}</span>
  `).join("");
}

function detailList(items) {
  const rows = items.filter((item) => item && item.value);
  if (!rows.length) return "";
  return `
    <dl class="detail-list">
      ${rows.map((item) => `
        <div>
          <dt>${escapeHtml(item.label)}</dt>
          <dd>${item.html || escapeHtml(item.value)}</dd>
        </div>
      `).join("")}
    </dl>
  `;
}

function listLabel(value) {
  if (Array.isArray(value)) return value.join(", ");
  return String(value || "");
}

function labeledTitle(id, title, fallback) {
  const clean = String(title || fallback || "").trim();
  if (!id) return clean;
  if (!clean) return id;
  return clean.toLowerCase().startsWith(String(id).toLowerCase()) ? clean : `${id} - ${clean}`;
}

function shortPath(pathValue) {
  const clean = String(pathValue || "");
  if (clean.length <= 96) return clean;
  return `...${clean.slice(-93)}`;
}

function safeHref(value) {
  const clean = String(value || "").trim();
  if (!clean) return "";
  try {
    const url = new URL(clean, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? clean : "";
  } catch {
    return "";
  }
}

function renderInlineMarkdown(value) {
  const tokens = [];
  const token = (html) => {
    const key = `%%MDTOKEN${tokens.length}%%`;
    tokens.push([key, html]);
    return key;
  };
  let text = String(value || "");
  text = text.replace(/`([^`]+)`/g, (_match, code) => token(`<code>${escapeHtml(code)}</code>`));
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => {
    const safe = safeHref(href);
    if (!safe) return escapeHtml(label);
    return token(`<a href="${escapeHtml(safe)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`);
  });
  let html = escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  for (const [key, replacement] of tokens) html = html.replaceAll(key, replacement);
  return html;
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{2,}:?$/.test(cell.trim()));
}

function splitTableRow(line) {
  let clean = String(line || "").trim();
  if (clean.startsWith("|")) clean = clean.slice(1);
  if (clean.endsWith("|")) clean = clean.slice(0, -1);
  return clean.split("|").map((cell) => cell.trim());
}

function renderMarkdownTable(lines, startIndex) {
  const header = splitTableRow(lines[startIndex]);
  const rows = [];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    const cells = splitTableRow(lines[index]);
    while (cells.length < header.length) cells.push("");
    rows.push(cells.slice(0, header.length));
    index += 1;
  }
  return {
    html: `
      <div class="markdown-table-wrap">
        <table>
          <thead><tr>${header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead>
          <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>
    `,
    nextIndex: index
  };
}

function isMarkdownBlockStart(lines, index) {
  const line = lines[index] || "";
  const next = lines[index + 1] || "";
  return /^#{1,6}\s+/.test(line) ||
    /^```/.test(line.trim()) ||
    /^>\s?/.test(line) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    (line.includes("|") && isTableSeparator(next));
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    const fence = /^```(\w+)?/.exec(trimmed);
    if (fence) {
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += index < lines.length ? 1 : 0;
      html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      const level = Math.min(heading[1].length, 4);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }
    if (line.includes("|") && isTableSeparator(lines[index + 1] || "")) {
      const table = renderMarkdownTable(lines, index);
      html.push(table.html);
      index = table.nextIndex;
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${quote.map(renderInlineMarkdown).join("<br>")}</blockquote>`);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*+]\s+/, ""));
        index += 1;
      }
      html.push(`<ul>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      html.push(`<ol>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ol>`);
      continue;
    }
    const paragraph = [trimmed];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isMarkdownBlockStart(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
  }
  return html.join("");
}

function linkOrText(value, fallback = "Open") {
  const clean = String(value || "").trim();
  if (!clean) return "";
  try {
    const url = new URL(clean);
    if (["http:", "https:"].includes(url.protocol)) {
      return `<a href="${escapeHtml(clean)}" target="_blank" rel="noreferrer">${escapeHtml(fallback)}</a>`;
    }
  } catch {
    return escapeHtml(clean);
  }
  return escapeHtml(clean);
}

function navTo(viewName) {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewName));
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  $(`${viewName}View`).classList.add("active");
}

function setFormField(formId, name, value) {
  const form = $(formId);
  if (!form) return;
  const field = form.elements[name];
  if (field) field.value = value || "";
}

function selectedActor(task) {
  return task.assigned_to || "";
}

function renderSelectedTaskSummary() {
  const task = taskById(state.selectedTaskId);
  const target = $("selectedTaskSummary");
  if (!target) return;
  if (!task) {
    target.innerHTML = `<strong>No task selected</strong><span>Select a task to prefill update forms.</span>`;
    return;
  }
  target.innerHTML = `
    <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "Untitled task")}</strong>
    <span>${escapeHtml(taskOwnerLabel(task))} / ${escapeHtml(task.status || "Backlog")} / ${escapeHtml(task.expected_output || "No expected output")}</span>
    <p>${escapeHtml(task.user_update || task.blocker || task.path || "")}</p>
  `;
}

function selectTaskForUpdate(taskId, openUpdates = true) {
  const task = taskById(taskId);
  if (!task) return;
  state.selectedTaskId = task.id;
  const picker = $("updateTaskPicker");
  if (picker) picker.value = task.id;
  const actor = selectedActor(task);
  const reviewer = task.reviewer || "";
  const fieldValues = {
    updateTaskForm: {
      task_id: task.id,
      actor,
      status: task.status || "",
      checkpoint: task.checkpoint || "",
      target_repo: task.target_repo || "",
      output: task.output || "",
      output_commit: task.output_commit || "",
      blocker: task.blocker || "",
      milestone: task.milestone || "",
      feature_area: task.feature_area || "",
      reviewer,
      user_update: task.user_update || ""
    },
    submitOutputForm: { task_id: task.id, actor, target_repo: task.target_repo || "", output: task.output || "", output_commit: task.output_commit || "" },
    reviewTaskForm: { task_id: task.id, reviewer },
    recordAttemptForm: { task_id: task.id, actor, target_repo: task.target_repo || "", output: task.output || "", output_commit: task.output_commit || "" },
    verificationFailedForm: { task_id: task.id, reviewer, output: task.output || "" },
    withdrawOutputForm: { task_id: task.id, actor, output: task.output || "" },
    supersedeOutputForm: { task_id: task.id, actor, old_output: task.output || "" },
    cancelReviewForm: { task_id: task.id, actor: reviewer || actor },
    addEventForm: { task_id: task.id, actor }
  };
  for (const [formId, values] of Object.entries(fieldValues)) {
    for (const [name, value] of Object.entries(values)) setFormField(formId, name, value);
  }
  renderSelectedTaskSummary();
  if (openUpdates) navTo("updates");
}

function renderDatalists() {
  const taskOptions = $("taskOptions");
  if (taskOptions && state.data) {
    taskOptions.innerHTML = state.data.tasks.map((task) => `
      <option value="${escapeHtml(task.id)}">${escapeHtml(task.title || "")}</option>
    `).join("");
  }
  const staffOptions = $("staffOptions");
  if (staffOptions && state.data) {
    staffOptions.innerHTML = people().flatMap((person) => {
      const rows = [];
      if (person.email) rows.push(`<option value="${escapeHtml(person.email)}">${escapeHtml(person.name || person.email)} / ${escapeHtml(person.role || "")}</option>`);
      if (person.name) rows.push(`<option value="${escapeHtml(person.name)}">${escapeHtml(person.role || "")}${person.email ? ` / ${escapeHtml(person.email)}` : ""}</option>`);
      return rows;
    }).join("");
  }
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
  $("taskResultCount").textContent = `${filteredTasks().length} matching`;
  $("taskRows").innerHTML = tasks.map((task) => `
    <tr>
      <td><strong>${escapeHtml(task.id)}</strong></td>
      <td>${escapeHtml(task.title || "")}<br><small>${escapeHtml(task.project_name || "")}${task.path ? ` / ${escapeHtml(task.path)}` : ""}</small></td>
      <td>${escapeHtml(taskOwnerLabel(task))}</td>
      <td><span class="badge ${statusClass(task.status)}">${escapeHtml(task.status || "Backlog")}</span></td>
      <td>${escapeHtml(task.expected_output || "")}${task.output ? `<br><small>${linkOrText(task.output, "Output")}</small>` : ""}</td>
      <td><button type="button" class="inline-action" data-task-action="update" data-task-id="${escapeHtml(task.id)}">Update</button></td>
    </tr>
  `).join("") || `<tr><td colspan="6">No matching tasks.</td></tr>`;
}

function renderTaskBoard() {
  const tasks = filteredTasks();
  $("taskBoard").innerHTML = tasks.map((task) => `
    <article class="task-card">
      <div class="item-title">
        <strong>${escapeHtml(labeledTitle(task.id, task.title, "Untitled task"))}</strong>
        <span class="badge ${statusClass(task.status)}">${escapeHtml(task.status || "Backlog")}</span>
      </div>
      ${detailList([
        { label: "Owner", value: taskOwnerLabel(task) },
        { label: "Expected output", value: task.expected_output || "TBD" },
        { label: "Repo", value: task.target_repo || "" },
        { label: "Milestone", value: task.milestone || "" },
        { label: "Reviewer", value: personLabel(task.reviewer || "") }
      ])}
      <p class="item-snippet">${escapeHtml(task.user_update || task.blocker || "No current update.")}</p>
      ${task.output ? `<p class="item-link"><span>Submitted output</span>${linkOrText(task.output, "Open output")}${task.output_commit ? ` <small>${escapeHtml(task.output_commit.slice(0, 12))}</small>` : ""}</p>` : ""}
      <div class="action-row"><button type="button" data-task-action="update" data-task-id="${escapeHtml(task.id)}">Update</button></div>
    </article>
  `).join("") || `<div class="task-card"><strong>No tasks</strong><span>Adjust search or filters.</span></div>`;
}

function renderDocs() {
  const docs = state.data ? state.data.docs.filter(matchesQuery) : [];
  $("docList").innerHTML = docs.map((doc) => `
    <article class="doc-row" data-doc-action="open" data-doc-id="${escapeHtml(doc.id)}" tabindex="0">
      <div class="item-title">
        <strong>${escapeHtml(labeledTitle(doc.id, doc.title, doc.type))}</strong>
        <span class="badge">${escapeHtml(doc.type || "doc")}</span>
      </div>
      ${detailList([
        { label: "Owner", value: personLabel(doc.owner || "") },
        { label: "Status", value: doc.status || "draft" },
        { label: "Hash", value: doc.sha256 ? doc.sha256.slice(0, 12) : "" }
      ])}
      ${doc.preview || doc.snippet ? `<p class="doc-preview">${escapeHtml(doc.preview || doc.snippet)}</p>` : `<p class="doc-preview muted">No readable preview available.</p>`}
      ${doc.headings?.length ? `<p class="section-line"><span>Sections</span>${escapeHtml(doc.headings.slice(0, 6).join(" / "))}</p>` : ""}
      <p class="path-line"><span>Path</span><code>${escapeHtml(shortPath(doc.path || ""))}</code></p>
      <div class="action-row"><button type="button" data-doc-action="open" data-doc-id="${escapeHtml(doc.id)}">Open full doc</button></div>
    </article>
  `).join("") || `<div class="doc-row"><strong>No docs found</strong><span>Run compile or initialize the repo.</span></div>`;
  renderDocReader();
}

function openDocReader(docId) {
  if (!docById(docId)) return;
  state.selectedDocId = docId;
  renderDocReader();
}

function closeDocReader() {
  state.selectedDocId = "";
  renderDocReader();
}

function renderDocReader() {
  const listPanel = $("docListPanel");
  const readerPanel = $("docReaderPanel");
  if (!listPanel || !readerPanel) return;
  const doc = docById(state.selectedDocId);
  listPanel.classList.toggle("hidden", Boolean(doc));
  readerPanel.classList.toggle("hidden", !doc);
  if (!doc) return;
  $("docReaderTitle").textContent = labeledTitle(doc.id, doc.title, doc.type);
  $("docReaderPath").textContent = doc.path || "";
  $("docReaderMeta").innerHTML = detailList([
    { label: "Owner", value: personLabel(doc.owner || "") },
    { label: "Status", value: doc.status || "draft" },
    { label: "Type", value: doc.type || "doc" },
    { label: "Hash", value: doc.sha256 ? doc.sha256.slice(0, 12) : "" }
  ]);
  $("docReaderBody").innerHTML = renderMarkdown(doc.markdown || doc.snippet || "");
}

function renderAssets() {
  const assets = state.data ? (state.data.assets || []).filter(matchesQuery) : [];
  $("assetList").innerHTML = assets.map((asset) => `
    <article class="doc-row">
      <div class="item-title">
        <strong>${escapeHtml(asset.id)} - ${escapeHtml(asset.title || asset.type)}</strong>
        <span class="badge">${escapeHtml(asset.type || "asset")}</span>
      </div>
      <div class="meta-row">${compactMeta([
        { label: "Owner", value: personLabel(asset.owner || "") },
        { label: "Status", value: asset.status || "" },
        { label: "Storage", value: asset.storage || "" },
        { label: "Used by", value: listLabel(asset.used_by) }
      ])}</div>
      <p class="item-link">${linkOrText(asset.source_url || asset.path || "", asset.source_url ? "Open asset" : "Repo path") || "No link recorded."}</p>
    </article>
  `).join("") || `<div class="doc-row"><strong>No assets found</strong><span>Register mockups, videos, builds, art, and external files.</span></div>`;
}

function renderEvents() {
  const events = state.data ? state.data.events.slice(-8).reverse() : [];
  $("eventList").innerHTML = events.map((event) => `
    <article class="event">
      <strong>${escapeHtml(event.task_id || "")} ${escapeHtml(event.event_type || "event")}</strong>
      <span>${escapeHtml(personLabel(event.actor || "system"))} / ${escapeHtml(event.created_at || "")}</span>
      <p>${escapeHtml(event.message || "")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No recent events</strong><span>Task activity will appear here.</span></div>`;
}

function renderReviewQueue() {
  const queue = state.data ? (state.data.review_queue || []) : [];
  $("reviewQueueList").innerHTML = queue.map((item) => `
    <article class="event">
      <strong>${escapeHtml(item.task_id || "")} ${escapeHtml((item.reasons || []).join(", "))}</strong>
      <span>${escapeHtml(personLabel(item.assigned_to || "Unassigned"))} / ${escapeHtml(personLabel(item.reviewer || "No reviewer"))} / ${escapeHtml(item.status || "")}</span>
      <p>${escapeHtml(item.title || "")}${item.output ? ` / ${escapeHtml(item.output)}` : ""}</p>
    </article>
  `).join("") || `<div class="event"><strong>No review queue items</strong><span>Submitted, failed, withdrawn, and cancelled reviews will appear here.</span></div>`;
}

function renderMyWork() {
  const owner = state.myWorkOwner.trim();
  const open = (state.data ? state.data.tasks : []).filter((task) => !["Done", "Verified", "Iceboxed"].includes(task.status));
  const assigned = open.filter((task) => identityMatches(task.assigned_to || "", owner));
  const review = open.filter((task) => {
    const reviewerMatch = identityMatches(task.reviewer || "", owner);
    return reviewerMatch && (task.status === "In Review" || String(task.reviewer || "").trim());
  });
  $("myAssignedList").innerHTML = assigned.map((task) => `
    <article class="task-card">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "Untitled task")}</strong>
      <span>${escapeHtml(taskOwnerLabel(task))} / ${escapeHtml(task.status || "Backlog")} / ${escapeHtml(task.expected_output || "No expected output")}</span>
      <p>${escapeHtml(task.user_update || task.blocker || task.path || "")}</p>
      <div class="action-row"><button type="button" data-task-action="update" data-task-id="${escapeHtml(task.id)}">Update</button></div>
    </article>
  `).join("") || `<div class="task-card"><strong>No assigned work</strong><span>Enter an assignee name or clear the filter.</span></div>`;
  $("myReviewList").innerHTML = review.map((task) => `
    <article class="task-card">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "Untitled task")}</strong>
      <span>${escapeHtml(personLabel(task.reviewer || "No reviewer"))} / ${escapeHtml(task.status || "Backlog")} / ${escapeHtml(task.target_repo || "No target repo")}</span>
      <p>${escapeHtml(task.output || task.user_update || task.path || "")}${task.output_commit ? ` / ${escapeHtml(task.output_commit.slice(0, 12))}` : ""}</p>
      <div class="action-row"><button type="button" data-task-action="update" data-task-id="${escapeHtml(task.id)}">Update</button></div>
    </article>
  `).join("") || `<div class="task-card"><strong>No review work</strong><span>In-review tasks and explicit reviewer assignments appear here.</span></div>`;
}

function renderHealth() {
  const blocked = state.data ? (state.data.blocked_tasks || []) : [];
  $("blockedTaskList").innerHTML = blocked.map((task) => `
    <article class="event">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "")}</strong>
      <span>${escapeHtml(taskOwnerLabel(task))} / ${escapeHtml(task.status || "")}</span>
      <p>${escapeHtml(task.blocker || task.user_update || "No blocker detail")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No blocked tasks</strong><span>Blocked tasks with blocker text will appear here.</span></div>`;

  const stale = state.data ? (state.data.stale_work || []) : [];
  $("staleWorkList").innerHTML = stale.map((task) => `
    <article class="event">
      <strong>${escapeHtml(task.id)} - ${escapeHtml(task.title || "")}</strong>
      <span>${escapeHtml(taskOwnerLabel(task))} / ${escapeHtml(task.status || "")} / ${task.age_days === null ? "no events" : `${escapeHtml(task.age_days)} days`}</span>
      <p>${escapeHtml(task.latest_event?.message || task.user_update || task.path || "")}</p>
    </article>
  `).join("") || `<div class="event"><strong>No stale work</strong><span>Open tasks without recent events will appear here.</span></div>`;

  const features = state.data ? (state.data.feature_proposals || []) : [];
  $("featureProposalList").innerHTML = features.map((doc) => `
    <article class="doc-row">
      <strong>${escapeHtml(doc.id)} - ${escapeHtml(doc.title || "Feature proposal")}</strong>
      <span>${escapeHtml(doc.status || "draft")} / ${escapeHtml(personLabel(doc.owner || "Unowned"))} / ${escapeHtml(doc.path || "")}</span>
    </article>
  `).join("") || `<div class="doc-row"><strong>No feature proposals awaiting decision</strong><span>Use Create > Feature Proposal PR/MR to start one.</span></div>`;

  const repoUnknown = state.data ? (state.data.repo_state_unknown || []) : [];
  $("repoStateUnknownList").innerHTML = repoUnknown.map((item) => `
    <article class="event">
      <strong>${escapeHtml(item.task_id || "")} ${escapeHtml((item.reasons || []).join(", "))}</strong>
      <span>${escapeHtml(item.target_repo || "No target repo")} / ${escapeHtml(item.output_commit || "No output commit")} / ${escapeHtml(item.status || "")}</span>
      <p>${escapeHtml(item.title || "")}${item.output ? ` / ${escapeHtml(item.output)}` : ""}</p>
    </article>
  `).join("") || `<div class="event"><strong>No repo verification gaps</strong><span>Tasks with missing target repos or output commits will appear here.</span></div>`;
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
  renderDatalists();
  renderTasksTable();
  renderTaskBoard();
  renderDocs();
  renderAssets();
  renderEvents();
  renderReviewQueue();
  renderMyWork();
  renderHealth();
  renderSelectedTaskSummary();
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

document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => navTo(button.dataset.view)));

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-task-action='update']");
  if (button) {
    selectTaskForUpdate(button.dataset.taskId);
    return;
  }
  const docTarget = event.target.closest("[data-doc-action='open']");
  if (docTarget) openDocReader(docTarget.dataset.docId);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const docTarget = event.target.closest("[data-doc-action='open']");
  if (docTarget) openDocReader(docTarget.dataset.docId);
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
$("updateTaskPicker").addEventListener("change", (event) => selectTaskForUpdate(event.target.value, false));
$("docBackButton").addEventListener("click", closeDocReader);

$("createTaskForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "create_task",
    project_id: form.get("project_id"),
    title: form.get("title"),
    assigned_to: form.get("assigned_to"),
    role: form.get("role"),
    expected_output: form.get("expected_output"),
    target_repo: form.get("target_repo")
  });
});

$("registerRepoForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  submitProposal({
    type: "register_repo",
    project_id: form.get("project_id"),
    name: form.get("name"),
    provider: form.get("provider"),
    url: form.get("url"),
    default_branch: form.get("default_branch"),
    role: form.get("role")
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
    target_repo: form.get("target_repo"),
    output: form.get("output"),
    output_commit: form.get("output_commit"),
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
    target_repo: form.get("target_repo"),
    output_commit: form.get("output_commit"),
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
    target_repo: form.get("target_repo"),
    output_commit: form.get("output_commit"),
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
