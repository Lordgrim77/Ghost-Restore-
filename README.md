# 👻 Ghost Backup, Restore & Support Suite

[![Ubuntu Support](https://img.shields.io/badge/Ubuntu-20.04%20%7C%2022.04%20%7C%2024.04-orange?logo=ubuntu)](https://ubuntu.com)
[![Ghost CMS](https://img.shields.io/badge/Ghost%20CMS-5.x-blue?logo=ghost)](https://ghost.org)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A production-ready suite for Ghost CMS publications featuring:
1. **🎨 Custom Alto Theme & Support Portal**: Sleek Obsidian Monochrome theme, clean `/support/` portal with logged-in member case tracking, `/team/` showcase, and redesigned email templates.
2. **🤖 Telegram Bot & Backup Daemon**: 1-Click full backup & restore engine, drag-and-drop restore, and live two-way support case triage directly in Telegram.

---

## 📑 Table of Contents

- [🎨 Part 1: Theme Setup & Installation](#-part-1-theme-setup--installation)
  - [Option A: 1-Click Automated Theme Deployer (Recommended)](#option-a-1-click-automated-theme-deployer-recommended)
  - [Option B: Manual Theme Setup via Ghost Admin](#option-b-manual-theme-setup-via-ghost-admin)
  - [Theme Features & Support Portal](#theme-features--support-portal)
  - [👥 Team Page Customization (team.json)](#-team-page-customization-teamjson)
- [🤖 Part 2: Bot Setup & Installation](#-part-2-bot-setup--installation)
  - [Prerequisites (Telegram Bot & User ID)](#prerequisites-telegram-bot--user-id)
  - [Option A: 1-Click Interactive Automated Installer (Recommended)](#option-a-1-click-interactive-automated-installer-recommended)
  - [Option B: 1-Click Quick Support Hub & Bot Updater](#option-b-1-click-quick-support-hub--bot-updater)
  - [Option C: Manual Bot Installation](#option-c-manual-bot-installation)
  - [Configuration Reference (.env)](#configuration-reference-env)
  - [Nginx Reverse Proxy Configuration](#nginx-reverse-proxy-configuration)
  - [Service Management Commands](#service-management-commands)
  - [How Backup & Restore Works](#how-backup--restore-works)
- [📂 Repository File Structure](#-repository-file-structure)
- [🔍 Verification & Troubleshooting](#-verification--troubleshooting)
- [📄 License](#-license)

---

# 🎨 Part 1: Theme Setup & Installation

The theme suite provides an Obsidian Monochrome edition of the official Ghost **Alto** theme, featuring an intake `/support/` portal, dynamic `/team/` showcase, and custom transactional email templates.

### Option A: 1-Click Automated Theme Deployer (Recommended)

Run this single command on your Ubuntu server to automatically install the theme, configure custom routing, register published pages in your database, inject the Nginx proxy, and clear Ghost's template cache:

```bash
curl -sSL https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/deploy_theme.sh | sudo bash
```

#### What This Script Does Automatically:
1. **Unpacks Latest Theme**: Downloads and cleanly extracts [`alto-theme-latest.zip`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/alto-theme-latest.zip) into `/var/www/ghost/content/themes/alto/`.
2. **Synchronizes Portal Template**: Installs [`page-support.hbs`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/page-support.hbs) into the theme.
3. **Installs Routing**: Updates [`routes.yaml`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/routes.yaml) in `/var/www/ghost/content/settings/routes.yaml`.
4. **Installs Email Templates & Core Overrides**: Deploys obsidian transactional email templates and the `models/author.js` override (ensuring all team members display on `/team/`).
5. **Configures Database & Pages**: Automatically registers published `/support/` and `/team/` pages in MySQL, sets the pure monochrome accent color, and adds navigation links.
6. **Injects Nginx API Proxy**: Ensures `/api/support/` points to the background daemon.
7. **Clears Template Cache**: Restarts Ghost CMS to immediately apply all changes.

---

### Option B: Manual Theme Setup via Ghost Admin

If you prefer uploading and configuring the theme manually via the Ghost Admin panel:

#### Step 1: Upload the Theme Package
1. Download [`alto-theme-latest.zip`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/alto-theme-latest.zip) from this repository.
2. In Ghost Admin, navigate to **Settings (⚙️) → Design & branding → Change theme → Advanced → Upload theme**.
3. Select `alto-theme-latest.zip`, upload it, and click **Activate**.

#### Step 2: Upload Custom Routes
1. Download [`routes.yaml`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/routes.yaml) from this repository.
2. In Ghost Admin, navigate to **Settings (⚙️) → Labs / Routing → Routes → Upload routes YAML**.
3. Upload `routes.yaml`.

#### Step 3: Create Support & Team Pages
1. Go to **Ghost Admin → Pages → New page**.
2. **Support Portal**:
   - Title: `Support`
   - Page URL / Slug: `support`
   - Under Page Settings (top right gear icon), verify the Template is set to **Support** (`page-support.hbs`).
   - Click **Publish**.
3. **Team Page**:
   - Title: `Our Team`
   - Page URL / Slug: `team`
   - Under Page Settings, verify the Template is set to **Team** (`page-team.hbs`).
   - Click **Publish**.

#### Step 4: Add Navigation Links
1. Go to **Settings (⚙️) → Navigation**.
2. Add Primary Navigation items:
   - `Support` &rarr; `/support/`
   - `Our Team` &rarr; `/team/`
3. Click **Save**.

---

### Theme Features & Support Portal

* **Minimalist Intake Form**: De-cluttered layout with intuitive category selection, priority dropdown (Standard, Urgent, Critical), drag-and-drop file attachments, and optional anonymous submissions.
* **Member Case Tracking**:
  - Logged-in Ghost members automatically see all their submitted cases under the **`[ 📁 My Cases ]`** tab.
  - Case cards display reference codes, submission timestamps, category badges, real-time status badges, and 1-click **Open Case & Live Chat** access.
* **Anonymous Access Keys**: Anonymous reporters receive a unique Case Reference Code and secure 32-character Access Key stored in `localStorage` and trackable via **`[ 🔍 Track by Code ]`**.
* **Two-Way Live Chat**: Integrated correspondence thread allowing reporters and staff to exchange updates and attachments directly within the ticket view.
* **Responsive Dark/Light Mode**: Obsidian styling with fluid transition and persistent theme memory.

---

### 👥 Team Page Customization (`team.json`)

The `/team/` showcase dynamically renders team members configured in `assets/data/team.json`. The [`team-page.js`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/team-page.js) engine parses this array, sorts operatives by priority, and automatically matches authors to their native Ghost profiles.

#### Supported Variables Reference

| Variable | Type | Required | Description | Example |
| :--- | :--- | :---: | :--- | :--- |
| **`order`** | `number` | Recommended | Sort priority. Cards sort ascending (`1` appears first, then `2`, `3`...). | `1` |
| **`name`** | `string` | **Yes** | Display name shown on the card. | `"LordGrim"` |
| **`title`** | `string` | **Yes** | Role or title displayed beneath the name. | `"Lead Investigator"` |
| **`slug`** | `string` | Recommended | Ghost author slug. If it matches a Ghost staff author, it links their posts, author page, and profile photo. | `"admin"` |
| **`alt_slug`** | `string` | Optional | Secondary fallback slug if the author slug differs across installs. | `"xlordgrim"` |
| **`location`** | `string` | Optional | Office, lab, or regional location (rendered with pin icon). | `"Global Operations"` |
| **`bio`** | `string` | Optional | Short description or mission statement. *(Defaults to Ghost author bio if omitted)*. | `"Specializing in OSINT & digital forensics."` |
| **`avatar`** | `string` | Optional | Image URL for profile photo. *(Defaults to Ghost author avatar, or auto-generates monogram initials)*. | `"/assets/images/team/member1.jpg"` |
| **`url`** | `string` | Optional | Custom destination for the **"View Profile"** button. *(Defaults to `/author/<slug>/` if matched)*. | `"/author/admin/"` |

#### Social & Contact Links (Rendered in Card Footer)

| Variable | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| **`telegram`** | `string` (URL) | Telegram profile, channel, or bot link. | `"https://t.me/StopAbuseTeam"` |
| **`twitter`** | `string` (URL) | X / Twitter profile URL. | `"https://x.com/username"` |
| **`github`** | `string` (URL) | GitHub profile URL. | `"https://github.com/username"` |
| **`website`** | `string` (URL) | Personal or organizational website. | `"https://example.org"` |
| **`email`** | `string` | Contact email address. | `"investigations@example.com"` |

#### Complete Example (`team.json`)

```json
[
  {
    "order": 1,
    "slug": "admin",
    "alt_slug": "xlordgrim",
    "name": "LordGrim",
    "title": "Lead Investigator & Developer",
    "location": "Global Operations",
    "bio": "Lead researcher coordinating digital forensics and threat intelligence.",
    "avatar": "",
    "telegram": "https://t.me/StopAbuseTeam",
    "github": "https://github.com/Lordgrim77",
    "website": "https://example.org"
  },
  {
    "order": 2,
    "slug": "analyst-1",
    "name": "Cyber Forensic Analyst",
    "title": "Digital Forensics & Incident Response",
    "location": "Forensics Lab",
    "bio": "Specialized in data carving, network packet analysis, and evidence custody.",
    "telegram": "https://t.me/StopAbuseTeam"
  },
  {
    "order": 3,
    "slug": "intel-lead",
    "name": "OSINT Investigator",
    "title": "Threat Tracking & Analysis",
    "location": "Global Operations",
    "bio": "Open-source intelligence gathering and pattern identification.",
    "telegram": "https://t.me/StopAbuseTeam"
  }
]
```

#### Where to Edit

* **Live Server**: `/var/www/ghost/content/themes/<active-theme>/assets/data/team.json`
* **Repository Source**: [`team.json`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/team.json) and inside [`assets/data/team.json`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/assets/data/team.json)
* **Inline Fallback**: Inside [`page-team.hbs`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/page-team.hbs#L361-L389) `<script id="gm-team-default-data" type="application/json">`

---

# 🤖 Part 2: Bot Setup & Installation

The bot acts as a publication manager for administrators and runs a lightweight REST API daemon (`support_hub.py`) on port 8080 to power the support portal.

### Prerequisites (Telegram Bot & User ID)

Before installing, obtain your Telegram credentials:

1. **Bot Token**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, choose a display name and username.
   - Copy the HTTP API token (e.g. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567`).

2. **Your Telegram User ID**:
   - Message [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot) on Telegram.
   - Send `/start` and copy your numeric User ID (e.g. `123456789`).

---

### Option A: 1-Click Interactive Automated Installer (Recommended)

Run this command on your Ubuntu server:

```bash
curl -sSL https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/install.sh -o /tmp/install.sh && sudo bash /tmp/install.sh
```

#### What the Installer Configures:
1. **System Dependencies**: Installs `python3`, `python3-pip`, `python3-venv`, `default-mysql-client`, `unzip`, `curl`, and `git`.
2. **Interactive Prompts**: Asks for your Ghost directory, Telegram Bot Token, and Telegram Admin User ID.
3. **Application Directory**: Deploys the code into `/opt/ghost-telegram-bot` with an isolated Python virtual environment.
4. **Systemd Service**: Configures, enables, and starts `ghost-telegram-bot.service` with automatic restart on boot.
5. **Nginx Reverse Proxy**: Automatically injects the `/api/support/` proxy rule into your Nginx virtual host and reloads Nginx.

---

### Option B: 1-Click Quick Support Hub & Bot Updater

If you already have the bot installed or need to update the support backend, sync templates, and verify connections, run:

```bash
curl -sSL https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/setup_support.sh | sudo bash
```

This script:
- Fetches the latest [`bot.py`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/bot.py), [`support_hub.py`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/support_hub.py), and [`page-support.hbs`](file:///C:/Users/LordgrimxDJay/.gemini/antigravity/scratch/Ghost-Restore/page-support.hbs).
- Distributes `page-support.hbs` across all installed Ghost themes.
- Verifies Python virtualenv dependencies.
- Restarts the background service and Nginx.
- Performs a connection self-test on port 8080 and `/api/support/`.

---

### Option C: Manual Bot Installation

If you prefer to configure the service manually:

```bash
# 1. Clone the repository into /opt/ghost-telegram-bot
sudo git clone https://github.com/Lordgrim77/Ghost-Restore-.git /opt/ghost-telegram-bot
cd /opt/ghost-telegram-bot

# 2. Create Python virtual environment and install packages
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt

# 3. Create .env configuration
sudo cp .env.example .env
sudo nano .env

# 4. Create systemd service
sudo bash -c 'cat <<EOF > /etc/systemd/system/ghost-telegram-bot.service
[Unit]
Description=Ghost Backup & Support Hub Daemon
After=network.target mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ghost-telegram-bot
EnvironmentFile=/opt/ghost-telegram-bot/.env
ExecStart=/opt/ghost-telegram-bot/venv/bin/python3 /opt/ghost-telegram-bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF'

# 5. Start and enable service
sudo systemctl daemon-reload
sudo systemctl enable ghost-telegram-bot.service
sudo systemctl start ghost-telegram-bot.service
```

---

### Configuration Reference (`.env`)

Configuration resides in `/opt/ghost-telegram-bot/.env` (or your chosen working directory):

```ini
# Telegram Bot HTTP API token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567

# Authorized Telegram user IDs permitted to run commands (comma-separated)
ALLOWED_USER_IDS=123456789,987654321

# Telegram chat or user ID where new support intake notifications are dispatched
ADMIN_CHAT_ID=123456789

# Absolute path to your Ghost publication directory
GHOST_DIR=/var/www/ghost

# Destination path where backup zip files are saved
BACKUPS_DIR=/var/www/ghost/backups

# Local support hub REST API listener configuration
SUPPORT_HOST=127.0.0.1
SUPPORT_PORT=8080
```

After modifying `.env`, restart the daemon:
```bash
sudo systemctl restart ghost-telegram-bot
```

---

### Nginx Reverse Proxy Configuration

The Support Portal submits tickets and fetches correspondence via `/api/support/`. Add this block inside your Ghost server configuration in `/etc/nginx/sites-available/` (before the main `location /` block):

```nginx
# Ghost Support Portal & Telegram Bot API Proxy
location /api/support/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 50M;
}
```

Then test and reload Nginx:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

### Service Management Commands

| Task | Command |
| :--- | :--- |
| **Check Bot & Support Hub Status** | `sudo systemctl status ghost-telegram-bot` |
| **View Live Real-Time Logs** | `sudo journalctl -u ghost-telegram-bot -f` |
| **Restart Bot & Daemon** | `sudo systemctl restart ghost-telegram-bot` |
| **Stop Bot & Daemon** | `sudo systemctl stop ghost-telegram-bot` |
| **Start Bot & Daemon** | `sudo systemctl start ghost-telegram-bot` |
| **Complete Uninstallation** | `sudo bash /opt/ghost-telegram-bot/uninstall.sh` |

---

### How Backup & Restore Works

#### Interactive Telegram Bot Dashboard:
```
+-------------------------------------------------------------+
| 👻 Ghost Publication Manager                                |
|                                                             |
| 🌐 Status: 🟢 Online                                        |
| 🔗 URL: https://yourdomain.com                              |
| 📁 Ghost Directory: /var/www/ghost                          |
| 💾 Total Backups: 4                                         |
+-------------------------------------------------------------+
|   [ 📦 Create Backup ]     |    [ ♻️ Restore Backup ]      |
+-------------------------------------------------------------+
|   [ 🐙 GitHub Sync ]       |    [ 📊 Ghost Status ]        |
+-------------------------------------------------------------+
|   [ 🛡️ Support Cases ]     |    [ 📑 List Backups ]        |
+-------------------------------------------------------------+
|   [ 🔄 Restart Ghost ]     |    [ ℹ️ Help & Info ]         |
+-------------------------------------------------------------+
```

#### Snapshot Creation (`[ 📦 Create Backup ]`):
1. Detects MySQL or SQLite connection credentials from `config.production.json`.
2. Generates a database dump using `mysqldump --single-transaction --routines`.
3. Compresses custom themes (`/content/themes/*`), uploads (`/content/images/*`), support records (`/support_vault/`), and settings (`/content/settings/*`).
4. Generates a POSIX-compliant `.zip` archive inside `backups/`.
5. Backups under 48 MB are sent directly to your Telegram chat for offline storage.

#### Snapshot Restoration (`[ ♻️ Restore Backup ]` or Uploading `.zip`):
1. Stops Ghost cleanly via Ghost CLI under the non-root owner (`ghost` or `ubuntu`).
2. Extracts the archive, converting any Windows backslash (`\`) archive paths into POSIX format.
3. Overlays themes and images while strictly preserving core symlinks (`casper`, `source`).
4. Restores the MySQL database using `SET FOREIGN_KEY_CHECKS=0`.
5. Corrects directory permissions (`chmod 775` on folders, `chmod 664` on files, `chown -R ghost:ghost`).
6. Starts Ghost and performs a health check.

#### 🐙 Private GitHub Backup & Restore (Unzipped Content Archive):
Sync your publication to a private GitHub repository in an **unzipped, clean layout** that resembles a natural static archive to avoid unwanted attention and Git size issues:
- **`posts/<slug>.json` & `pages/<slug>.json`**: Individual human-readable JSON files with post title, slug, HTML, Lexical/Mobiledoc, custom excerpt, tags, authors, and status.
- **`images/`**: Full unzipped directory of uploaded media images preserving year/month folder structure.
- **`database/ghost_database.sql`**: Full MySQL/SQLite dump for loss-free relational restoration.
- **`settings/routes.yaml` & `themes/`**: Custom routes and active custom themes.
- **🔒 Strict Privacy Guarantee**: Confidential support vault and evidence records are strictly excluded (`support_vault/` and `evidence/` are never committed).
- **1-Click Restore**: Pulls the latest commit from your private GitHub repo, imports the database, restores images and themes, secures Linux permissions, and restarts Ghost.

##### GitHub Bot Commands:
- `/github_setup <repo_url> <token> [branch]` *(alias `/gh_setup`)*: Validates connection and writes credentials to `.env` (automatically deletes message for security).
- `/github_backup` *(alias `/gh_backup`)*: Exports and pushes unzipped publication content to GitHub.
- `/github_restore` *(alias `/gh_restore`)*: 1-Click restore of publication from your private GitHub repository.
- `/github_status` *(alias `/gh_status`)*: Displays repository configuration, branch, and latest synced commit.

#### Real-Time Support Triage:
When a visitor or member submits a report on `/support/`, the bot:
1. Scrubs `APP1` EXIF, GPS, and metadata chunks from uploaded images in pure Python.
2. Generates SHA-256 evidentiary hashes.
3. Dispatches an interactive alert card to the administrator Telegram chat (`ADMIN_CHAT_ID`).
4. Offers inline buttons:
   - `[ 🔍 In Review ]`: Moves case into active investigation.
   - `[ ✅ Mark Closed ]`: Resolves the case.
   - `[ 💬 Reply to Reporter ]`: Sends a direct response appearing in the reporter's live web ticket chat.
   - `[ 📥 Evidence ]`: Streams attached evidence files directly into Telegram.

---

# 📂 Repository File Structure

```
Ghost-Restore/
├── alto-theme-latest.zip     # Ready-to-upload Alto theme zip package
├── email-templates.zip       # Redesigned obsidian email templates package
├── page-support.hbs          # Clean support intake & member case tracking portal
├── page-team.hbs             # Team showcase page template
├── routes.yaml               # Routing configuration for /support/ and /team/
├── team.json                 # Team members data configuration
├── team-page.js              # Client-side dynamic team card rendering engine
│
├── deploy_theme.sh           # 1-Click theme & support portal deployer script
├── install.sh                # 1-Click interactive bot installer
├── setup_support.sh          # 1-Click support hub connector & updater
├── fix_bot.sh                # 1-Click diagnostic and auto-repair utility
├── uninstall.sh              # Clean removal script
│
├── bot.py                    # Telegram bot event handler & triage bridge
├── ghost_manager.py          # Backup/restore snapshot engine & permission fixer
├── support_hub.py            # Async REST API server (port 8080) & SQLite vault
├── package_all.py            # Build script for packaging Alto theme and templates
│
├── .env.example              # Example environment configuration template
├── requirements.txt          # Python dependencies (python-telegram-bot, requests)
└── README.md                 # Complete documentation and setup guide
```

---

# 🔍 Verification & Troubleshooting

### 1. Checking the Local Support Daemon
Test whether the Python backend is listening locally on port 8080:
```bash
curl -I http://127.0.0.1:8080/health
```
*Expected response*: `HTTP/1.0 200 OK` with JSON `{"status": "ok", "service": "support-hub"}`.

### 2. Checking the Nginx Reverse Proxy
Verify that your Nginx reverse proxy correctly forwards requests:
```bash
curl -I https://yourdomain.com/api/support/health
```
*Expected response*: `HTTP/2 200` or `HTTP/1.1 200 OK`.

### 3. Clearing Ghost Template Cache
If edits to `page-support.hbs` or `page-team.hbs` do not immediately reflect on the live website, restart Ghost to reload in-memory Handlebars templates:
```bash
sudo systemctl restart ghost_*.service 2>/dev/null || sudo systemctl restart ghost.service 2>/dev/null
```
Or as the `ghost` user:
```bash
su - ghost -c "cd /var/www/ghost && ghost restart"
```

---

# 📄 License

This project is licensed under the [MIT License](LICENSE).
