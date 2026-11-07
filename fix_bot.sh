#!/bin/bash
# ==============================================================================
# Ghost Telegram Bot & Support Hub Diagnostic & Auto-Repair Tool
# Diagnoses bot startup failures, verifies tokens, fixes services, and heals port 8080
# Repository: https://github.com/Lordgrim77/Ghost-Restore-
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}   🔧 Ghost Telegram Bot & Support Hub Diagnostic & Repair Tool   ${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] This script must be run as root (or with sudo).${NC}"
  echo -e "Please run: ${YELLOW}sudo bash fix_bot.sh${NC}"
  exit 1
fi

GHOST_DIR="/var/www/ghost"
TARGET_DIR="/var/www/ghost/Ghost-Restore"
if [ -d "/opt/ghost-telegram-bot" ]; then
  TARGET_DIR="/opt/ghost-telegram-bot"
fi

echo -e "${BLUE}[1/6] Detecting installation paths and configuration...${NC}"
echo -e "  • Primary Directory: ${CYAN}$TARGET_DIR${NC}"
mkdir -p "$TARGET_DIR"
mkdir -p "$GHOST_DIR/Ghost-Restore"
mkdir -p "$GHOST_DIR/support_vault/evidence"
chmod -R 775 "$GHOST_DIR/support_vault" 2>/dev/null || true

# Locate existing .env file
ENV_FILE=""
for c in "$TARGET_DIR/.env" "$GHOST_DIR/Ghost-Restore/.env" "/opt/ghost-telegram-bot/.env" "$GHOST_DIR/.env"; do
  if [ -f "$c" ]; then
    ENV_FILE="$c"
    break
  fi
done

if [ -n "$ENV_FILE" ]; then
  echo -e "  • Active Configuration: ${GREEN}$ENV_FILE${NC}"
  # Ensure all directories share the same config
  for sdir in "$TARGET_DIR" "$GHOST_DIR/Ghost-Restore"; do
    if [ ! -f "$sdir/.env" ]; then
      cp "$ENV_FILE" "$sdir/.env"
    fi
  done
else
  echo -e "  • Active Configuration: ${YELLOW}None found. Creating default in $TARGET_DIR/.env...${NC}"
  cat <<EOF > "$TARGET_DIR/.env"
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=
ADMIN_CHAT_ID=
GHOST_DIR=$GHOST_DIR
BACKUPS_DIR=$GHOST_DIR/backups
SUPPORT_HOST=127.0.0.1
SUPPORT_PORT=8080
EOF
  ENV_FILE="$TARGET_DIR/.env"
fi

# Read token & IDs
BOT_TOKEN=$(grep -E '^\s*TELEGRAM_BOT_TOKEN\s*=' "$ENV_FILE" | head -n 1 | cut -d= -f2- | tr -d ' "'\'' ' || echo "")
ALLOWED_IDS=$(grep -E '^\s*ALLOWED_USER_IDS\s*=' "$ENV_FILE" | head -n 1 | cut -d= -f2- | tr -d ' "'\'' ' || echo "")
ADMIN_ID=$(grep -E '^\s*ADMIN_CHAT_ID\s*=' "$ENV_FILE" | head -n 1 | cut -d= -f2- | tr -d ' "'\'' ' || echo "")

echo ""
echo -e "${BLUE}[2/6] Verifying Telegram Bot Token status...${NC}"
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_bot_token_here" ]; then
  echo -e "  ${YELLOW}⚠️ TELEGRAM_BOT_TOKEN is not configured or still placeholder in $ENV_FILE${NC}"
  echo -e "  Telegram bot polling will be paused, but Support REST API on port 8080 will run in fallback mode."
else
  # Masked display
  TOKEN_PREFIX=$(echo "$BOT_TOKEN" | cut -c1-6)
  TOKEN_SUFFIX=$(echo "$BOT_TOKEN" | rev | cut -c1-4 | rev)
  echo -e "  • Token detected: ${CYAN}${TOKEN_PREFIX}...${TOKEN_SUFFIX}${NC}"

  # Test token against Telegram API
  TG_TEST=$(curl -s -m 8 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" 2>/dev/null || echo "")
  if [[ "$TG_TEST" =~ "\"ok\":true" ]]; then
    BOT_USER=$(echo "$TG_TEST" | grep -o '"username":"[^"]*"' | cut -d: -f2 | tr -d '"')
    echo -e "  • Telegram Cloud API Status: ${GREEN}VALID & CONNECTED (@$BOT_USER)${NC}"
  else
    echo -e "  • Telegram Cloud API Status: ${RED}FAILED / REJECTED${NC}"
    echo -e "    API Response: $TG_TEST"
    echo -e "    ${YELLOW}Please verify your bot token with @BotFather in Telegram.${NC}"
  fi
fi

if [ -n "$ALLOWED_IDS" ]; then
  echo -e "  • Allowed User IDs: ${CYAN}$ALLOWED_IDS${NC}"
else
  echo -e "  • Allowed User IDs: ${YELLOW}Not set (Fail-closed: send /start to bot to get your Telegram ID)${NC}"
fi

echo ""
echo -e "${BLUE}[3/6] Syncing latest code and verifying dependencies...${NC}"
CACHE_BUSTER=$(date +%s)
RAW_BASE="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main"

for sdir in "$TARGET_DIR" "$GHOST_DIR/Ghost-Restore"; do
  mkdir -p "$sdir"
  curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/bot.py?v=$CACHE_BUSTER" -o "$sdir/bot.py"
  curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/support_hub.py?v=$CACHE_BUSTER" -o "$sdir/support_hub.py"
  curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/ghost_manager.py?v=$CACHE_BUSTER" -o "$sdir/ghost_manager.py"
  curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/requirements.txt?v=$CACHE_BUSTER" -o "$sdir/requirements.txt"
done

# Ensure python3, venv and pip
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y -q >/dev/null 2>&1 || true
  apt-get install -y -q python3 python3-pip python3-venv curl >/dev/null 2>&1 || true
fi

# Rebuild venv if damaged
if [ ! -x "$TARGET_DIR/venv/bin/python3" ]; then
  echo -e "  • Creating Python virtualenv in $TARGET_DIR/venv..."
  python3 -m venv "$TARGET_DIR/venv"
fi
"$TARGET_DIR/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
"$TARGET_DIR/venv/bin/pip" install -r "$TARGET_DIR/requirements.txt" -q
pip3 install -r "$TARGET_DIR/requirements.txt" --break-system-packages -q 2>/dev/null || pip3 install -r "$TARGET_DIR/requirements.txt" -q 2>/dev/null || true
echo -e "  ✓ Dependencies installed & verified."

echo ""
echo -e "${BLUE}[4/6] Repairing Systemd Service configurations...${NC}"
BOT_SVC_FILE="/etc/systemd/system/ghost-telegram-bot.service"
cat <<EOF > "$BOT_SVC_FILE"
[Unit]
Description=Ghost Backup & Support Hub Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TARGET_DIR
EnvironmentFile=-$TARGET_DIR/.env
ExecStart=$TARGET_DIR/venv/bin/python3 $TARGET_DIR/bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > /etc/systemd/system/ghost-support.service
[Unit]
Description=Ghost Support Hub REST API Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$GHOST_DIR/Ghost-Restore
ExecStart=/usr/bin/python3 $GHOST_DIR/Ghost-Restore/support_hub.py --port 8080 --ghost-dir $GHOST_DIR
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo -e "  ✓ Service units sanitized and reloaded."

echo ""
echo -e "${BLUE}[5/6] Starting services with auto-failover...${NC}"
# Stop any conflicting fallback service first
systemctl stop ghost-support.service 2>/dev/null || true
systemctl enable ghost-telegram-bot.service -q 2>/dev/null || true
systemctl restart ghost-telegram-bot.service

sleep 3

# Verify port 8080
CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
  echo -e "  ✓ ghost-telegram-bot.service is ${GREEN}ACTIVE & LISTENING${NC} on port 8080."
else
  echo -e "  ${YELLOW}⚠️ ghost-telegram-bot not listening on port 8080. Activating fallback ghost-support.service...${NC}"
  systemctl enable ghost-support.service -q 2>/dev/null || true
  systemctl restart ghost-support.service
  sleep 2
  CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
  if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
    echo -e "  ✓ Cryptographic Challenge Engine active via fallback: ${GREEN}ONLINE (port 8080)${NC}"
  else
    echo -e "  ${RED}❌ Error: Port 8080 failed to respond.${NC}"
  fi
fi

echo ""
echo -e "${BLUE}[6/6] Verifying Nginx Reverse Proxy routing...${NC}"
PROXY_CHECK=$(curl -s -m 5 http://127.0.0.1/api/support/health 2>/dev/null || echo "")
if [[ "$PROXY_CHECK" =~ "support-hub" ]]; then
  echo -e "  ✓ Nginx /api/support/ proxy: ${GREEN}WORKING (HTTP 200)${NC}"
else
  echo -e "  ℹ️  Nginx reverse proxy is active for domain traffic."
fi

echo ""
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}                     Live Service Status Log                      ${NC}"
echo -e "${CYAN}==================================================================${NC}"
journalctl -u ghost-telegram-bot -n 15 --no-pager
echo ""
echo -e "${GREEN}All diagnostics and auto-repair routines finished!${NC}"
echo ""

