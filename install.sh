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
EnvironmentFile=-$INSTALL_DIR/.env
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

# 6. Auto-configure Nginx reverse proxy for Support Portal
echo ""
echo -e "${BLUE}[6/6] Auto-configuring Nginx reverse proxy for Support Portal...${NC}"

NGINX_STATUS=0
python3 -c '
import sys, re, os, glob

conf_dirs = ["/etc/nginx/sites-enabled", "/etc/nginx/sites-available", "/etc/nginx/conf.d"]
proxy_block = """    # Ghost Support Portal & Telegram Bot API Proxy
    location /api/support/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50M;
    }

"""

seen_files = set()
patched_any = False

for cdir in conf_dirs:
    if not os.path.isdir(cdir):
        continue
    for f in sorted(glob.glob(os.path.join(cdir, "*"))):
        real_f = os.path.realpath(f)
        if not os.path.isfile(real_f) or real_f.endswith(".bak") or real_f in seen_files:
            continue
        seen_files.add(real_f)
        try:
            with open(real_f, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
            if "2368" in content:
                if "location /api/support/" in content:
                    print(f"  ℹ️  Support proxy already configured in: {f}")
                    patched_any = True
                else:
                    parts = re.split(r"(\s+location\s+/\s*\{)", content)
                    if len(parts) > 1:
                        with open(real_f + ".bak", "w", encoding="utf-8") as bkp:
                            bkp.write(content)
                        new_parts = []
                        for p in parts:
                            if re.match(r"^\s+location\s+/\s*\{", p):
                                new_parts.append("\n" + proxy_block + p)
                            else:
                                new_parts.append(p)
                        with open(real_f, "w", encoding="utf-8") as fp:
                            fp.write("".join(new_parts))
                        print(f"  ✓ Successfully injected Support proxy into: {f}")
                        patched_any = True
        except Exception as e:
            print(f"  ⚠️ Error inspecting {f}: {e}")

if patched_any:
    sys.exit(0)
else:
    sys.exit(2)
' || NGINX_STATUS=$?

if [ "$NGINX_STATUS" -eq 0 ]; then
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx
    echo -e "${GREEN}✓ Nginx configuration verified and reloaded.${NC}"
  else
    echo -e "${YELLOW}⚠️ Nginx syntax check failed. Reverting modified files...${NC}"
    find /etc/nginx/ -name "*.bak" -exec sh -c 'mv "$1" "${1%.bak}"' _ {} \;
  fi
fi

# Self-test endpoints
echo ""
echo -e "${BLUE}Running live connection tests...${NC}"
sleep 1
HEALTH_LOCAL=$(curl -s http://127.0.0.1:8080/health 2>/dev/null || echo "")
if [[ "$HEALTH_LOCAL" =~ "support-hub" ]]; then
  echo -e "${GREEN}✓ Bot API Daemon: ONLINE & LISTENING on 127.0.0.1:8080${NC}"
else
  echo -e "${RED}✗ Bot API Daemon: NOT RESPONDING on port 8080${NC}"
fi

HEALTH_PROXY=$(curl -s http://127.0.0.1/api/support/health 2>/dev/null || echo "")
if [[ "$HEALTH_PROXY" =~ "support-hub" ]]; then
  echo -e "${GREEN}✓ Nginx Proxy: VERIFIED (/api/support/ -> 8080)${NC}"
else
  echo -e "${YELLOW}ℹ️  Nginx proxy on 127.0.0.1: (Will connect through domain SSL)${NC}"
fi

# Check status
if systemctl is-active --quiet ghost-telegram-bot.service; then
  echo ""
  echo -e "${GREEN}==================================================================${NC}"
  echo -e "${GREEN}    🎉 Ghost Telegram Bot Installed & Running Successfully!       ${NC}"
  echo -e "${GREEN}==================================================================${NC}"
  echo -e "Your bot and support portal API are now live and connected!"
  echo ""
  echo -e "👉 Open Telegram, open your bot, and send: ${CYAN}/start${NC}"
  echo -e "👉 Visit your support portal: ${CYAN}https://yourdomain.com/support/${NC}"
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
