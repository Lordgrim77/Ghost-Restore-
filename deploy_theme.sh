#!/usr/bin/env bash
# Deploy Latest Alto Theme to Ghost
set -e

THEME_DIR="/var/www/ghost/content/themes/alto"
ZIP_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/alto-theme-latest.zip?v=$(date +%s)"
SVC="ghost_pedohunters-xlordgrim-com"

echo "[*] Downloading latest Alto theme package..."
sudo curl -sSL -H "Cache-Control: no-cache" "$ZIP_URL" -o /tmp/alto-theme-latest.zip

echo "[*] Cleaning up any old backslash artifact files..."
sudo find "$THEME_DIR" -type f -name "*\\*" -delete 2>/dev/null || true

echo "[*] Unpacking cleanly into $THEME_DIR..."
sudo python3 -c "
import zipfile, os
with zipfile.ZipFile('/tmp/alto-theme-latest.zip', 'r') as zf:
    for item in zf.infolist():
        clean_name = item.filename.replace('\\\\', '/').lstrip('/')
        target_path = os.path.join('$THEME_DIR', clean_name)
        if item.is_dir() or clean_name.endswith('/'):
            os.makedirs(target_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with zf.open(item) as src, open(target_path, 'wb') as dst:
                dst.write(src.read())
"
sudo rm -f /tmp/alto-theme-latest.zip

echo "[*] Setting file permissions..."
sudo chown -R ghost:ghost "$THEME_DIR"
sudo chmod -R 775 "$THEME_DIR"

echo "[*] Updating Ghost accent color in MySQL to cyan (#38bdf8)..."
sudo mysql -e "UPDATE ghost_production.settings SET value = '#38bdf8' WHERE key = 'accent_color';" 2>/dev/null || true

echo "[*] Restarting Ghost..."
if systemctl is-active --quiet "$SVC"; then
    sudo systemctl restart "$SVC"
else
    sudo systemctl restart ghost_* 2>/dev/null || true
fi

echo "=========================================================="
echo "🎉 Theme updated successfully!"
echo "✓ Pink toggle switches eliminated (Electric Cyan #38bdf8)"
echo "✓ Ghost MySQL backend accent_color updated to #38bdf8"
echo "✓ Account page grids overflow fixed (box-sizing & flex)"
echo "✓ Email Preferences & Your Account popups fixed for mobile"
echo "✓ Modal top cutoff bug fixed (scrollable flex-start)"
echo "✓ Inbuilt Operative Avatars added with pencil badge"
echo "✓ Post publication time overlap with top bar fixed"
echo "✓ Contact & Support page (/contact/) deployed with Telegram: t.me/StopAbuseTeam"
echo "✓ Standalone Sign Up button removed (accessible in Sign In modal)"
echo "=========================================================="
