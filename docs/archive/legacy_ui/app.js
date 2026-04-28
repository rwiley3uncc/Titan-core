/*
Titan Personal Assistant UI Controller
--------------------------------------
Simple frontend for Titan Core.

Flow:
UI -> /api/chat -> Titan -> UI
*/

let lastProposed = [];

async function sendMsg() {
  const input = document.getElementById("msg");
  const text = input.value.trim();

  if (!text) return;

  const chat = document.getElementById("chat");

  chat.innerText += (chat.innerText ? "\n\n" : "") + "USER: " + text;
  input.value = "";

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: text,
        mode: "personal_general"
      })
    });

    if (!r.ok) {
      const errText = await r.text();
      alert("Titan backend error:\n" + errText);
      return;
    }

    const j = await r.json();

    chat.innerText += "\n\nTITAN: " + (j.reply || "(no reply)");
    chat.scrollTop = chat.scrollHeight;

    lastProposed = j.proposed_actions || [];
    renderActions();

  } catch (err) {
    alert("Request failed: " + err.message);
  }
}

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
  });
}

document.getElementById("msg").addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
});