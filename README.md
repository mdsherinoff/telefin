# TeleFin
## Telegram → Sonarr/Radarr → Jellyfin

A Telegram bot that accepts media uploads and automatically imports them into your Jellyfin media stack.

## Features

- Upload media files directly to Telegram
- Downloads files to your server
- Restricts uploads to allowed Telegram users
- Automatically triggers:
  - Sonarr for TV shows
  - Radarr for movies
- Jellyfin updates automatically after import
- Runs as a `systemd` service
- Works great on:
  - Proxmox
  - Ubuntu Server
  - Debian
  - Docker/LXC VMs

---

# Architecture

```text
Telegram
   ↓
Telegram Bot
   ↓
Incoming Download Folder
   ↓
Sonarr / Radarr Import
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
- Telegram Bot Token

## Recommended Setup

```text
/srv/media/
├── incoming/
├── movies/
└── tv/
```

Example:

```text
/srv/media/incoming
/srv/media/movies
/srv/media/tv
```

---

# Create Telegram Bot

Talk to BotFather on Telegram:

https://t.me/BotFather

Create a bot:

```text
/newbot
```

Save the bot token.

Example:

```text
123456789:ABCDEF123456
```

---

# Get Your Telegram User ID

Message this bot on Telegram:

https://t.me/userinfobot

Save your numeric user ID.

Example:

```text
123456789
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/mdsherinoff/telegram-jellyfin-bot.git /opt/telegram-jellyfin-bot

cd /opt/telegram-jellyfin-bot
```

---

## Create Python Virtual Environment

```bash
python3 -m venv venv

source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Configuration

Create `.env`

```env
BOT_TOKEN=YOUR_BOT_TOKEN

ALLOWED_USERS=123456789,987654321

DOWNLOAD_DIR=/srv/media/incoming

SONARR_URL=http://localhost:8989
SONARR_API_KEY=YOUR_SONARR_API_KEY

RADARR_URL=http://localhost:7878
RADARR_API_KEY=YOUR_RADARR_API_KEY
```

---

# Sonarr Setup

In Sonarr:

## Enable Completed Download Handling

Settings → Download Clients

Enable:

- Completed Download Handling

---

## Add Import Folder

Settings → Media Management

Root Folder:

```text
/srv/media/tv
```

---

# Radarr Setup

In Radarr:

## Enable Completed Download Handling

Settings → Download Clients

Enable:

- Completed Download Handling

---

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

# Running the Bot

## Start Manually

```bash
source venv/bin/activate

python bot.py
```

---

# systemd Service

Create service:

```bash
sudo nano /etc/systemd/system/telegram-media-bot.service
```

Paste:

```ini
[Unit]
Description=Telegram Media Bot
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

---

## Enable Service

```bash
sudo systemctl daemon-reload

sudo systemctl enable telegram-media-bot

sudo systemctl start telegram-media-bot
```

---

## View Logs

```bash
journalctl -u telegram-media-bot -f
```

---

# Security

## Allowed Users Only

Only Telegram users listed in:

```env
ALLOWED_USERS=
```

can upload media.

All other users are ignored.

---

## Recommended

- Do NOT expose Sonarr/Radarr publicly
- Run behind a reverse proxy if remote access is needed
- Use firewall rules
- Keep API keys secret
- Never commit `.env`

---

# Example Workflow

1. Send a movie file to Telegram bot
2. Bot downloads file
3. Bot saves to:

```text
/srv/media/incoming
```

4. Bot notifies Sonarr/Radarr
5. Sonarr/Radarr:
   - Renames files
   - Organizes folders
   - Moves media
6. Jellyfin automatically detects new media

---

# Suggested Repository Structure

```text
telegram-jellyfin-bot/
├── bot.py
├── requirements.txt
├── README.md
├── .env.example
├── services/
│   └── telegram-media-bot.service
└── utils/
    ├── radarr.py
    ├── sonarr.py
    └── telegram_helpers.py
```

---

# Future Ideas

## Planned Features

- Magnet link support
- Torrent support
- Auto movie/show detection
- Subtitle downloads
- Telegram progress updates
- Duplicate detection
- Web dashboard
- Multi-user quotas
- Admin commands
- File size limits
- Request queue system

---

# requirements.txt

```text
python-telegram-bot
python-dotenv
requests
```

---

# Example `.gitignore`

```gitignore
venv/
.env
__pycache__/
*.pyc
```

---

# License

MIT License

---

# Disclaimer

Only download and manage media you legally own or are authorized to access.
