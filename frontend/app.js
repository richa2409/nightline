/**
 * Nightline frontend — a small vanilla-JS SPA.
 * No build step on purpose: this ships straight from nginx as static files,
 * which keeps the frontend container trivial (see docker-compose.yml).
 *
 * All backend calls go through /api/* which nginx rewrites to the FastAPI
 * service (see nginx/nginx.conf). WebSocket chat goes through /ws/*.
 */

const API_BASE = "/api";
const state = {
  token: localStorage.getItem("nl_token") || null,
  roomId: null,
  socket: null,
  myHandle: null,
};

// ---------- view routing ----------
const views = ["landing", "signup", "login", "waiting", "chat"];
function showView(name) {
  views.forEach(v => {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== name);
  });
}
document.querySelectorAll("[data-nav]").forEach(el => {
  el.addEventListener("click", () => showView(el.dataset.nav));
});

// ---------- helpers ----------
async function api(path, { method = "GET", body, form = false } = {}) {
  const headers = {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

  let payload = body;
  if (body && !form) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.status === 204 ? null : res.json();
}

function setToken(token) {
  state.token = token;
  localStorage.setItem("nl_token", token);
}

// ---------- signup ----------
document.getElementById("form-signup").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const errEl = document.getElementById("signup-error");
  errEl.textContent = "";
  try {
    await api("/auth/register", {
      method: "POST",
      body: {
        email: f.get("email"),
        password: f.get("password"),
        interests_text: f.get("interests") || "",
      },
    });
    // auto-login right after registering
    const loginBody = new URLSearchParams();
    loginBody.set("username", f.get("email"));
    loginBody.set("password", f.get("password"));
    const tokenRes = await api("/auth/login", { method: "POST", body: loginBody, form: true });
    setToken(tokenRes.access_token);
    enterQueue();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

// ---------- login ----------
document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    const body = new URLSearchParams();
    body.set("username", f.get("email"));
    body.set("password", f.get("password"));
    const tokenRes = await api("/auth/login", { method: "POST", body, form: true });
    setToken(tokenRes.access_token);
    enterQueue();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

// ---------- matchmaking ----------
let pollTimer = null;

async function enterQueue() {
  const waitingSub = document.getElementById("waiting-sub");
  try {
    const me = await api("/users/me");
    state.myHandle = me.anon_handle;
    showView("waiting");
    waitingSub.textContent = "Comparing interests with everyone else waiting right now.";
    await api("/match/join", { method: "POST" });
    pollTimer = setInterval(pollMatch, 2500);
    pollMatch(); // fire immediately too
  } catch (err) {
    showView("landing");
    alert(`Couldn't join the queue: ${err.message}`);
  }
}

async function pollMatch() {
  try {
    const result = await api("/match/poll", { method: "POST" });
    if (result.status === "waiting") return;
    clearInterval(pollTimer);
    state.roomId = result.room_id;
    document.getElementById("partner-handle").textContent = result.partner_handle;
    document.getElementById("match-score").textContent =
      `shared interest score: ${(result.match_score * 100).toFixed(0)}%`;
    connectChat(result.room_id);
  } catch (err) {
    console.error(err);
  }
}

document.getElementById("btn-cancel-queue").addEventListener("click", async () => {
  clearInterval(pollTimer);
  await api("/match/leave", { method: "POST" }).catch(() => {});
  showView("landing");
});

// ---------- chat ----------
function connectChat(roomId) {
  const log = document.getElementById("chat-log");
  log.innerHTML = "";
  showView("chat");

  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/ws/chat/${roomId}?token=${state.token}`);
  state.socket = socket;

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    appendMessage(data);
  };

  api(`/chat/${roomId}/history`).then(messages => {
    messages.forEach(message => appendMessage({ type: "message", ...message }));
  }).catch(err => console.error("Couldn't load chat history", err));

  socket.onclose = () => {
    appendMessage({ type: "system", content: "Connection closed." });
  };
}

function appendMessage({ type, sender_handle, content }) {
  const log = document.getElementById("chat-log");
  const bubble = document.createElement("div");

  if (type === "system") {
    bubble.className = "msg msg--system";
    bubble.textContent = content;
  } else {
    bubble.className = `msg ${sender_handle === state.myHandle ? "msg--me" : "msg--them"}`;
    bubble.textContent = content;
  }

  log.appendChild(bubble);
  log.scrollTop = log.scrollHeight;
}

document.getElementById("form-chat-input").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-message");
  const content = input.value.trim();
  if (!content || !state.socket || state.socket.readyState !== WebSocket.OPEN) return;
  state.socket.send(JSON.stringify({ content }));
  input.value = "";
});

document.getElementById("btn-end-chat").addEventListener("click", async () => {
  if (state.socket) state.socket.close();
  if (state.roomId) await api(`/chat/${state.roomId}/end`, { method: "POST" }).catch(() => {});
  showView("landing");
});

// ---------- boot ----------
if (state.token) {
  // returning user with a stored token could jump straight back into the queue;
  // kept simple here and left on the landing page for clarity in a demo.
}
showView("landing");
