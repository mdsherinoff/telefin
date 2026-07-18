const PAGE_SIZE = 50;

const state = {
  filter: "active",
  query: "",
  page: 1,
  items: new Map(),    
  selected: new Set(),
};

const el = (id) => document.getElementById(id);

// Font Awesome Free solid-style glyphs (CC BY 4.0) -- matches Sonarr's own
// icon set (Helpers/Props/icons.ts) rather than an unrelated stroke style.
const fa = (viewBox, path, size = 16) =>
  `<svg viewBox="${viewBox}" width="${size}" height="${size}" fill="currentColor">${path}</svg>`;

const ICONS = {
  // Status column -- mirrors Sonarr's QUEUED/DOWNLOADING/DOWNLOAD/WARNING/DANGER icons.
  queued: fa("0 0 640 512", `<path d="M537.6 226.6c4.1-10.7 6.4-22.4 6.4-34.6 0-53-43-96-96-96-19.7 0-38.1 6-53.3 16.2C367 64.2 315.3 32 256 32c-88.4 0-160 71.6-160 160 0 2.7.1 5.4.2 8.1C40.2 219.8 0 273.2 0 336c0 79.5 64.5 144 144 144h368c70.7 0 128-57.3 128-128 0-61.9-44-113.6-102.4-125.4z"/>`),
  downloading: fa("0 0 640 512", `<path d="M537.6 226.6c4.1-10.7 6.4-22.4 6.4-34.6 0-53-43-96-96-96-19.7 0-38.1 6-53.3 16.2C367 64.2 315.3 32 256 32c-88.4 0-160 71.6-160 160 0 2.7.1 5.4.2 8.1C40.2 219.8 0 273.2 0 336c0 79.5 64.5 144 144 144h368c70.7 0 128-57.3 128-128 0-61.9-44-113.6-102.4-125.4zm-132.9 88.7L299.3 420.7c-6.2 6.2-16.4 6.2-22.6 0L171.3 315.3c-10.1-10.1-2.9-27.3 11.3-27.3H248V176c0-8.8 7.2-16 16-16h48c8.8 0 16 7.2 16 16v112h65.4c14.2 0 21.4 17.2 11.3 27.3z"/>`),
  importing: fa("0 0 512 512", `<path d="M216 0h80c13.3 0 24 10.7 24 24v168h87.7c17.8 0 26.7 21.5 14.1 34.1L269.7 378.3c-7.5 7.5-19.8 7.5-27.3 0L90.1 226.1c-12.6-12.6-3.7-34.1 14.1-34.1H192V24c0-13.3 10.7-24 24-24zm296 376v112c0 13.3-10.7 24-24 24H24c-13.3 0-24-10.7-24-24V376c0-13.3 10.7-24 24-24h146.7l49 49c20.1 20.1 52.5 20.1 72.6 0l49-49H488c13.3 0 24 10.7 24 24zm-124 88c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20zm64 0c0-11-9-20-20-20s-20 9-20 20 9 20 20 20 20-9 20-20z"/>`),
  completed: fa("0 0 512 512", `<path d="M173.898 439.404l-166.4-166.4c-9.997-9.997-9.997-26.206 0-36.204l36.203-36.204c9.997-9.998 26.207-9.998 36.204 0L192 312.69 432.095 72.596c9.997-9.997 26.207-9.997 36.204 0l36.203 36.204c9.997 9.997 9.997 26.206 0 36.204l-294.4 294.401c-9.998 9.997-26.207 9.997-36.204-.001z"/>`),
  failed: fa("0 0 512 512", `<path d="M504 256c0 136.997-111.043 248-248 248S8 392.997 8 256C8 119.083 119.043 8 256 8s248 111.083 248 248zm-248 50c-25.405 0-46 20.595-46 46s20.595 46 46 46 46-20.595 46-46-20.595-46-46-46zm-43.673-165.346l7.418 136c.347 6.364 5.609 11.346 11.982 11.346h48.546c6.373 0 11.635-4.982 11.982-11.346l7.418-136c.375-6.874-5.098-12.654-11.982-12.654h-63.383c-6.884 0-12.356 5.78-11.981 12.654z"/>`),
  skipped: fa("0 0 512 512", `<path d="M500.5 231.4l-192-160C287.9 54.3 256 68.6 256 96v320c0 27.4 31.9 41.8 52.5 24.6l192-160c15.3-12.8 15.3-36.4 0-49.2zm-256 0l-192-160C31.9 54.3 0 68.6 0 96v320c0 27.4 31.9 41.8 52.5 24.6l192-160c15.3-12.8 15.3-36.4 0-49.2z"/>`),
  cancelled: fa("0 0 512 512", `<path d="M256 8C119.034 8 8 119.033 8 256s111.034 248 248 248 248-111.034 248-248S392.967 8 256 8zm130.108 117.892c65.448 65.448 70 165.481 20.677 235.637L150.47 105.216c70.204-49.356 170.226-44.735 235.638 20.676zM125.892 386.108c-65.448-65.448-70-165.481-20.677-235.637L361.53 406.784c-70.203 49.356-170.226 44.736-235.638-20.676z"/>`),
  // Row/toolbar actions -- REFRESH/REMOVE/TABLE mirror Sonarr's toolbar icons exactly.
  retry: fa("0 0 512 512", `<path d="M440.65 12.57l4 82.77A247.16 247.16 0 0 0 255.83 8C134.73 8 33.91 94.92 12.29 209.82A12 12 0 0 0 24.09 224h49.05a12 12 0 0 0 11.67-9.26 175.91 175.91 0 0 1 317-56.94l-101.46-4.86a12 12 0 0 0-12.57 12v47.41a12 12 0 0 0 12 12H500a12 12 0 0 0 12-12V12a12 12 0 0 0-12-12h-47.37a12 12 0 0 0-11.98 12.57zM255.83 432a175.61 175.61 0 0 1-146-77.8l101.8 4.87a12 12 0 0 0 12.57-12v-47.4a12 12 0 0 0-12-12H12a12 12 0 0 0-12 12V500a12 12 0 0 0 12 12h47.35a12 12 0 0 0 12-12.6l-4.15-82.57A247.17 247.17 0 0 0 255.83 504c121.11 0 221.93-86.92 243.55-201.82a12 12 0 0 0-11.8-14.18h-49.05a12 12 0 0 0-11.67 9.26A175.86 175.86 0 0 1 255.83 432z"/>`, 15),
  remove: fa("0 0 352 512", `<path d="M242.72 256l100.07-100.07c12.28-12.28 12.28-32.19 0-44.48l-22.24-22.24c-12.28-12.28-32.19-12.28-44.48 0L176 189.28 75.93 89.21c-12.28-12.28-32.19-12.28-44.48 0L9.21 111.45c-12.28 12.28-12.28 32.19 0 44.48L109.28 256 9.21 356.07c-12.28 12.28-12.28 32.19 0 44.48l22.24 22.24c12.28 12.28 32.2 12.28 44.48 0L176 322.72l100.07 100.07c12.28 12.28 32.2 12.28 44.48 0l22.24-22.24c12.28-12.28 12.28-32.19 0-44.48L242.72 256z"/>`, 15),
  stop: fa("0 0 512 512", `<path d="M256 8C119 8 8 119 8 256s111 248 248 248 248-111 248-248S393 8 256 8zm96 328c0 8.8-7.2 16-16 16H176c-8.8 0-16-7.2-16-16V176c0-8.8 7.2-16 16-16h160c8.8 0 16 7.2 16 16v160z"/>`, 15),
  notify: fa("0 0 448 512", `<path d="M224 512c35.32 0 63.97-28.65 63.97-64H160.03c0 35.35 28.65 64 63.97 64zm215.39-149.71c-19.32-20.76-55.47-51.99-55.47-154.29 0-77.7-54.48-139.9-127.94-155.16V32c0-17.67-14.32-32-31.98-32s-31.98 14.33-31.98 32v20.84C118.56 68.1 64.08 130.3 64.08 208c0 102.3-36.15 133.53-55.47 154.29-6 6.45-8.66 14.16-8.61 21.71.11 16.4 12.98 32 32.1 32h383.8c19.12 0 32-15.6 32.1-32 .05-7.55-2.61-15.27-8.61-21.71z"/>`, 15),
  gear: fa("0 0 512 512", `<path d="M464 32H48C21.49 32 0 53.49 0 80v352c0 26.51 21.49 48 48 48h416c26.51 0 48-21.49 48-48V80c0-26.51-21.49-48-48-48zM224 416H64v-96h160v96zm0-160H64v-96h160v96zm224 160H288v-96h160v96zm0-160H288v-96h160v96z"/>`, 15),
  sortDesc: `<svg class="sort-caret" viewBox="0 0 320 512" width="12" height="12" fill="currentColor"><path d="M31.3 192h257.3c17.8 0 26.7 21.5 14.1 34.1L174.1 354.8c-7.8 7.8-20.5 7.8-28.3 0L17.2 226.1C4.6 213.5 13.5 192 31.3 192z"/></svg>`,
  eye: fa("0 0 576 512", `<path d="M288 144a110.94 110.94 0 0 0-31.24 5 55.4 55.4 0 0 1 7.24 27 56 56 0 0 1-56 56 55.4 55.4 0 0 1-27-7.24A111.71 111.71 0 1 0 288 144zm284.52 97.4C518.29 135.59 410.93 64 288 64S57.68 135.64 3.48 241.41a32.35 32.35 0 0 0 0 29.19C57.71 376.41 165.07 448 288 448s230.32-71.64 284.52-177.41a32.35 32.35 0 0 0 0-29.19zM288 400c-98.65 0-189.09-55-237.93-144C98.91 167 189.34 112 288 112s189.09 55 237.93 144C477.1 345 386.66 400 288 400z"/>`, 15),
  eyeSlash: fa("0 0 640 512", `<path d="M634 471L36 3.51A16 16 0 0 0 13.51 6l-10 12.49A16 16 0 0 0 6 41l598 467.49a16 16 0 0 0 22.49-2.49l10-12.49A16 16 0 0 0 634 471zM296.79 146.47l134.79 105.38C429.36 191.91 380.48 144 320 144a112.26 112.26 0 0 0-23.21 2.47zm46.42 219.07L208.42 260.16C210.65 320.09 259.53 368 320 368a113 113 0 0 0 23.21-2.46zM320 112c98.65 0 189.09 55 237.93 144a285.53 285.53 0 0 1-44 60.2l37.74 29.5a333.7 333.7 0 0 0 52.9-75.11 32.35 32.35 0 0 0 0-29.19C550.29 135.59 442.93 64 320 64c-36.7 0-71.71 7-104.63 18.81l46.41 36.29c18.94-4.3 38.34-7.1 58.22-7.1zm0 288c-98.65 0-189.08-55-237.93-144a285.47 285.47 0 0 1 44.05-60.19l-37.74-29.5a333.6 333.6 0 0 0-52.89 75.1 32.35 32.35 0 0 0 0 29.19C89.72 376.41 197.08 448 320 448c36.7 0 71.71-7.05 104.63-18.81l-46.41-36.28C359.28 397.2 339.89 400 320 400z"/>`, 15),
};

// Settings page -- mirrors the .env.example groupings (Basic vs Advanced).
const SETTINGS_SCHEMA = [
  { key: "TELEGRAM_API_ID", label: "Telegram API ID", type: "text", group: "basic", help: "From my.telegram.org → API development tools" },
  { key: "TELEGRAM_API_HASH", label: "Telegram API Hash", type: "password", group: "basic" },
  { key: "ALLOWED_USERS", label: "Allowed Users", type: "text", group: "basic", help: "Comma-separated Telegram user IDs allowed to send files" },
  { key: "WATCH_CHAT", label: "Watch Chat", type: "text", group: "basic", help: "me, a group/channel ID, or a comma-separated mix" },
  { key: "DOWNLOAD_DIR", label: "Download Directory", type: "text", group: "basic", help: "Fallback path; must match Sonarr/Radarr's view of the same folder" },
  { key: "DOWNLOAD_DIR_MOVIES", label: "Movies Download Directory", type: "text", group: "basic", help: "Optional override for movies (e.g. a separate drive)" },
  { key: "DOWNLOAD_DIR_TV", label: "TV Download Directory", type: "text", group: "basic", help: "Optional override for TV shows" },
  { key: "SONARR_URL", label: "Sonarr URL", type: "text", group: "basic" },
  { key: "SONARR_API_KEY", label: "Sonarr API Key", type: "password", group: "basic" },
  { key: "RADARR_URL", label: "Radarr URL", type: "text", group: "basic" },
  { key: "RADARR_API_KEY", label: "Radarr API Key", type: "password", group: "basic" },

  { key: "SESSION_NAME", label: "Session Name", type: "text", group: "advanced", help: "Telegram session file name" },
  { key: "MAX_CONCURRENT_DOWNLOADS", label: "Max Concurrent Downloads", type: "text", group: "advanced" },
  { key: "PROGRESS_INTERVAL", label: "Progress Update Interval (s)", type: "text", group: "advanced" },
  { key: "MAX_DOWNLOAD_RETRIES", label: "Max Download Retries", type: "text", group: "advanced" },
  { key: "RETRY_BACKOFF_SECONDS", label: "Retry Backoff (s)", type: "text", group: "advanced" },
  { key: "ALLOWED_EXTENSIONS", label: "Allowed Extensions", type: "text", group: "advanced", help: "Comma-separated, e.g. mkv,mp4,avi" },
  { key: "DB_PATH", label: "Database Path", type: "text", group: "advanced" },
  { key: "NOTIFY_INTERVAL_MINUTES", label: "Re-notify Interval (min)", type: "text", group: "advanced", help: "Re-announce stuck completed downloads to Sonarr/Radarr. 0 disables." },
  { key: "RETENTION_DAYS", label: "History Retention (days)", type: "text", group: "advanced", help: "Auto-delete finished history older than this. 0 disables." },
  { key: "WEB_ENABLED", label: "Web Dashboard Enabled", type: "checkbox", group: "advanced" },
  { key: "WEB_HOST", label: "Web Host", type: "text", group: "advanced" },
  { key: "WEB_PORT", label: "Web Port", type: "text", group: "advanced" },
  { key: "WEB_USERNAME", label: "Web Username", type: "text", group: "advanced" },
  { key: "WEB_PASSWORD", label: "Web Password", type: "password", group: "advanced" },
  { key: "LOG_LEVEL", label: "Log Level", type: "select", group: "advanced", options: ["DEBUG", "INFO", "WARNING", "ERROR"] },
  { key: "LOG_FILE", label: "Log File", type: "text", group: "advanced", help: "Optional; leave blank to log to stdout only" },
  { key: "LOG_MAX_BYTES", label: "Log Max Bytes", type: "text", group: "advanced" },
  { key: "LOG_BACKUP_COUNT", label: "Log Backup Count", type: "text", group: "advanced" },
];

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

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
    <td class="col-type"><span class="tag ${item.media_type === "tv" ? "tag-tv" : "tag-movie"}">${item.media_type === "tv" ? "TV" : "Movie"}</span></td>
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

// settings

function renderSettingsField(field, value) {
  const help = field.help ? `<div class="field-help">${escapeHtml(field.help)}</div>` : "";

  if (field.type === "checkbox") {
    const checked = TRUE_VALUES.has(String(value).toLowerCase()) ? "checked" : "";
    return `
      <div class="field-row field-row-checkbox">
        <label class="field-label">
          <input type="checkbox" data-key="${field.key}" ${checked} />
          ${escapeHtml(field.label)}
        </label>
      </div>`;
  }

  if (field.type === "select") {
    const opts = field.options
      .map((o) => `<option value="${o}" ${o === value ? "selected" : ""}>${o}</option>`)
      .join("");
    return `
      <div class="field-row">
        <label class="field-label">${escapeHtml(field.label)}</label>
        <div class="field-control">
          <select data-key="${field.key}">${opts}</select>
          ${help}
        </div>
      </div>`;
  }

  if (field.type === "password") {
    return `
      <div class="field-row">
        <label class="field-label">${escapeHtml(field.label)}</label>
        <div class="field-control">
          <div class="field-control-password">
            <input type="password" data-key="${field.key}" value="${escapeHtml(value)}" autocomplete="off" />
            <button type="button" class="field-reveal" data-reveal="${field.key}" title="Show/hide">${ICONS.eye}</button>
          </div>
          ${help}
        </div>
      </div>`;
  }

  return `
    <div class="field-row">
      <label class="field-label">${escapeHtml(field.label)}</label>
      <div class="field-control">
        <input type="text" data-key="${field.key}" value="${escapeHtml(value)}" autocomplete="off" />
        ${help}
      </div>
    </div>`;
}

function renderSettingsForm(values) {
  el("settings-basic").innerHTML = SETTINGS_SCHEMA
    .filter((f) => f.group === "basic")
    .map((f) => renderSettingsField(f, values[f.key] ?? ""))
    .join("");
  el("settings-advanced").innerHTML = SETTINGS_SCHEMA
    .filter((f) => f.group === "advanced")
    .map((f) => renderSettingsField(f, values[f.key] ?? ""))
    .join("");

  document.querySelectorAll(".field-reveal").forEach((btn) => {
    btn.onclick = () => {
      const input = document.querySelector(`input[data-key="${btn.dataset.reveal}"]`);
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.innerHTML = showing ? ICONS.eye : ICONS.eyeSlash;
    };
  });
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  const values = await res.json();
  renderSettingsForm(values);
  el("settings-restart-banner").hidden = true;
}

function collectSettingsPayload() {
  const payload = {};
  for (const field of SETTINGS_SCHEMA) {
    if (field.type === "checkbox") {
      const input = document.querySelector(`input[data-key="${field.key}"]`);
      payload[field.key] = input.checked ? "true" : "false";
      continue;
    }
    const input = document.querySelector(`[data-key="${field.key}"]`);
    if (input) payload[field.key] = input.value;
  }
  return payload;
}

async function saveSettings() {
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectSettingsPayload()),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || "Save failed");
    el("settings-restart-banner").hidden = false;
    toast("Settings saved");
  } catch (e) {
    toast(e.message || "Save failed", "error");
  }
}

function showView(view) {
  el("queue-view").hidden = view !== "queue";
  el("settings-view").hidden = view !== "settings";
  el("nav-activity-group").classList.toggle("active", view === "queue");
  el("nav-settings-group").classList.toggle("active", view === "settings");
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
    showView("queue");
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

el("nav-settings").onclick = () => {
  showView("settings");
  loadSettings();
};

el("btn-toggle-advanced").onclick = () => {
  const group = el("settings-advanced-group");
  group.hidden = !group.hidden;
  el("advanced-toggle-label").textContent = group.hidden ? "Show Advanced" : "Hide Advanced";
};

el("btn-save-settings").onclick = () => saveSettings();

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
