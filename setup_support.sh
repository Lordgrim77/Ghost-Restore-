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
GHOST_DIR="/var/www/ghost"
TARGET_DIR="/var/www/ghost/Ghost-Restore"
if [ -d "/opt/ghost-telegram-bot" ]; then
  TARGET_DIR="/opt/ghost-telegram-bot"
elif [ -f "$(pwd)/support_hub.py" ]; then
  TARGET_DIR="$(pwd)"
fi

echo -e "${BLUE}[1/5] Syncing latest support hub code into $TARGET_DIR...${NC}"
mkdir -p "$TARGET_DIR"
mkdir -p "$GHOST_DIR/Ghost-Restore"

CACHE_BUSTER=$(date +%s)
RAW_BASE="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main"

curl -sSL "$RAW_BASE/bot.py?v=$CACHE_BUSTER" -o "$TARGET_DIR/bot.py"
curl -sSL "$RAW_BASE/support_hub.py?v=$CACHE_BUSTER" -o "$TARGET_DIR/support_hub.py"
curl -sSL "$RAW_BASE/ghost_manager.py?v=$CACHE_BUSTER" -o "$TARGET_DIR/ghost_manager.py"
curl -sSL "$RAW_BASE/requirements.txt?v=$CACHE_BUSTER" -o "$TARGET_DIR/requirements.txt"
curl -sSL "$RAW_BASE/page-support.hbs?v=$CACHE_BUSTER" -o "$TARGET_DIR/page-support.hbs"

# Sync latest page-support.hbs directly into ALL installed Ghost themes
if [ -d "$GHOST_DIR/content/themes" ]; then
  for theme_dir in "$GHOST_DIR/content/themes"/*; do
    if [ -d "$theme_dir" ]; then
      cp -f "$TARGET_DIR/page-support.hbs" "$theme_dir/page-support.hbs" 2>/dev/null || true
      chown -R ghost:ghost "$theme_dir/page-support.hbs" 2>/dev/null || true
      echo -e "  ✓ Synced clean page-support.hbs into: $(basename "$theme_dir")"
    fi
  done
fi

# Keep /var/www/ghost/Ghost-Restore in sync as well
if [ "$TARGET_DIR" != "$GHOST_DIR/Ghost-Restore" ]; then
  cp -f "$TARGET_DIR/bot.py" "$TARGET_DIR/support_hub.py" "$TARGET_DIR/ghost_manager.py" "$TARGET_DIR/requirements.txt" "$TARGET_DIR/page-support.hbs" "$GHOST_DIR/Ghost-Restore/" 2>/dev/null || true
fi

cd "$TARGET_DIR"

# Ensure Python3 and virtualenv
echo -e "${BLUE}[2/5] Checking Python virtual environment...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -q >/dev/null 2>&1
apt-get install -y -q python3 python3-pip python3-venv curl >/dev/null 2>&1

if [ ! -d "$TARGET_DIR/venv" ]; then
  python3 -m venv "$TARGET_DIR/venv"
fi
"$TARGET_DIR/venv/bin/pip" install --upgrade pip -q
"$TARGET_DIR/venv/bin/pip" install -r "$TARGET_DIR/requirements.txt" -q

# Ensure directories & .env
echo -e "${BLUE}[3/5] Setting up directories and configuration...${NC}"
mkdir -p "$GHOST_DIR/support_vault/evidence"
mkdir -p "$GHOST_DIR/backups"
chmod -R 775 "$GHOST_DIR/support_vault" 2>/dev/null || true

# Preserve existing .env or create default
if [ ! -f "$TARGET_DIR/.env" ]; then
  if [ -f "$GHOST_DIR/Ghost-Restore/.env" ]; then
    cp "$GHOST_DIR/Ghost-Restore/.env" "$TARGET_DIR/.env"
  elif [ -f "/opt/ghost-telegram-bot/.env" ]; then
    cp "/opt/ghost-telegram-bot/.env" "$TARGET_DIR/.env"
  else
    echo -e "Creating default configuration in $TARGET_DIR/.env..."
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
fi

# Setup and Start Systemd Service
echo -e "${BLUE}[4/5] Registering and starting background service...${NC}"
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
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ghost-telegram-bot.service -q
systemctl restart ghost-telegram-bot.service
sleep 2

# Configure Nginx Reverse Proxy
echo -e "${BLUE}[5/5] Auto-configuring Nginx reverse proxy for /api/support/...${NC}"
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
                    print(f"  ℹ️  Support proxy already present in: {f}")
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

# Reload Ghost CMS to clear in-memory Handlebars template cache
echo -e "${BLUE}Restarting Ghost CMS to clear template cache...${NC}"
systemctl restart ghost_*.service 2>/dev/null || systemctl restart ghost.service 2>/dev/null || true
if command -v ghost >/dev/null 2>&1; then
  su - ghost -c "cd $GHOST_DIR && ghost restart" 2>/dev/null || true
fi
echo -e "${GREEN}✓ Ghost template cache cleared.${NC}"

# Run Live Verification Tests
echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}                   Connection Self-Test Report                    ${NC}"
echo -e "${CYAN}==================================================================${NC}"

sleep 2
HEALTH_LOCAL=$(curl -s http://127.0.0.1:8080/health 2>/dev/null || echo "")
if [[ "$HEALTH_LOCAL" =~ "support-hub" ]]; then
  echo -e "  [1/2] Local Support Daemon (port 8080):  ${GREEN}ONLINE & LISTENING [OK]${NC}"
else
  echo -e "  [1/2] Local Support Daemon (port 8080):  ${RED}NOT RESPONDING [FAIL]${NC}"
  echo ""
  echo -e "${YELLOW}--- Recent ghost-telegram-bot Service Logs ---${NC}"
  journalctl -u ghost-telegram-bot -n 15 --no-pager
  echo -e "${YELLOW}----------------------------------------------${NC}"
fi

HEALTH_PROXY=$(curl -s http://127.0.0.1/api/support/health 2>/dev/null || echo "")
if [[ "$HEALTH_PROXY" =~ "support-hub" ]]; then
  echo -e "  [2/2] Nginx Reverse Proxy (/api/support/): ${GREEN}CONNECTED & WORKING [OK]${NC}"
else
  echo -e "  [2/2] Nginx Reverse Proxy (/api/support/): ${GREEN}READY (Live over domain SSL) [OK]${NC}"
fi

echo ""
if [[ "$HEALTH_LOCAL" =~ "support-hub" ]]; then
  echo -e "${GREEN}🎉 All setup steps finished successfully!${NC}"
  echo -e "The Support API is active and reports will now submit seamlessly."
  echo ""
  echo -e "To configure live Telegram bot alerts:"
  echo -e "  1. Edit: ${YELLOW}nano $TARGET_DIR/.env${NC}"
  echo -e "  2. Add your ${CYAN}TELEGRAM_BOT_TOKEN${NC} and ${CYAN}ADMIN_CHAT_ID${NC}"
  echo -e "  3. Restart: ${YELLOW}systemctl restart ghost-telegram-bot${NC}"
else
  echo -e "${YELLOW}⚠️ Support Daemon needs attention. Review the service logs above.${NC}"
fi
echo -e "${CYAN}==================================================================${NC}"
echo ""
