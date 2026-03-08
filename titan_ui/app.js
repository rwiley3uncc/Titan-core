/*
Titan Core - Frontend Client Logic (MVP)
-----------------------------------------

Purpose:
  Lightweight UI controller for interacting with Titan Core backend.

Architecture Flow:
  UI -> API -> Brain -> Audit -> Approval -> Dispatcher

Responsibilities:
  - Authentication
  - Conversation management
  - Chat interaction
  - Rendering proposed actions
  - Approving actions
  - Displaying persisted system state

Design Notes:
  - Stateless backend (JWT required per request)
  - Client stores token in memory only (MVP choice)
  - All actions require explicit approval

Author:
  Ron Wiley
Project:
  Titan AI - Operational Personnel Assistant
*/


// ---------------------------------------------------------------------
// Global State
// ---------------------------------------------------------------------

let token = null;
let currentConversationId = null;
let lastAuditId = null;
let lastProposed = [];


// ---------------------------------------------------------------------
// Helper: Auth Headers
// ---------------------------------------------------------------------

function headers() {
  return token ? { "Authorization": "Bearer " + token } : {};
}


// ---------------------------------------------------------------------
// Helper: Role Badge Utilities
// ---------------------------------------------------------------------

function roleClass(role) {
  if (role === "admin") return "role-admin";
  if (role === "teacher") return "role-teacher";
  return "role-student";
}

function roleLabel(role) {
  if (role === "admin") return "Admin";
  if (role === "teacher") return "Teacher";
  return "Student";
}

function setHeaderRole(role) {
  const mode = document.getElementById("modeLabel");
  const badgeHost = document.getElementById("roleBadgeHeader");

  if (!role) {
    mode.innerText = "Mode: Not signed in";
    badgeHost.style.display = "none";
    badgeHost.innerHTML = "";
    return;
  }

  const cls = roleClass(role);
  mode.innerText = `Mode: ${roleLabel(role)}`;

  badgeHost.style.display = "inline-block";
  badgeHost.innerHTML = `<span class="role-badge header-badge ${cls}">${role.toUpperCase()}</span>`;
}


// ---------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------

async function login() {
  const username = document.getElementById("u").value;
  const password = document.getElementById("p").value;

  const form = new FormData();
  form.append("username", username);
  form.append("password", password);

  const r = await fetch("/login", { method: "POST", body: form });

  if (!r.ok) {
    alert("Login failed");
    setHeaderRole(null);
    return;
  }

  const j = await r.json();
  token = j.token;

  // Update login panel badge
  const cls = roleClass(j.role);

  document.getElementById("who").innerHTML =
    `Logged in as <strong>${j.username}</strong>
     <span class="role-badge ${cls}">${j.role.toUpperCase()}</span>`;

  // Update header badge + mode label
  setHeaderRole(j.role);

  await loadConvos();
}


// ---------------------------------------------------------------------
// Conversation Management
// ---------------------------------------------------------------------

async function newChat() {
  const form = new FormData();
  form.append("title", "New chat");

  const r = await fetch("/conversations", {
    method: "POST",
    headers: headers(),
    body: form
  });

  const j = await r.json();

  currentConversationId = j.id;
  await loadConvos();
  await loadMessages();
}

async function loadConvos() {
  const r = await fetch("/conversations", { headers: headers() });
  const j = await r.json();

  const div = document.getElementById("convos");
  div.innerHTML = "";

  j.forEach(c => {
    const b = document.createElement("button");
    b.innerText = `${c.id}: ${c.title}`;
    b.onclick = async () => {
      currentConversationId = c.id;
      await loadMessages();
    };

    div.appendChild(b);
    div.appendChild(document.createElement("br"));
  });

  if (!currentConversationId && j.length) {
    currentConversationId = j[0].id;
    await loadMessages();
  }
}


// ---------------------------------------------------------------------
// Chat Rendering
// ---------------------------------------------------------------------

async function loadMessages() {
  if (!currentConversationId) return;

  const r = await fetch(
    `/conversations/${currentConversationId}/messages`,
    { headers: headers() }
  );

  const j = await r.json();

  const chat = document.getElementById("chat");
  chat.innerText = j.map(m => `${m.role.toUpperCase()}: ${m.content}`).join("\n\n");
  chat.scrollTop = chat.scrollHeight;
}


// ---------------------------------------------------------------------
// Send Message
// ---------------------------------------------------------------------

async function sendMsg() {
  if (!currentConversationId) {
    alert("Create a chat first");
    return;
  }

  const textInput = document.getElementById("msg");
  const text = textInput.value.trim();
  if (!text) return;

  const form = new FormData();
  form.append("conversation_id", currentConversationId);
  form.append("text", text);

  const r = await fetch("/chat", {
    method: "POST",
    headers: headers(),
    body: form
  });

  const j = await r.json();

  textInput.value = "";
  lastAuditId = j.audit_log_id;
  lastProposed = j.proposed_actions || [];

  await loadMessages();
  renderActions();
}


// ---------------------------------------------------------------------
// Render Proposed Actions
// ---------------------------------------------------------------------

function renderActions() {
  const div = document.getElementById("actions");
  div.innerHTML = "";

  if (!lastProposed.length) {
    div.innerText = "(none)";
    return;
  }

  lastProposed.forEach((action) => {
    const pre = document.createElement("pre");
    pre.innerText = JSON.stringify(action, null, 2);
    div.appendChild(pre);

    const btn = document.createElement("button");
    btn.innerText = "Approve this action";
    btn.onclick = async () => approve([action]);
    div.appendChild(btn);

    div.appendChild(document.createElement("hr"));
  });

  const btnAll = document.createElement("button");
  btnAll.innerText = "Approve ALL proposed actions";
  btnAll.onclick = async () => approve(lastProposed);
  div.appendChild(btnAll);
}


// ---------------------------------------------------------------------
// Approve Actions
// ---------------------------------------------------------------------

async function approve(actions) {
  const form = new FormData();
  form.append("audit_log_id", lastAuditId);
  form.append("actions_json", JSON.stringify(actions));

  const r = await fetch("/actions/approve", {
    method: "POST",
    headers: headers(),
    body: form
  });

  const j = await r.json();

  alert("Approved.\n\nResults:\n" + JSON.stringify(j.results, null, 2));
  await refreshAll();
}


// ---------------------------------------------------------------------
// Refresh Data Panels
// ---------------------------------------------------------------------

async function refreshAll() {
  const [tasks, memory, drafts, audit] = await Promise.all([
    fetch("/tasks", { headers: headers() }).then(r => r.json()),
    fetch("/memory", { headers: headers() }).then(r => r.json()),
    fetch("/drafts", { headers: headers() }).then(r => r.json()),
    fetch("/audit", { headers: headers() }).then(r => r.json()),
  ]);

  document.getElementById("data").innerText =
    "TASKS:\n" + JSON.stringify(tasks, null, 2) +
    "\n\nMEMORY:\n" + JSON.stringify(memory, null, 2) +
    "\n\nDRAFTS:\n" + JSON.stringify(drafts, null, 2) +
    "\n\nAUDIT (latest 5):\n" + JSON.stringify(audit.slice(0, 5), null, 2);
}

// Initialize header state on load
setHeaderRole(null);