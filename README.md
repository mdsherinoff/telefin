# TeleFin

## Telegram → Sonarr/Radarr → Jellyfin

A Telegram **userbot** that watches for forwarded media files and automatically imports them into your Jellyfin media stack. Uses the full Telegram client API (MTProto via Telethon), so there is **no file size limit**, works with files up to 4 GB.

---

## Why a Userbot and Not a Bot?

Standard Telegram bots are limited to **20 MB** per file transfer. Since movie and TV show files are much above that size, a regular bot cannot download them.
So, this project uses a **userbot**; a script that logs into your personal Telegram account using the official MTProto API. This gives it the same file access as the regular Telegram app, with a 4 GB limit per file.

---

## Features

- Forward any video file to yourself on Telegram
- Downloads files directly to your server with no size limit
- **Download queue** — files are processed in order, with a configurable concurrency limit instead of racing for bandwidth
- **Live progress** — a progress bar with speed and ETA, both in your Telegram chat and on the web dashboard
- **Web dashboard** (Radarr/Sonarr style) — active queue, history, stats, retry and remove, live over WebSocket
- **SQLite history** — every download is recorded; survives restarts
- **Duplicate detection** — a file you already downloaded is skipped
- **Crash-safe** — downloads interrupted by a restart are marked failed and can be retried from the dashboard
- Restricts downloads to allowed Telegram user IDs
- Auto-detects media type and triggers:
  - Sonarr for TV shows (`S01E01` / `1x01` naming)
  - Radarr for movies
- Jellyfin picks up new files automatically
- Runs as a `systemd` service
- Tested on Proxmox Ubuntu LXC

---

## Architecture

```text
Telegram (forward file to Saved Messages)
   ↓
Userbot — Telethon  ──►  enqueue job (SQLite)
   ↓                          │
Download worker(s)  ◄─────────┘
   │  progress ──►  Telegram message + Web dashboard (WebSocket)
   ↓
/srv/media/incoming
   ↓
Sonarr (TV) / Radarr (Movies)
   ↓
/srv/media/tv or /srv/media/movies
   ↓
Jellyfin auto detects
```

Everything runs in **one Python process**: the Telethon userbot, the download
queue, and the FastAPI web dashboard all share a single asyncio event loop.

### Project layout

```text
telefin/
├── main.py          entrypoint — wires bot + queue + web into one loop
├── config.py        environment configuration
├── bot.py           Telethon client + new-message handler (enqueues jobs)
├── worker.py        download queue + workers + progress
├── db.py            SQLite (queue + history)
├── events.py        in-process pub/sub for live updates
├── webapp.py        FastAPI REST + WebSocket
├── web/             dashboard (static HTML/CSS/JS, no build step)
└── utils/           sonarr / radarr triggers, helpers
```

---

## Running with Docker (recommended)

The whole stack ships as a single container. A `docker-compose.yml` is
included at the repo root.

### 1. Configure

```bash
cp telefin/.env.example telefin/.env
nano telefin/.env          # fill in API creds, ALLOWED_USERS, *arr keys
```

Two things that matter for Docker specifically:

- **`DOWNLOAD_DIR`** must be a path that is (a) mounted into the container and
  (b) the exact same path Sonarr/Radarr see. Otherwise the scan trigger points
  at a directory they can't find. With the default `/srv/media` mount, use
  something like `DOWNLOAD_DIR=/srv/media/incoming`.
- **`SONARR_URL` / `RADARR_URL`** — if the \*arr apps run directly on the host,
  address them as `http://host.docker.internal:8989` (the Compose file already
  wires up `host.docker.internal`). If they run in Docker too, use their
  service names on a shared network instead.

The session file and SQLite database are stored on the `./config` volume, so
they survive rebuilds. You don't set `SESSION_NAME`/`DB_PATH` for Docker —
Compose points them at `/config` automatically.

### 2. One-time Telegram login

Telethon needs an interactive login once to create the session file. Run the
helper (it prompts for your phone number and the code Telegram sends):

```bash
docker compose run --rm telefin python login.py
```

You only ever do this once — the session lands in `./config`.

### 3. Start

```bash
docker compose up -d
```

Dashboard: `http://YOUR_SERVER_IP:8420`. Logs: `docker compose logs -f`.

To update after pulling changes: `docker compose up -d --build`.

> Prefer a bare-metal / systemd install instead? Skip this section and follow
> the manual steps below.

---

## Requirements

- Python 3.10+
- `python3.12-venv` (on Debian/Ubuntu)
- Sonarr
- Radarr
- Jellyfin
- Telegram account
- Telegram API credentials (find from my.telegram.org)

### Recommended media folder layout

```text
/srv/media/
├── incoming/
├── movies/
└── tv/
```

---

## Step 1 — Get Telegram API Credentials

1. Go to **https://my.telegram.org**
2. Log in with your phone number
3. Click **"API development tools"**
4. Fill in the form; app name and platform can be anything
5. Save your `api_id` (a number) and `api_hash` (a long string)

---

## Step 2 — Get Your Telegram User ID

Message this bot on Telegram: **https://t.me/userinfobot**

Save your numeric user ID, for example `123456789`.

---

## Step 3 — Clone the Repository

```bash
git clone https://github.com/mdsherinoff/telefin.git /opt/telefin
```

> **Note:** the application code lives in the inner `telefin/` folder, so all
> the following steps happen in `/opt/telefin/telefin`.

---

## Step 4 — Install Python venv

```bash
apt install python3.12-venv -y
```

---

## Step 5 — Create Virtual Environment and Install Dependencies

```bash
cd /opt/telefin/telefin
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 6 — Create .env

Copy the example file and fill in your values:

```bash
cd /opt/telefin/telefin
cp .env.example .env
nano .env
```

The required values:

```env
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here

ALLOWED_USERS=123456789

DOWNLOAD_DIR=/srv/media/incoming

SONARR_URL=http://localhost:8989
SONARR_API_KEY=your_sonarr_api_key

RADARR_URL=http://localhost:7878
RADARR_API_KEY=your_radarr_api_key
```

---

## Step 7 — Create Media Directories

```bash
mkdir -p /srv/media/incoming /srv/media/movies /srv/media/tv
```

---

## Step 8 — First Run (Interactive Login)

The first run requires an interactive login. Telethon will ask for your phone number and the confirmation code Telegram sends you. **This only needs to be done once.**

```bash
cd /opt/telefin/telefin
source venv/bin/activate
python main.py
```

You will see:

```text
Please enter your phone number: +31612345678
Please enter the code you received: 12345
Signed in successfully as Your Name
```

After login, a `userbot_session.session` file is created in the project folder. This stores your authentication, **do not delete it** or you will need to log in again.

Once signed in, stop the process with `Ctrl+C` and move on to the next step.

---

## Step 9 — Install systemd Service

Copy the service file:

```bash
cp /opt/telefin/telefin/services/telefin.service /etc/systemd/system/telefin.service
```

The service file has `User=root` set and expects the repo at `/opt/telefin`. If you cloned somewhere else or want to run as a different user, edit it first:

```bash
nano /etc/systemd/system/telefin.service
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable telefin
systemctl start telefin
```

Check it is running:

```bash
systemctl status telefin
```

View live logs:

```bash
journalctl -u telefin -f
```

---

## Web Dashboard

Once the service is running, open:

```text
http://YOUR_SERVER_IP:8420
```

You get a Sonarr/Radarr-style interface (dark theme, sidebar navigation,
flat table) with:

- **Queue** — files currently downloading, with live progress, speed and ETA
- **History** — everything downloaded, with the Sonarr/Radarr result
- **Failed** — anything that errored, with a one-click **Retry**
- Live stats (active / completed / failed / total downloaded)
- Filename filter box and live page counters

The dashboard updates in real time over a WebSocket — no refreshing needed.

### Optional: protect the dashboard

For access beyond your LAN, set **both** HTTP Basic auth credentials in `.env`:

```env
WEB_USERNAME=admin
WEB_PASSWORD=a_long_random_password
```

Leave them blank for open LAN-only access. You can also change the port
(`WEB_PORT`) or disable the dashboard entirely (`WEB_ENABLED=false`).

---

## Sonarr Setup

Settings → Download Clients → enable **Completed Download Handling**

Settings → Media Management → Root Folders → add:

```text
/srv/media/tv
```

---

## Radarr Setup

Settings → Download Clients → enable **Completed Download Handling**

Settings → Media Management → Root Folders → add:

```text
/srv/media/movies
```

---

## Jellyfin Setup

Add libraries pointing to:

```text
/srv/media/movies
/srv/media/tv
```

Enable:

- Real Time Monitoring
- Library Auto Scan

---

## How to Use

1. Find a video file in any Telegram chat
2. Forward it to your **Saved Messages** (your own chat with yourself)
3. The userbot detects the file and starts downloading it to your server
4. You receive a reply in Saved Messages:

```
Download complete

Type: Movie
File: The.Movie.2024.mkv
Path: /srv/media/incoming/The.Movie.2024.mkv

Radarr notified
```

5. Sonarr or Radarr renames and moves the file, Jellyfin picks it up automatically

---

## TV Show Detection

Files are detected as TV shows if their filename matches:

```text
Show.Name.S01E01.mkv    ← matched
Show.Name.1x01.mkv      ← matched
The.Movie.2024.mkv      ← treated as movie
```

---

## Supported File Types

```text
.mkv  .mp4  .avi  .mov  .wmv  .flv  .webm  .m4v
```

---

## Troubleshooting

**The bot ignores my forwarded files.**
Almost always a wrong `ALLOWED_USERS`. It must be your _numeric_ Telegram ID
(from [@userinfobot](https://t.me/userinfobot)), not your username. Also check
you are forwarding to the chat set in `WATCH_CHAT` (default: Saved Messages)
and that the file type is in the supported list.

**Startup fails with "Configuration problem(s) found".**
The message tells you exactly which `.env` value is missing and where to get
it. Fix it and start again.

**"Sonarr scan failed" / "Radarr scan failed" after a download.**

- Wrong `SONARR_URL`/`RADARR_URL` or API key (Settings → General in each app).
- Running in Docker with the \*arr apps on the host? Use
  `http://host.docker.internal:8989`, not `localhost`.
- Path mismatch: Sonarr/Radarr must see `DOWNLOAD_DIR` at the **same path**
  TeleFin writes to. In Docker, mount the media folder identically in all
  containers.

**Telegram asks for a login code every time / session lost.**
The `.session` file was deleted or is not writable. Bare-metal: keep
`userbot_session.session` next to `main.py`. Docker: make sure the `./config`
volume exists and is writable.

**Dashboard loads but shows "reconnecting…".**
A reverse proxy in front of TeleFin must forward WebSocket upgrades for `/ws`
(for nginx: `proxy_set_header Upgrade $http_upgrade; proxy_set_header
Connection "upgrade";`).

**Downloads are slow.**
That's Telegram's server-side per-connection limit, not a bug. Keep
`MAX_CONCURRENT_DOWNLOADS=1` so a single file gets the full rate.

---

## License

MIT License

---

## Disclaimer

Only download and manage media you legally own or are authorized to access.
