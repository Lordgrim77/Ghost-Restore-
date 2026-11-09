#!/bin/bash
# ==============================================================================
# Ghost Telegram Bot & Support Hub - Uninstaller
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Please run as root (sudo).${NC}"
  exit 1
fi

echo -e "${YELLOW}Stopping and disabling ghost-telegram-bot and ghost-support services...${NC}"
for svc in ghost-telegram-bot ghost-support; do
  systemctl stop "$svc" 2>/dev/null || true
  systemctl disable "$svc" 2>/dev/null || true
  if [ -f "/etc/systemd/system/${svc}.service" ]; then
    rm -f "/etc/systemd/system/${svc}.service"
  fi
done
systemctl daemon-reload

INSTALL_DIR="/opt/ghost-telegram-bot"
if [ -d "$INSTALL_DIR" ]; then
  echo -e "${YELLOW}Removing application files from $INSTALL_DIR...${NC}"
  rm -rf "$INSTALL_DIR"
fi

echo -e "${GREEN}✓ Ghost Telegram Bot & Support Hub services have been cleanly uninstalled.${NC}"
echo -e "*(Note: Your backups in /var/www/ghost/backups and support vault in /var/www/ghost/support_vault have been kept safe)*"
