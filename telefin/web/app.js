const PAGE_SIZE = 50;

const state = {
  filter: "active",
  query: "",
  page: 1,
  items: new Map(),    
  selected: new Set(),
};

const el = (id) => document.getElementById(id);

const svg = (paths, size = 16) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

const ICONS = {
  queued: svg(`<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>`),
  downloading: svg(`<path d="M12 4v10"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>`),
  importing: svg(`<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m8 17 4 4 4-4"/>`),
  completed: svg(`<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="m9 15 2 2 4-4"/>`),
  failed: svg(`<path d="m10.3 3.9-8.2 14.2a2 2 0 0 0 1.7 3h16.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>`),
  skipped: svg(`<path d="m5 4 10 8-10 8V4Z"/><path d="M19 5v14"/>`),
  cancelled: svg(`<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>`),
  retry: svg(`<path d="M3 12a9 9 0 1 0 2.64-6.36"/><path d="M3 3v6h6"/>`, 15),
  remove: svg(`<path d="M18 6 6 18M6 6l12 12"/>`, 15),
  stop: svg(`<rect x="6" y="6" width="12" height="12" rx="1"/>`, 15),
  notify: svg(`<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>`, 15),
  gear: svg(`<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z"/>`, 15),
  sortDesc: `<svg class="sort-caret" viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="m7 10 5 6 5-6Z"/></svg>`,
};

const STATUS_TITLES = {
  queued: "Queued",
  downloading: "Downloading",
  importing: "Importing",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped — duplicate, already downloaded",
  cancelled: "Cancelled by user",
};

const EMPTY_STATES = {
  active: {
    title: "Queue is empty",
    hint: " — forward a video file to your Saved Messages on Telegram and it will appear here",
  },
  all: { title: "No history", hint: "" },
  failed: { title: "No failed downloads", hint: "" },
};

// formatting
function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatTimeLeft(item) {
  if (!item.speed || !item.size || item.downloaded >= item.size) return "-";
  const secs = (item.size - item.downloaded) / item.speed;
  if (!isFinite(secs) || secs > 86400 * 7) return "-";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.ceil(secs % 60);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d >= today) {
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  if (d >= yesterday) return "Yesterday";
  return d.toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

// filtering / paging
function matchesFilter(item) {
  if (state.query &&
      !item.filename.toLowerCase().includes(state.query)) {
    return false;
  }
  if (state.filter === "all") return true;
  if (state.filter === "active") {
    return ["queued", "downloading", "importing"].includes(item.status);
  }
  return item.status === state.filter;
}

function visibleItems() {
  return [...state.items.values()]
    .filter(matchesFilter)
    .sort((a, b) =>
      state.filter === "active" ? a.id - b.id : b.id - a.id
    );
}

function render() {
  const items = visibleItems();

  const pages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  state.page = Math.min(Math.max(1, state.page), pages);
  const pageItems = items.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);

  // Drop selections that are no longer visible.
  const pageIds = new Set(pageItems.map((i) => i.id));
  for (const id of state.selected) {
    if (!pageIds.has(id)) state.selected.delete(id);
  }

  el("table").hidden = items.length === 0;
  el("pager").hidden = items.length === 0;

  const empty = el("empty");
  empty.hidden = items.length !== 0;
  if (!items.length) {
    const copy = state.query
      ? { title: "No results found", hint: "" }
      : EMPTY_STATES[state.filter] || EMPTY_STATES.all;
    el("empty-title").textContent = copy.title;
    el("empty-hint").textContent = copy.hint;
  }

  renderHead();

  const tbody = el("tbody");
  tbody.innerHTML = "";
  for (const item of pageItems) tbody.appendChild(renderRow(item));

  el("pager-label").textContent = `${state.page} / ${pages}`;
  el("pager-total").textContent = `Total records: ${items.length}`;
  document.querySelectorAll(".pager-btn").forEach((btn) => {
    const dir = btn.dataset.page;
    btn.disabled = (dir === "first" || dir === "prev")
      ? state.page <= 1
      : state.page >= pages;
  });

  renderCounts();
  updateToolbar();
}

function hasCheckboxes() {
  return state.filter === "active" || state.filter === "failed";
}

function renderHead() {
  const check = hasCheckboxes()
    ? `<th class="col-check"><input type="checkbox" id="check-all" /></th>`
    : "";

  let cols = "";
  if (state.filter === "active") {
    cols = `
      <th class="col-size">Size</th>
      <th class="col-timeleft">Time Left</th>
      <th class="col-progress">Progress</th>`;
  } else if (state.filter === "failed") {
    cols = `
      <th class="col-size">Size</th>
      <th class="col-error">Error</th>
      <th class="col-date">Date${ICONS.sortDesc}</th>`;
  } else {
    cols = `
      <th class="col-size">Size</th>
      <th class="col-date">Date${ICONS.sortDesc}</th>`;
  }

  el("thead").innerHTML = `
    <tr>
      ${check}
      <th class="col-icon"></th>
      <th>Title</th>
      <th class="col-type">Type</th>
      ${cols}
      <th class="col-gear">${ICONS.gear}</th>
    </tr>`;

  const all = el("check-all");
  if (all) {
    all.onchange = () => {
      const items = visibleItems()
        .slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
      state.selected.clear();
      if (all.checked) for (const item of items) state.selected.add(item.id);
      render();
    };
  }
}

function renderRow(item) {
  const row = document.createElement("tr");
  row.dataset.id = item.id;

  const statusClass = `status-${item.status}`;
  const icon =
    `<span class="${statusClass}" title="${escapeHtml(statusTitle(item))}">` +
    `${ICONS[item.status] || ""}</span>`;

  const check = hasCheckboxes()
    ? `<td class="col-check"><input type="checkbox" class="row-check"
         ${state.selected.has(item.id) ? "checked" : ""} /></td>`
    : "";

  let cols = "";
  if (state.filter === "active") {
    const pct = item.size
      ? Math.min(100, (item.downloaded / item.size) * 100)
      : 0;
    const downloading = item.status === "downloading";
    cols = `
      <td class="col-size">${item.size ? formatSize(item.size) : "-"}</td>
      <td class="col-timeleft">${downloading ? formatTimeLeft(item) : "-"}</td>
      <td class="col-progress">
        <div class="progress" title="${item.speed ? formatSize(item.speed) + "/s" : ""}">
          <div class="progress-bar" style="width:${pct}%"></div>
          ${downloading ? `<span class="progress-text">${Math.round(pct)}%</span>` : ""}
        </div>
      </td>`;
  } else if (state.filter === "failed") {
    cols = `
      <td class="col-size">${item.size ? formatSize(item.size) : "-"}</td>
      <td class="col-error"><div title="${escapeHtml(item.error || "")}">${escapeHtml(item.error || "")}</div></td>
      <td class="col-date">${formatDate(item.completed_at || item.created_at)}</td>`;
  } else {
    cols = `
      <td class="col-size">${item.size ? formatSize(item.size) : "-"}</td>
      <td class="col-date">${formatDate(item.completed_at || item.created_at)}</td>`;
  }

  row.innerHTML = `
    ${check}
    <td class="col-icon">${icon}</td>
    <td class="title-cell">
      <div class="title-text" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
    </td>
    <td class="col-type"><span class="tag">${item.media_type === "tv" ? "TV" : "Movie"}</span></td>
    ${cols}
    <td class="col-gear"><div class="actions">${renderActions(item)}</div></td>
  `;

  const checkbox = row.querySelector(".row-check");
  if (checkbox) {
    checkbox.onchange = () => {
      if (checkbox.checked) state.selected.add(item.id);
      else state.selected.delete(item.id);
      updateToolbar();
      syncCheckAll();
    };
  }
  const retry = row.querySelector("[data-action=retry]");
  if (retry) retry.onclick = () => retryItem(item.id);
  const del = row.querySelector("[data-action=delete]");
  if (del) del.onclick = () => deleteItem(item.id);
  const cancel = row.querySelector("[data-action=cancel]");
  if (cancel) cancel.onclick = () => cancelItem(item.id);
  const notify = row.querySelector("[data-action=notify]");
  if (notify) notify.onclick = () => notifyItem(item.id);

  return row;
}

function statusTitle(item) {
  const base = STATUS_TITLES[item.status] || item.status;
  if (item.status === "completed" && item.arr_result) {
    return `${base} — ${item.arr_result}`;
  }
  return base;
}

function renderActions(item) {
  const buttons = [];
  if (item.status === "completed") {
    buttons.push(`<button class="icon-btn" data-action="notify" title="Notify Sonarr/Radarr again">${ICONS.notify}</button>`);
  }
  if (["failed", "completed", "skipped", "cancelled"].includes(item.status)) {
    buttons.push(`<button class="icon-btn" data-action="retry" title="Retry">${ICONS.retry}</button>`);
    buttons.push(`<button class="icon-btn" data-action="delete" title="Remove from list">${ICONS.remove}</button>`);
  } else if (["queued", "downloading"].includes(item.status)) {
    buttons.push(`<button class="icon-btn" data-action="cancel" title="Cancel">${ICONS.stop}</button>`);
  }
  return buttons.join("");
}

function renderCounts() {
  let active = 0;
  let failed = 0;
  for (const item of state.items.values()) {
    if (["queued", "downloading", "importing"].includes(item.status)) active++;
    else if (item.status === "failed") failed++;
  }
  setCount("count-active", active);
  setCount("count-failed", failed);
}

function setCount(id, value) {
  const node = el(id);
  node.hidden = value === 0;
  node.textContent = value;
}

function updateToolbar() {
  const retryBtn = el("btn-retry-selected");
  const removeBtn = el("btn-remove-selected");
  const cancelBtn = el("btn-cancel-selected");
  const showRetry = state.filter === "failed";
  const showRemove = state.filter === "failed";
  const showCancel = state.filter === "active";

  retryBtn.hidden = !showRetry;
  removeBtn.hidden = !showRemove;
  cancelBtn.hidden = !showCancel;
  el("toolbar-sep").hidden = !(showRetry || showRemove || showCancel);

  retryBtn.disabled = state.selected.size === 0;
  removeBtn.disabled = state.selected.size === 0;
  cancelBtn.disabled = state.selected.size === 0;
}

function syncCheckAll() {
  const all = el("check-all");
  if (!all) return;
  const checks = document.querySelectorAll(".row-check");
  all.checked = checks.length > 0 &&
    [...checks].every((c) => c.checked);
}

// toasts

function toast(message, kind = "ok") {
  const node = document.createElement("div");
  node.className = `toast ${kind === "error" ? "error" : ""}`;
  node.textContent = message;
  el("toasts").appendChild(node);
  setTimeout(() => node.remove(), 3500);
}

// stats

async function loadStats() {
  const res = await fetch("/api/stats");
  const s = await res.json();
  el("stat-active").textContent = s.active;
  el("stat-completed").textContent = s.completed;
  el("stat-failed").textContent = s.failed;
  el("stat-total").textContent = formatSize(s.total_bytes);
  renderDisks(s.disks || []);
}

function renderDisks(disks) {
  const container = el("sidebar-disks");
  container.innerHTML = disks.map((disk) => {
    const label = disk.roles.join(" + ");
    if (disk.error) {
      return `
        <div class="disk-row">
          <div class="disk-row-label"><span>${escapeHtml(label)}</span><span>unreachable</span></div>
        </div>`;
    }
    const pct = disk.used_percent || 0;
    const barClass = pct >= 95 ? "danger" : pct >= 85 ? "warn" : "";
    return `
      <div class="disk-row">
        <div class="disk-row-label"><span>${escapeHtml(label)}</span><span>${formatSize(disk.free)} free</span></div>
        <div class="progress"><div class="progress-bar ${barClass}" style="width:${pct}%"></div></div>
      </div>`;
  }).join("");
}

async function loadConfig() {
  const res = await fetch("/api/config");
  const c = await res.json();
  el("foot-config").textContent =
    `${c.download_dir}  •  ${c.max_concurrent_downloads} concurrent  •  ` +
    `Sonarr ${c.sonarr_configured ? "✓" : "✗"}  •  ` +
    `Radarr ${c.radarr_configured ? "✓" : "✗"}`;
}

// data

async function loadItems() {
  const res = await fetch("/api/downloads?filter=all&limit=200");
  const rows = await res.json();
  state.items.clear();
  for (const row of rows) state.items.set(row.id, row);
  render();
}

async function refresh() {
  try {
    await Promise.all([loadItems(), loadStats(), loadConfig()]);
  } catch (e) {
    toast("Could not reach the server", "error");
  }
}

async function retryItem(id) {
  try {
    const res = await fetch(`/api/downloads/${id}/retry`, { method: "POST" });
    if (!res.ok) throw new Error();
    toast("Added back to the queue");
  } catch {
    toast("Retry failed", "error");
  }
  await refresh();
}

async function deleteItem(id) {
  if (!confirm("Remove this entry from the list? The downloaded file (if any) is kept.")) return;
  await deleteQuietly([id]);
  toast("Entry removed");
}

async function cancelItem(id) {
  try {
    const res = await fetch(`/api/downloads/${id}/cancel`, { method: "POST" });
    if (!res.ok) throw new Error();
    toast("Download cancelled");
  } catch {
    toast("Cancel failed", "error");
  }
  await refresh();
}

async function notifyItem(id) {
  try {
    const res = await fetch(`/api/downloads/${id}/notify`, { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || "");
    toast(body.result || "Sonarr/Radarr notified");
  } catch (e) {
    toast(e.message || "Notify failed", "error");
  }
  await refresh();
}

async function deleteQuietly(ids) {
  for (const id of ids) {
    try {
      await fetch(`/api/downloads/${id}`, { method: "DELETE" });
      state.items.delete(id);
      state.selected.delete(id);
    } catch {
      toast("Remove failed", "error");
    }
  }
  render();
  loadStats();
}

async function retrySelected() {
  const ids = [...state.selected];
  state.selected.clear();
  for (const id of ids) {
    try {
      await fetch(`/api/downloads/${id}/retry`, { method: "POST" });
    } catch {
      toast("Retry failed", "error");
    }
  }
  toast(`Retrying ${ids.length} download(s)`);
  await refresh();
}

async function removeSelected() {
  const ids = [...state.selected];
  if (!confirm(`Remove ${ids.length} entr${ids.length === 1 ? "y" : "ies"} from the list? Downloaded files (if any) are kept.`)) return;
  await deleteQuietly(ids);
  toast(`Removed ${ids.length} entr${ids.length === 1 ? "y" : "ies"}`);
}

async function cancelSelected() {
  const ids = [...state.selected];
  state.selected.clear();
  for (const id of ids) {
    try {
      await fetch(`/api/downloads/${id}/cancel`, { method: "POST" });
    } catch {
      toast("Cancel failed", "error");
    }
  }
  toast(`Cancelled ${ids.length} download(s)`);
  await refresh();
}

// live socket

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const conn = el("conn");

  ws.onopen = () => {
    conn.className = "conn online";
    el("conn-label").textContent = "live";
  };

  ws.onclose = () => {
    conn.className = "conn offline";
    el("conn-label").textContent = "reconnecting…";
    setTimeout(connect, 2000);
  };

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "status" && msg.download) {
      state.items.set(msg.download.id, msg.download);
      render();
      loadStats();
    } else if (msg.type === "progress") {
      const item = state.items.get(msg.id);
      if (item) {
        item.downloaded = msg.downloaded;
        item.size = msg.size || item.size;
        item.speed = msg.speed;
        updateProgress(item);
      }
    }
  };
}

function updateProgress(item) {
  // progress bars animate without a full redraw.
  const row = document.querySelector(`tr[data-id="${item.id}"]`);
  if (!row) {
    render();
    return;
  }
  const pct = item.size ? Math.min(100, (item.downloaded / item.size) * 100) : 0;
  const bar = row.querySelector(".progress-bar");
  const text = row.querySelector(".progress-text");
  const wrap = row.querySelector(".progress");
  const timeLeft = row.querySelector(".col-timeleft");
  if (bar) bar.style.width = `${pct}%`;
  if (text) text.textContent = `${Math.round(pct)}%`;
  if (wrap && item.speed) wrap.title = `${formatSize(item.speed)}/s`;
  if (timeLeft) timeLeft.textContent = formatTimeLeft(item);
}

// wire up

document.querySelectorAll(".nav-child").forEach((nav) => {
  nav.onclick = () => {
    document.querySelectorAll(".nav-child").forEach((n) => n.classList.remove("active"));
    nav.classList.add("active");
    state.filter = nav.dataset.filter;
    state.page = 1;
    state.selected.clear();
    render();
  };
});

el("nav-parent").onclick = () => {
  document.querySelector('.nav-child[data-filter="active"]').click();
};

el("search").addEventListener("input", (e) => {
  state.query = e.target.value.trim().toLowerCase();
  state.page = 1;
  render();
});

el("btn-refresh").onclick = () => refresh();
el("btn-retry-selected").onclick = () => retrySelected();
el("btn-remove-selected").onclick = () => removeSelected();
el("btn-cancel-selected").onclick = () => cancelSelected();

document.querySelectorAll(".pager-btn").forEach((btn) => {
  btn.onclick = () => {
    const items = visibleItems();
    const pages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
    const dir = btn.dataset.page;
    if (dir === "first") state.page = 1;
    if (dir === "prev") state.page -= 1;
    if (dir === "next") state.page += 1;
    if (dir === "last") state.page = pages;
    state.selected.clear();
    render();
  };
});

refresh();
connect();
setInterval(loadStats, 15000);
setInterval(render, 30000);
