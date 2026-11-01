#!/usr/bin/env bash
# Deploy Latest Alto Theme to Ghost
set -e

THEME_DIR="/var/www/ghost/content/themes/alto"
ZIP_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/alto-theme-latest.zip?v=$(date +%s)"
SVC="ghost_pedohunters-xlordgrim-com"

echo "[*] Downloading latest Alto theme package..."
sudo curl -sSL -H "Cache-Control: no-cache" "$ZIP_URL" -o /tmp/alto-theme-latest.zip

echo "[*] Unpacking into $THEME_DIR..."
sudo mkdir -p "$THEME_DIR"
sudo unzip -q -o /tmp/alto-theme-latest.zip -d "$THEME_DIR"
sudo rm -f /tmp/alto-theme-latest.zip

echo "[*] Setting file permissions..."
sudo chown -R ghost:ghost "$THEME_DIR"
sudo chmod -R 775 "$THEME_DIR"

echo "[*] Restarting Ghost..."
if systemctl is-active --quiet "$SVC"; then
    sudo systemctl restart "$SVC"
else
    # Try generic restart if specific service name varies
    sudo systemctl restart ghost_* 2>/dev/null || true
fi

echo "=========================================================="
echo "🎉 Theme updated successfully!"
echo "✓ Account page grids overflow fixed (box-sizing & flex)"
echo "✓ Inbuilt Operative Avatars added (zero upload storage)"
echo "✓ Post publication time overlap with top bar fixed"
echo "✓ Contact & Support page (/contact/) deployed with Telegram: t.me/StopAbuseTeam"
echo "✓ Standalone Sign Up button removed (accessible in Sign In modal)"
echo "=========================================================="
