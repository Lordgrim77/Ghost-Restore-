#!/bin/bash
# ==============================================================================
# Ghost Telegram Bot - 1-Click Interactive Installer for Ubuntu Linux
# Repository: https://github.com/Lordgrim77/Ghost-Restore-
# ==============================================================================

set -e

# Terminal Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/ghost-telegram-bot"
REPO_URL="https://github.com/Lordgrim77/Ghost-Restore-.git"

echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}        👻 Ghost Backup & Restore Telegram Bot Installer          ${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo -e "This script configures and deploys the Ghost Telegram Bot as an"
echo -e "automated background systemd service."
echo ""

# 1. Root Check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] This installer must be run as root (or with sudo).${NC}"
  echo -e "Please re-run with: ${YELLOW}sudo bash install.sh${NC}"
  exit 1
fi

# Helper functions for reading from /dev/tty safely (works both in script and curl | bash)
read_tty() {
  local prompt="$1"
  local var_name="$2"
  local default_val="$3"
  local val=""

  if [ -c /dev/tty ]; then
    read -r -p "$prompt" val < /dev/tty
  else
    read -r -p "$prompt" val
  fi

  if [ -z "$val" ]; then
    val="$default_val"
  fi
  eval "$var_name=\"$val\""
}

# 2. Check & Install System Dependencies
echo -e "${BLUE}[1/5] Updating packages and installing dependencies...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-pip python3-venv default-mysql-client unzip curl git
echo -e "${GREEN}✓ System dependencies ready.${NC}"

# 3. Prompt Configuration
echo ""
echo -e "${BLUE}[2/5] Configuring Telegram Bot Settings...${NC}"

# Ghost Directory
DEFAULT_GHOST_DIR="/var/www/ghost"
read_tty "Enter Ghost installation directory [$DEFAULT_GHOST_DIR]: " GHOST_DIR "$DEFAULT_GHOST_DIR"

if [ ! -f "$GHOST_DIR/config.production.json" ] && [ ! -f "$GHOST_DIR/config.development.json" ]; then
  echo -e "${YELLOW}[WARNING] No config.production.json found in $GHOST_DIR.${NC}"
  read_tty "Continue anyway? (y/N): " CONFIRM_GHOST "N"
  if [[ ! "$CONFIRM_GHOST" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Installation cancelled.${NC}"
    exit 1
  fi
fi

# Telegram Bot Token
while [ -z "$BOT_TOKEN" ]; do
  echo ""
  echo -e "Get your Bot Token from ${CYAN}@BotFather${NC} on Telegram (/newbot)."
  read_tty "Enter your Telegram Bot Token: " BOT_TOKEN ""
  BOT_TOKEN=$(echo "$BOT_TOKEN" | xargs)
  if [ -z "$BOT_TOKEN" ]; then
    echo -e "${RED}Bot token cannot be empty!${NC}"
  fi
done

# Telegram Admin User ID
while [ -z "$ADMIN_ID" ]; do
  echo ""
  echo -e "Find your Telegram User ID using ${CYAN}@userinfobot${NC} on Telegram."
  read_tty "Enter your Telegram User ID (e.g. 123456789): " ADMIN_ID ""
  ADMIN_ID=$(echo "$ADMIN_ID" | xargs)
  if [ -z "$ADMIN_ID" ]; then
    echo -e "${RED}User ID cannot be empty!${NC}"
  fi
done

# 4. Setup Bot Files & Python Environment
echo ""
echo -e "${BLUE}[3/5] Setting up application files in $INSTALL_DIR...${NC}"

# Determine directory where script is executing
SCRIPT_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

mkdir -p "$INSTALL_DIR"
if [ -f "$SCRIPT_SOURCE_DIR/bot.py" ] && [ -f "$SCRIPT_SOURCE_DIR/ghost_manager.py" ] && [ "$SCRIPT_SOURCE_DIR" != "$INSTALL_DIR" ]; then
  echo -e "Copying files from $SCRIPT_SOURCE_DIR to $INSTALL_DIR..."
  cp -rf "$SCRIPT_SOURCE_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
elif [ ! -f "$INSTALL_DIR/bot.py" ]; then
  echo -e "Downloading latest release from $REPO_URL..."
  if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR" && git pull -q
  else
    rm -rf "$INSTALL_DIR"/*
    git clone -q "$REPO_URL" "$INSTALL_DIR"
  fi
fi

# Ensure backups and support vault directories exist
mkdir -p "$GHOST_DIR/backups"
mkdir -p "$GHOST_DIR/support_vault/evidence"
chmod -R 775 "$GHOST_DIR/support_vault" 2>/dev/null || true

# Write .env file
echo -e "Writing configuration to $INSTALL_DIR/.env..."
cat <<EOF > "$INSTALL_DIR/.env"
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
ALLOWED_USER_IDS=$ADMIN_ID
ADMIN_CHAT_ID=$ADMIN_ID
GHOST_DIR=$GHOST_DIR
BACKUPS_DIR=$GHOST_DIR/backups
SUPPORT_HOST=127.0.0.1
SUPPORT_PORT=8080
EOF
chmod 600 "$INSTALL_DIR/.env"

# Create Python Virtual Environment
echo ""
echo -e "${BLUE}[4/5] Building Python virtual environment & installing packages...${NC}"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
echo -e "${GREEN}✓ Python dependencies installed.${NC}"

# 5. Create & Enable Systemd Service
echo ""
echo -e "${BLUE}[5/5] Creating systemd service ghost-telegram-bot...${NC}"

SERVICE_FILE="/etc/systemd/system/ghost-telegram-bot.service"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Ghost Backup & Restore Telegram Bot
After=network.target mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ghost-telegram-bot.service -q
systemctl restart ghost-telegram-bot.service

sleep 2

# Check status
if systemctl is-active --quiet ghost-telegram-bot.service; then
  echo ""
  echo -e "${GREEN}==================================================================${NC}"
  echo -e "${GREEN}    🎉 Ghost Telegram Bot Installed & Running Successfully!       ${NC}"
  echo -e "${GREEN}==================================================================${NC}"
  echo -e "Your bot is now live and waiting for commands on Telegram!"
  echo ""
  echo -e "👉 Open Telegram, open your bot, and send: ${CYAN}/start${NC}"
  echo ""
  echo -e "Useful Commands:"
  echo -e "  • Check service status: ${YELLOW}systemctl status ghost-telegram-bot${NC}"
  echo -e "  • View live logs:      ${YELLOW}journalctl -u ghost-telegram-bot -f${NC}"
  echo -e "  • Restart bot:         ${YELLOW}systemctl restart ghost-telegram-bot${NC}"
  echo -e "  • Uninstall bot:       ${YELLOW}bash $INSTALL_DIR/uninstall.sh${NC}"
  echo -e "${GREEN}==================================================================${NC}"
else
  echo -e "${RED}[ERROR] Service failed to start. Checking recent logs:${NC}"
  journalctl -u ghost-telegram-bot -n 25 --no-pager
  exit 1
fi
