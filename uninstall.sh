#!/bin/bash
# ==============================================================================
# Ghost Telegram Bot - Uninstaller
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Please run as root (sudo).${NC}"
  exit 1
fi

echo -e "${YELLOW}Stopping and disabling ghost-telegram-bot service...${NC}"
systemctl stop ghost-telegram-bot 2>/dev/null || true
systemctl disable ghost-telegram-bot 2>/dev/null || true

if [ -f "/etc/systemd/system/ghost-telegram-bot.service" ]; then
  rm -f "/etc/systemd/system/ghost-telegram-bot.service"
  systemctl daemon-reload
fi

INSTALL_DIR="/opt/ghost-telegram-bot"
if [ -d "$INSTALL_DIR" ]; then
  echo -e "${YELLOW}Removing application files from $INSTALL_DIR...${NC}"
  rm -rf "$INSTALL_DIR"
fi

echo -e "${GREEN}✓ Ghost Telegram Bot has been completely uninstalled.${NC}"
echo -e "*(Note: Your backups in /var/www/ghost/backups have been kept safe)*"
