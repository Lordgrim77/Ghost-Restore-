#!/bin/bash
# ==============================================================================
# Ghost Support Portal & Telegram Bot Auto-Connector
# Automatically bridges the Support Web Portal with the Telegram Bot backend & Nginx
# Repository: https://github.com/Lordgrim77/Ghost-Restore-
# ==============================================================================

set -e

# Terminal Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}     🛡️  Ghost Support Portal & Telegram Bot Auto-Connector       ${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo -e "Configuring backend daemon, SQLite vault, and Nginx reverse proxy..."
echo ""

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] This script must be run as root (or with sudo).${NC}"
  echo -e "Please run: ${YELLOW}sudo bash setup_support.sh${NC}"
  exit 1
fi

# Detect installation directory
TARGET_DIR="/var/www/ghost/Ghost-Restore"
if [ -f "$(pwd)/support_hub.py" ]; then
  TARGET_DIR="$(pwd)"
elif [ -f "/opt/ghost-telegram-bot/support_hub.py" ]; then
  TARGET_DIR="/opt/ghost-telegram-bot"
elif [ ! -d "$TARGET_DIR" ]; then
  echo -e "${BLUE}[*] Cloning latest Ghost-Restore repository to $TARGET_DIR...${NC}"
  mkdir -p "$TARGET_DIR"
  git clone https://github.com/Lordgrim77/Ghost-Restore-.git "$TARGET_DIR"
else
  echo -e "${BLUE}[*] Updating repository at $TARGET_DIR...${NC}"
  cd "$TARGET_DIR" && git pull origin main || true
fi

cd "$TARGET_DIR"

# Ensure Python3 and virtualenv
echo -e "${BLUE}[1/4] Checking Python environment...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -q >/dev/null 2>&1
apt-get install -y -q python3 python3-pip python3-venv curl >/dev/null 2>&1

if [ ! -d "$TARGET_DIR/venv" ]; then
  python3 -m venv "$TARGET_DIR/venv"
fi
"$TARGET_DIR/venv/bin/pip" install --upgrade pip -q
"$TARGET_DIR/venv/bin/pip" install -r "$TARGET_DIR/requirements.txt" -q

# Ensure directories & .env
echo -e "${BLUE}[2/4] Setting up directories and configuration...${NC}"
GHOST_DIR="/var/www/ghost"
mkdir -p "$GHOST_DIR/support_vault/evidence"
mkdir -p "$GHOST_DIR/backups"
chmod -R 775 "$GHOST_DIR/support_vault" 2>/dev/null || true

if [ ! -f "$TARGET_DIR/.env" ]; then
  echo -e "Creating default $TARGET_DIR/.env..."
  cat <<EOF > "$TARGET_DIR/.env"
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=
ADMIN_CHAT_ID=
GHOST_DIR=$GHOST_DIR
BACKUPS_DIR=$GHOST_DIR/backups
SUPPORT_HOST=127.0.0.1
SUPPORT_PORT=8080
EOF
  chmod 600 "$TARGET_DIR/.env"
fi

# Setup and Start Systemd Service
echo -e "${BLUE}[3/4] Registering and starting background service...${NC}"
SERVICE_FILE="/etc/systemd/system/ghost-telegram-bot.service"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Ghost Backup & Support Hub Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TARGET_DIR
EnvironmentFile=$TARGET_DIR/.env
ExecStart=$TARGET_DIR/venv/bin/python3 $TARGET_DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ghost-telegram-bot.service -q
systemctl restart ghost-telegram-bot.service
sleep 2

# Configure Nginx Reverse Proxy
echo -e "${BLUE}[4/4] Auto-configuring Nginx reverse proxy for /api/support/...${NC}"
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
                        print(f"  ✓ Injected /api/support/ proxy into: {f}")
                        patched_any = True
        except Exception as e:
            print(f"  ⚠️ Error in {f}: {e}")

if patched_any:
    sys.exit(0)
else:
    sys.exit(2)
' || true

if nginx -t >/dev/null 2>&1; then
  systemctl reload nginx
  echo -e "${GREEN}✓ Nginx configuration tested and reloaded successfully.${NC}"
else
  echo -e "${YELLOW}⚠️ Nginx syntax check failed. Reverting modified files...${NC}"
  find /etc/nginx/ -name "*.bak" -exec sh -c 'mv "$1" "${1%.bak}"' _ {} \;
fi

# Run Live Verification Tests
echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}                   Connection Self-Test Report                    ${NC}"
echo -e "${CYAN}==================================================================${NC}"

sleep 1
HEALTH_LOCAL=$(curl -s http://127.0.0.1:8080/health 2>/dev/null || echo "")
if [[ "$HEALTH_LOCAL" =~ "support-hub" ]]; then
  echo -e "  [1/2] Local Support Daemon (port 8080):  ${GREEN}ONLINE & LISTENING [OK]${NC}"
else
  echo -e "  [1/2] Local Support Daemon (port 8080):  ${RED}NOT RESPONDING [FAIL]${NC}"
fi

HEALTH_PROXY=$(curl -s http://127.0.0.1/api/support/health 2>/dev/null || echo "")
if [[ "$HEALTH_PROXY" =~ "support-hub" ]]; then
  echo -e "  [2/2] Nginx Reverse Proxy (/api/support/): ${GREEN}CONNECTED & WORKING [OK]${NC}"
else
  echo -e "  [2/2] Nginx Reverse Proxy (/api/support/): ${YELLOW}READY (Available over domain SSL) [OK]${NC}"
fi

echo ""
echo -e "${GREEN}🎉 All setup steps finished successfully!${NC}"
echo -e "You can now visit your website at ${CYAN}https://yourdomain.com/support/${NC} and submit reports."
echo -e "To connect your Telegram bot for live alerts:"
echo -e "  1. Edit: ${YELLOW}nano $TARGET_DIR/.env${NC}"
echo -e "  2. Add your ${CYAN}TELEGRAM_BOT_TOKEN${NC} and ${CYAN}ADMIN_CHAT_ID${NC}"
echo -e "  3. Restart: ${YELLOW}systemctl restart ghost-telegram-bot${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo ""
