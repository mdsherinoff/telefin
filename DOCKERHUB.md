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
- Auto-detects TV vs. movie and notifies Sonarr / Radarr
- Watch your Saved Messages **or** a group of allowed users
- SQLite history, duplicate detection, crash-safe restarts
- Restricts downloads to allowed Telegram user IDs

## Quick start

```yaml
# docker-compose.yml
services:
  telefin:
    image: YOURUSER/telefin:latest
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
| `SONARR_URL` / `SONARR_API_KEY` | Optional — TV imports |
| `RADARR_URL` / `RADARR_API_KEY` | Optional — movie imports |

## Tags

- `latest` — current build
- `0.1.0` — pinned version

Built for `linux/amd64` and `linux/arm64`.

📖 Full docs & source: <your GitHub repo link>
