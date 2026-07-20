# TeleFin

**Telegram → Sonarr / Radarr → Jellyfin**

A Telegram *userbot* that watches for video files and automatically imports
them into your media stack. Because it uses the full Telegram client API
(MTProto), there's **no 20 MB bot limit** — it handles files up to **4 GB**.

Send a movie or show to your Saved Messages (or a shared group), and TeleFin
downloads it, hands it to Sonarr/Radarr, and Jellyfin picks it up.

## Features

- No file size limit (up to 4 GB per file)
- Download queue with live progress in Telegram + a web dashboard
- Auto-detects TV vs. movie and notifies Sonarr / Radarr, with automatic
  re-notify if a completed download never got picked up
- Watch your Saved Messages **or** a group of allowed users
- SQLite history, duplicate detection, crash-safe restarts
- Reconfigure most settings from the dashboard's Settings page instead of
  editing `.env` by hand
- Restricts downloads to allowed Telegram user IDs

## Quick start

```yaml
# docker-compose.yml
services:
  telefin:
    image: xherxn/telefin:latest
    container_name: telefin
    restart: unless-stopped
    env_file: ./.env
    ports:
      - "8420:8420"
    volumes:
      - ./config:/config       # session + database live here
      - /srv/media:/srv/media   # your media folder
```

First-time login (creates the Telegram session), then start it:

```bash
docker compose run --rm telefin python login.py
docker compose up -d
```

Dashboard: `http://YOUR_SERVER_IP:8420`

## Configuration

Set these in a `.env` file (see `.env.example` in the repo):

| Variable | What it is |
|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | From my.telegram.org |
| `ALLOWED_USERS` | Comma-separated Telegram user IDs allowed to send files |
| `WATCH_CHAT` | `me` (Saved Messages) or a group ID, e.g. `me,-1001234567890` |
| `DOWNLOAD_DIR` | Where files land (must match Sonarr/Radarr's path) |
| `DOWNLOAD_DIR_MOVIES` / `DOWNLOAD_DIR_TV` | Optional — split movies/TV onto separate paths (e.g. separate drives); overrides `DOWNLOAD_DIR` per type |
| `SONARR_URL` / `SONARR_API_KEY` | Optional — TV imports |
| `RADARR_URL` / `RADARR_API_KEY` | Optional — movie imports |

## Tags

- `latest` — most recent tagged release
- `X.Y.Z` / `X.Y` — pinned versions (e.g. `0.2.0`, `0.2`), published from git tags `vX.Y.Z`

Built for `linux/amd64` and `linux/arm64`.

📖 Full docs & source: https://github.com/mdsherinoff/telefin
