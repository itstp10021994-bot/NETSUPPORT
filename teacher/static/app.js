/* Teacher console: connects to the hub WebSocket as a teacher, renders a live
 * grid of student screen thumbnails, and sends control commands. */

const P = {
  HELLO: "hello", ROSTER: "roster", STUDENT_JOINED: "student_joined",
  STUDENT_LEFT: "student_left", THUMBNAIL: "thumbnail", ACK: "ack",
  LOCK: "lock", UNLOCK: "unlock", MESSAGE: "message",
  REQUEST_THUMBNAILS: "request_thumbnails",
};

const state = {
  ws: null,
  room: "default",
  students: new Map(), // id -> {id, name, locked, active_window, el}
};

const $ = (sel) => document.querySelector(sel);
const grid = $("#grid");
const tpl = $("#card-tpl");

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
}

function send(type, fields = {}) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type, ts: Date.now() / 1000, ...fields }));
  }
}

function setConnected(online) {
  $("#conn-dot").classList.toggle("online", online);
  $("#room-label").textContent = online ? `· phòng: ${state.room}` : "";
}

function ensureCard(student) {
  let s = state.students.get(student.id);
  if (!s) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".name").textContent = student.name || student.id;
    node.querySelectorAll(".card-actions button").forEach((btn) => {
      btn.addEventListener("click", () => cardAction(student.id, btn.dataset.op));
    });
    grid.appendChild(node);
    s = { ...student, el: node };
    state.students.set(student.id, s);
  }
  return s;
}

function renderRoster(students) {
  const seen = new Set();
  students.forEach((stu) => {
    const s = ensureCard(stu);
    seen.add(stu.id);
    s.name = stu.name;
    s.locked = stu.locked;
    s.active_window = stu.active_window;
    s.el.querySelector(".name").textContent = stu.name || stu.id;
    s.el.querySelector(".win").textContent = stu.active_window || "";
    s.el.classList.toggle("locked", !!stu.locked);
  });
  // Remove cards for students no longer present.
  for (const [id, s] of state.students) {
    if (!seen.has(id)) { s.el.remove(); state.students.delete(id); }
  }
  $("#empty").style.display = state.students.size ? "none" : "block";
}

function onThumbnail(msg) {
  const s = state.students.get(msg.student_id);
  if (s && msg.image) {
    s.el.querySelector(".thumb").src = `data:image/jpeg;base64,${msg.image}`;
  }
}

function cardAction(id, op) {
  if (op === "lock") send(P.LOCK, { targets: [id] });
  else if (op === "unlock") send(P.UNLOCK, { targets: [id] });
  else if (op === "message") {
    const text = prompt("Tin nhắn gửi tới máy này:");
    if (text) send(P.MESSAGE, { targets: [id], title: "Thông báo", text });
  }
}

function handle(msg) {
  switch (msg.type) {
    case P.ROSTER: renderRoster(msg.students || []); break;
    case P.THUMBNAIL: onThumbnail(msg); break;
    case P.STUDENT_JOINED:
    case P.STUDENT_LEFT: break; // roster follows
    case P.ACK: break;
  }
}

function connect() {
  state.room = $("#room-input").value.trim() || "default";
  if (state.ws) { state.ws.close(); state.ws = null; }

  const ws = new WebSocket(wsUrl());
  state.ws = ws;
  ws.onopen = () => {
    send(P.HELLO, { role: "teacher", name: "console", room: state.room });
    setConnected(true);
    // Ask students to start sending thumbnails.
    send(P.REQUEST_THUMBNAILS, { targets: "all", fps: 0.5 });
  };
  ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (_) {} };
  ws.onclose = () => { setConnected(false); };
  ws.onerror = () => { setConnected(false); };
}

// Toolbar wiring
$("#connect-btn").addEventListener("click", connect);
document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const a = btn.dataset.action;
    if (a === "monitor-on") send(P.REQUEST_THUMBNAILS, { targets: "all", fps: 0.5 });
    else if (a === "monitor-off") send(P.REQUEST_THUMBNAILS, { targets: "all", fps: 0 });
    else if (a === "lock-all") send(P.LOCK, { targets: "all", title: "Màn hình đã khóa", body: "Giáo viên đã khóa máy này." });
    else if (a === "unlock-all") send(P.UNLOCK, { targets: "all" });
    else if (a === "message-all") {
      const text = prompt("Tin nhắn gửi tới cả lớp:");
      if (text) send(P.MESSAGE, { targets: "all", title: "Thông báo cả lớp", text });
    }
  });
});

// Auto-connect on load for convenience.
connect();
