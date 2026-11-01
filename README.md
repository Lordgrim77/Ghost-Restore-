# 👻 Ghost Backup & Restore Telegram Bot

[![Ubuntu Support](https://img.shields.io/badge/Ubuntu-20.04%20%7C%2022.04%20%7C%2024.04-orange?logo=ubuntu)](https://ubuntu.com)
[![Ghost CMS](https://img.shields.io/badge/Ghost%20CMS-5.x-blue?logo=ghost)](https://ghost.org)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An interactive Telegram Bot for **1-Click Full Backup & Restore** of any Ghost CMS publication on Ubuntu Linux. Manage your publication directly from your smartphone or desktop via intuitive inline buttons!

---

## ⚡ Quick 1-Click Install (Ubuntu)

Run this single command on your Ubuntu server as `root` (or with `sudo`):

```bash
curl -sSL https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/install.sh | sudo bash
```

The installer will:
1. Automatically install system packages (`python3`, `python3-venv`, `default-mysql-client`, `unzip`).
2. Prompt for your Telegram Bot Token and Telegram User ID.
3. Build an isolated Python virtual environment in `/opt/ghost-telegram-bot`.
4. Configure, enable, and start the `ghost-telegram-bot.service` systemd background service.

---

## 🌟 Key Features

* **📱 Interactive Inline Buttons**: No confusing syntax or memorized CLI flags. Control backups and restores with clean buttons.
* **📦 Complete 1:1 Publication Snapshots**:
  * **Database**: Automatic `mysqldump` for MySQL 8 installations or direct `.db` copy for SQLite.
  * **Themes**: Archives active custom themes (e.g. Alto, Liebling) while safely preserving core symlinks (`casper`, `source`).
  * **Media & Images**: Full backup of `/content/images` and content routes.
  * **Settings**: Preserves `config.production.json` and theme customization settings.
* **📤 Drag-and-Drop Restore**:
  * Send/upload any `.zip` backup directly into your Telegram chat.
  * The bot verifies the archive and displays a **`[ ✅ Yes, Restore This Backup ]`** prompt.
* **📥 Direct Telegram Downloads**:
  * Backups under 48 MB are automatically uploaded directly to your Telegram chat for instant offline archival.
* **🛡️ Hardened & Cross-Platform Safe**:
  * **Path Normalization**: Corrects Windows backslash (`\`) archive paths so archives extracted on Linux never corrupt into flat filenames.
  * **Ghost CLI Non-Root Execution**: Runs Ghost commands under the appropriate user (`ghost` or `ubuntu`), bypassing the `"You can't run commands as the 'root' user"` blocker.
  * **Symlink Protection**: Never overwrites core theme symlinks with non-directories.
  * **Dual Engine Sync**: Restores MySQL databases cleanly with `FOREIGN_KEY_CHECKS=0` and can even translate SQLite records into MySQL tables.
* **🔒 User ID Whitelist**:
  * Restricts bot access strictly to authorized Telegram user IDs.

---

## 📸 Telegram Bot Interface

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
|   [ 📊 Ghost Status ]      |    [ 📑 List Backups ]        |
+-------------------------------------------------------------+
|   [ 🔄 Restart Ghost ]     |    [ ℹ️ Help & Info ]         |
+-------------------------------------------------------------+
```

---

## 📋 Prerequisites & Preparation

Before running the installer, get two things from Telegram:

1. **Bot Token**:
   * Open Telegram and search for [@BotFather](https://t.me/BotFather).
   * Send `/newbot`, choose a name and username (e.g. `MyGhostBackupBot`).
   * Copy the HTTP API token provided.

2. **Your Telegram User ID**:
   * Search for [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot).
   * Send `/start` and copy your numeric User ID (e.g. `123456789`).

---

## 🛠️ Manual Installation (Alternative)

If you prefer to clone and install manually:

```bash
# 1. Clone repository
git clone https://github.com/Lordgrim77/Ghost-Restore-.git /opt/ghost-telegram-bot
cd /opt/ghost-telegram-bot

# 2. Run installer
sudo bash install.sh
```

---

## ⚙️ Configuration & Environment (`.env`)

Configuration resides in `/opt/ghost-telegram-bot/.env`:

```ini
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567

# Authorized Telegram user IDs (comma-separated)
ALLOWED_USER_IDS=123456789,987654321

# Ghost installation path
GHOST_DIR=/var/www/ghost

# Backup destination path
BACKUPS_DIR=/var/www/ghost/backups
```

After modifying `.env`, restart the service:
```bash
sudo systemctl restart ghost-telegram-bot
```

---

## 🔧 Service Management

| Task | Command |
| :--- | :--- |
| **Check Bot Status** | `sudo systemctl status ghost-telegram-bot` |
| **View Live Logs** | `sudo journalctl -u ghost-telegram-bot -f` |
| **Restart Bot** | `sudo systemctl restart ghost-telegram-bot` |
| **Stop Bot** | `sudo systemctl stop ghost-telegram-bot` |
| **Start Bot** | `sudo systemctl start ghost-telegram-bot` |
| **Uninstall** | `sudo bash /opt/ghost-telegram-bot/uninstall.sh` |

---

## 💡 How Backup & Restore Works Under the Hood

### When You Tap `[ 📦 Create Backup ]`
1. Inspects `/var/www/ghost/config.production.json` to detect database credentials and active theme.
2. Dumps MySQL database using `mysqldump --single-transaction --routines` into `content/data/mysql_database.sql` (or copies `.db` if SQLite).
3. Archives custom themes (`/content/themes/*`), media (`/content/images/*`), and routing configs (`/content/settings/*`).
4. Compresses all assets into a POSIX-compliant `.zip` archive inside `/var/www/ghost/backups/`.
5. Sends the `.zip` archive into Telegram chat if $\le 48$ MB.

### When You Tap `[ ♻️ Restore Backup ]` or Upload a `.zip`
1. Gracefully stops Ghost (`ghost stop` run as non-root user).
2. Extracts the archive, converting any Windows backslashes (`\`) into POSIX slashes (`/`).
3. Safely overlays themes without overwriting core Casper/Source symlinks.
4. Restores images and settings.
5. Imports MySQL dump using `SET FOREIGN_KEY_CHECKS=0` (or restores SQLite file).
6. Fixes directory permissions (`chmod 775` on folders, `chmod 664` on files, `chown -R ghost:ghost`).
7. Starts Ghost (`ghost start`) and confirms health check.

---

## 🗑️ Uninstallation

To remove the bot and systemd service completely:

```bash
sudo bash /opt/ghost-telegram-bot/uninstall.sh
```

*(Your backups in `/var/www/ghost/backups` are safely kept intact).*

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
