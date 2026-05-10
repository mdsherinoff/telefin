# TeleFin
## Telegram → Sonarr/Radarr → Jellyfin

A Telegram **userbot** that watches for forwarded media files and automatically imports them into your Jellyfin media stack. Uses the full Telegram client API (MTProto via Telethon), so there is **no file size limit** — works with files up to 4 GB.

## Features

- Forward any video file to yourself on Telegram
- Downloads files directly to your server (no size limit)
- Restricts downloads to allowed Telegram users
- Automatically detects and triggers:
  - Sonarr for TV shows (S01E01 / 1x01 naming)
  - Radarr for movies
- Jellyfin updates automatically after import
- Runs as a `systemd` service
- Works great on:
  - Proxmox LXC
  - Ubuntu Server
  - Debian
  - Docker/LXC VMs

---

# Why a Userbot?

Standard Telegram bots are limited to **20 MB** file transfers. Since movie and TV show files are routinely 1–20+ GB, a regular bot cannot download them.

This project uses a **userbot** instead — a script that logs into your personal Telegram account using the official MTProto API. This gives it the same file access as the regular Telegram app, with a 4 GB limit per file.

> **Note:** The userbot runs as your personal Telegram account. For personal self-hosted use this is standard practice in the homelab community. Never use it for automation at scale.

---

# Architecture

```text
Telegram (forward file to Saved Messages)
   ↓
Userbot (Telethon — runs on your server)
   ↓
Incoming Download Folder
   ↓
Sonarr (TV) / Radarr (Movies)
   ↓
Organized Media Library
   ↓
Jellyfin Auto Detects
```

---

# Requirements

## Software

- Python 3.10+
- Sonarr
- Radarr
- Jellyfin
- Telegram account
- Telegram API credentials (free — from my.telegram.org)

## Recommended Setup

```text
/srv/media/
├── incoming/
├── movies/
└── tv/
```

---

# Get Telegram API Credentials

1. Go to **https://my.telegram.org**
2. Log in with your phone number
3. Click **"API development tools"**
4. Fill in the form (app name and platform can be anything)
5. Save your:
   - `api_id` (a number)
   - `api_hash` (a long string)

---

# Get Your Telegram User ID

Message this bot on Telegram:

https://t.me/userinfobot

Save your numeric user ID. Example:

```text
123456789
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/mdsherinoff/telefin.git /opt/telegram-jellyfin-bot
cd /opt/telegram-jellyfin-bot
```

## Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Configuration

Create `.env`:

```bash
nano .env
```

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

# Sonarr Setup

## Enable Completed Download Handling

Settings → Download Clients → Enable:
- Completed Download Handling

## Add Root Folder

Settings → Media Management → Root Folders:

```text
/srv/media/tv
```

---

# Radarr Setup

## Enable Completed Download Handling

Settings → Download Clients → Enable:
- Completed Download Handling

## Add Root Folder

```text
/srv/media/movies
```

---

# Jellyfin Setup

Add your media folders:

```text
/srv/media/movies
/srv/media/tv
```

Enable:
- Real Time Monitoring
- Library Auto Scan

Jellyfin will automatically detect newly imported files.

---

# First Run (Required)

The first run is **interactive** — Telethon needs to log in to your Telegram account and will prompt for your phone number and the confirmation code Telegram sends you.

You must do this manually once:

```bash
cd /opt/telegram-jellyfin-bot
source venv/bin/activate
python bot.py
```

You will see prompts like:

```text
Please enter your phone (or bot token): +31612345678
Please enter the code you received: 12345
```

After login, a `userbot_session.session` file is created in the project folder. This stores your authentication — **do not delete it** or you will need to log in again.

Once logged in, stop the process with `Ctrl+C` and set up the systemd service below.

---

# systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/telegram-media-bot.service
```

Paste:

```ini
[Unit]
Description=Telegram Userbot Media Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/opt/telegram-jellyfin-bot
ExecStart=/opt/telegram-jellyfin-bot/venv/bin/python bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-media-bot
sudo systemctl start telegram-media-bot
```

## View Logs

```bash
journalctl -u telegram-media-bot -f
```

---

# How to Use

1. Find a video file in any Telegram chat
2. **Forward it to your Saved Messages** (your own chat with yourself)
3. The userbot detects the file and starts downloading it to your server
4. You receive a reply in Saved Messages confirming:
   - Download complete
   - Detected media type (Movie or TV Show)
   - Save path
   - Whether Sonarr or Radarr was notified
5. Jellyfin picks it up automatically

## TV Show Detection

Files are detected as TV shows if their filename matches patterns like:

```text
Show.Name.S01E01.mkv
Show.Name.1x01.mkv
```

Everything else is treated as a movie.

---

# Supported File Types

```text
.mkv  .mp4  .avi  .mov  .wmv  .flv  .webm  .m4v
```

---

# Project Structure

```text
telegram-jellyfin-bot/
├── bot.py
├── requirements.txt
├── README.md
├── .env
├── userbot_session.session   ← created on first login, do not delete
└── utils/
    ├── radarr.py
    ├── sonarr.py
    └── telegram_helpers.py
```

---

# Security

## Allowed Users Only

Only Telegram user IDs listed in `ALLOWED_USERS` in your `.env` will trigger downloads. All other users are silently ignored.

## Recommendations

- Do NOT expose Sonarr/Radarr publicly
- Run behind a reverse proxy if remote access is needed
- Use firewall rules to limit access
- Keep `.env` and `userbot_session.session` private
- Never commit `.env` or the session file to version control

---

# Example .gitignore

```gitignore
venv/
.env
*.session
__pycache__/
*.pyc
```

---

# Future Ideas

- Magnet/torrent link support
- Subtitle downloads
- Telegram progress bar during download
- Duplicate file detection
- Web dashboard
- Multi-user quotas
- Admin commands
- File size limits
- Request queue system

---

# requirements.txt

```text
telethon
python-dotenv
requests
```

---

# License

MIT License

---

# Disclaimer

Only download and manage media you legally own or are authorized to access.
