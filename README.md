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
Userbot — Telethon (runs on your server)
   ↓
/srv/media/incoming
   ↓
Sonarr (TV) / Radarr (Movies)
   ↓
/srv/media/tv or /srv/media/movies
   ↓
Jellyfin auto detects
```

---

## Requirements

- Python 3.10+
- `python3.12-venv` (on Debian/Ubuntu)
- Sonarr
- Radarr
- Jellyfin
- A Telegram account
- Telegram API credentials (free — from my.telegram.org)

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
git clone https://github.com/mdsherinoff/telefin.git /opt/telegram-jellyfin-bot
cd /opt/telegram-jellyfin-bot
```

---

## Step 4 — Install Python venv

```bash
apt install python3.12-venv -y
```

---

## Step 5 — Create Virtual Environment and Install Dependencies

```bash
cd /opt/telegram-jellyfin-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Step 6 — Create .env

```bash
nano .env
```

Fill in your values:

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
cd /opt/telegram-jellyfin-bot
source venv/bin/activate
python bot.py
```

You will see:

```text
Please enter your phone (or bot token): +31612345678
Please enter the code you received: 12345
Signed in successfully as Your Name
```

After login, a `userbot_session.session` file is created in the project folder. This stores your authentication, **do not delete it** or you will need to log in again.

Once signed in, stop the process with `Ctrl+C` and move on to the next step.

---

## Step 9 — Install systemd Service

Copy the service file:

```bash
cp services/telegram-media-bot.service /etc/systemd/system/telegram-media-bot.service
```

The service file already has `User=root` set. If you want to run as a different user, edit it first:

```bash
nano /etc/systemd/system/telegram-media-bot.service
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable telegram-media-bot
systemctl start telegram-media-bot
```

Check it is running:

```bash
systemctl status telegram-media-bot
```

View live logs:

```bash
journalctl -u telegram-media-bot -f
```

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

## Future Ideas

- Magnet/torrent link support
- Download progress updates in Telegram
- Subtitle downloads
- Duplicate file detection
- Web dashboard
- Multi-user quotas
- File size limits
- Request queue system

---

## License

MIT License

---

## Disclaimer

Only download and manage media you legally own or are authorized to access.
