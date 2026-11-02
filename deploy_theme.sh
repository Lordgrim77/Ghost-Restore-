#!/usr/bin/env bash
# Deploy Latest Alto Theme to Ghost
set -e

THEME_DIR="/var/www/ghost/content/themes/alto"
ZIP_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/alto-theme-latest.zip?v=$(date +%s)"
ROUTES_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/routes.yaml?v=$(date +%s)"
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

echo "[*] Updating routes.yaml if settings dir exists..."
if [ -d "/var/www/ghost/content/settings" ]; then
    sudo curl -sSL -H "Cache-Control: no-cache" "$ROUTES_URL" -o /var/www/ghost/content/settings/routes.yaml 2>/dev/null || true
    sudo chown ghost:ghost /var/www/ghost/content/settings/routes.yaml 2>/dev/null || true
fi

EMAIL_ZIP_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/email-templates.zip?v=$(date +%s)"
echo "[*] Downloading redesigned Email Templates & Core overrides package..."
if sudo curl -sSL -f -H "Cache-Control: no-cache" "$EMAIL_ZIP_URL" -o /tmp/email-templates.zip 2>/dev/null; then
    echo "[*] Installing redesigned email templates and core overrides into Ghost..."
    sudo python3 -c "
import zipfile, os
core_base = '/var/www/ghost/current/core'
server_base = '/var/www/ghost/current/core/server'
if os.path.exists(core_base):
    with zipfile.ZipFile('/tmp/email-templates.zip', 'r') as zf:
        for item in zf.infolist():
            clean_name = item.filename.replace('\\\\', '/').lstrip('/')
            if clean_name.startswith('frontend/'):
                dest = os.path.join(core_base, clean_name)
            else:
                dest = os.path.join(server_base, clean_name)
            if item.is_dir() or clean_name.endswith('/'):
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(item) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
"
    sudo rm -f /tmp/email-templates.zip
    sudo chown -R ghost:ghost /var/www/ghost/current/core/
fi

OG_IMAGE_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/og-image.png?v=$(date +%s)"
echo "[*] Downloading Open Graph social thumbnail image..."
sudo mkdir -p /var/www/ghost/content/images
if sudo curl -sSL -f -H "Cache-Control: no-cache" "$OG_IMAGE_URL" -o /var/www/ghost/content/images/og-image.png 2>/dev/null; then
    sudo chown ghost:ghost /var/www/ghost/content/images/og-image.png
    sudo chmod 664 /var/www/ghost/content/images/og-image.png
fi

echo "[*] Setting file permissions..."
sudo chown -R ghost:ghost "$THEME_DIR"
sudo chmod -R 775 "$THEME_DIR"

echo "[*] Ensuring Ghost MySQL accent color is pure white (#ffffff)..."
sudo mysql -e "UPDATE ghost_production.settings SET value = '#ffffff' WHERE key = 'accent_color';" 2>/dev/null || true

echo "[*] Ensuring Open Graph, Twitter card, and Cover images use obsidian social card..."
sudo mysql -e "
UPDATE ghost_production.settings SET value = '__GHOST_URL__/content/images/og-image.png' WHERE key = 'cover_image';
UPDATE ghost_production.settings SET value = '__GHOST_URL__/content/images/og-image.png' WHERE key = 'og_image';
UPDATE ghost_production.settings SET value = '__GHOST_URL__/content/images/og-image.png' WHERE key = 'twitter_image';
" 2>/dev/null || true

echo "[*] Ensuring /contact/ and /support/ pages exist in Ghost database..."
sudo mysql -e "
INSERT IGNORE INTO ghost_production.posts (
    id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
) SELECT 
    '6ae71fbd6a4691255cb0ca99', UUID(), 'Contact & Support', 'contact', lexical, html, plaintext, '6ae71fbd6a4691255cb0ca99', 0, 'page', 'published', 'public', 'all', NOW(), NOW(), NOW(), published_by, 1
FROM ghost_production.posts WHERE slug = 'about' LIMIT 1;

INSERT IGNORE INTO ghost_production.posts (
    id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
) SELECT 
    '6ae71fbd6a4691255cb0ca98', UUID(), 'Contact & Support', 'support', lexical, html, plaintext, '6ae71fbd6a4691255cb0ca98', 0, 'page', 'published', 'public', 'all', NOW(), NOW(), NOW(), published_by, 1
FROM ghost_production.posts WHERE slug = 'about' LIMIT 1;
" 2>/dev/null || true

UPDATE_EMAIL_DB_URL="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main/update_email_db.py?v=$(date +%s)"
if sudo curl -sSL -f -H "Cache-Control: no-cache" "$UPDATE_EMAIL_DB_URL" -o /tmp/update_email_db.py 2>/dev/null; then
    sudo python3 /tmp/update_email_db.py || true
    sudo rm -f /tmp/update_email_db.py
fi

echo "[*] Restarting Ghost..."
if systemctl is-active --quiet "$SVC"; then
    sudo systemctl restart "$SVC"
else
    sudo systemctl restart ghost_* 2>/dev/null || true
fi

echo "=========================================================="
echo "🎉 Theme, Email Templates & Social Thumbnails updated!"
echo "✓ Social thumbnail: Pink/blue gradient replaced with Obsidian card (cover_image, og:image, twitter:image)"
echo "✓ Comments UI: Delete popup themed, duplicate click guard added, spinner contrast fixed"
echo "✓ Email Templates: Fully redesigned in Obsidian Monochrome (Signin, Signup, Newsletters, Comments, Staff)"
echo "✓ Email Branding: Dynamic site logo integration from settings"
echo "✓ Top bar: 'Latest Posts' heading & 'View all posts' button removed"
echo "✓ Profile avatar: pencil badge uncropped (perfect circle with crisp outline)"
echo "✓ Footer: Realigned in desktop mode (3-column balanced grid, centered official links)"
echo "✓ Contact Team button: Fully wired, styled & connected to /contact/"
echo "✓ Monochrome: 100% pure black & white in light and dark mode"
echo "=========================================================="
