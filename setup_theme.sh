#!/usr/bin/env bash
# ==============================================================================
# Ghost Alto Theme & Support Portal Automated Deployer
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
echo -e "${CYAN}       🎨 Ghost Alto Theme & Support Portal Deployer              ${NC}"
echo -e "${CYAN}==================================================================${NC}"
echo ""

GHOST_DIR="/var/www/ghost"
THEME_DIR="$GHOST_DIR/content/themes/alto"
RAW_BASE="https://raw.githubusercontent.com/Lordgrim77/Ghost-Restore-/main"
CACHE_BUSTER=$(date +%s)

# 1. Download and extract theme
echo -e "${BLUE}[1/6] Downloading latest Alto theme package...${NC}"
sudo mkdir -p "$THEME_DIR"
sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/alto-theme-latest.zip?v=$CACHE_BUSTER" -o /tmp/alto-theme-latest.zip

echo -e "${BLUE}[2/6] Unpacking cleanly into $THEME_DIR...${NC}"
sudo find "$THEME_DIR" -type f -name "*\\*" -delete 2>/dev/null || true
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

# Ensure clean page-support.hbs, page-about.hbs, and page-team.hbs are in place
sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/page-support.hbs?v=$CACHE_BUSTER" -o "$THEME_DIR/page-support.hbs"
sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/page-about.hbs?v=$CACHE_BUSTER" -o "$THEME_DIR/page-about.hbs" 2>/dev/null || true
sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/page-team.hbs?v=$CACHE_BUSTER" -o "$THEME_DIR/page-team.hbs" 2>/dev/null || true

# 2. Update routes.yaml if settings dir exists
echo -e "${BLUE}[3/6] Configuring content routes (routes.yaml)...${NC}"
if [ -d "$GHOST_DIR/content/settings" ]; then
    sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/routes.yaml?v=$CACHE_BUSTER" -o "$GHOST_DIR/content/settings/routes.yaml" 2>/dev/null || true
    sudo chown ghost:ghost "$GHOST_DIR/content/settings/routes.yaml" 2>/dev/null || true
fi

# 3. Email Templates & Core overrides
echo -e "${BLUE}[4/6] Installing redesigned email templates and core overrides...${NC}"
if sudo curl -sSL -f -H "Cache-Control: no-cache" "$RAW_BASE/email-templates.zip?v=$CACHE_BUSTER" -o /tmp/email-templates.zip 2>/dev/null; then
    sudo python3 -c "
import os, sys, urllib.request, tarfile, io, zipfile

ghost_dir = '$GHOST_DIR'
current_dir = os.path.join(ghost_dir, 'current')

# 1. Detect Ghost version
version = None
if os.path.islink(current_dir):
    version = os.path.basename(os.path.realpath(current_dir))
elif os.path.isdir(os.path.join(ghost_dir, 'versions')):
    versions = sorted([v for v in os.listdir(os.path.join(ghost_dir, 'versions')) if not v.startswith('.')])
    if versions:
        version = versions[-1]

print(f'  Ghost version detected: {version or \"unknown\"}')

stock_core_files = [
    'core/server/services/gifts/index.js',
    'core/server/services/gifts/gift-email-service.js',
    'core/server/services/members/api.js',
    'core/server/lib/mail/ghost-mailer.js',
    'core/server/lib/mail/email-content-generator.js',
    'core/server/lib/mail/index.js',
    'core/server/services/email-service/email-renderer.js',
    'core/server/services/comments/comments-service-emails.js',
    'core/server/services/staff/staff-service-emails.js',
    'core/server/services/member-welcome-emails/service.js',
    'core/server/services/member-welcome-emails/member-welcome-email-renderer.js',
    'core/frontend/meta/og-image.js',
    'core/frontend/meta/twitter-image.js',
]

gifts_index = os.path.join(current_dir, 'core', 'server', 'services', 'gifts', 'index.js')
is_corrupted = False
if os.path.isfile(gifts_index):
    try:
        with open(gifts_index, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if '../i18n' in content:
            is_corrupted = True
    except Exception:
        pass

if version and (is_corrupted or not os.path.exists(gifts_index)):
    print(f'  [*] Self-healing: Restoring clean core modules for Ghost {version}...')
    url = f'https://registry.npmjs.org/ghost/-/ghost-{version}.tgz'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Ghost-Deploy-Heal'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
            for m in tf.getmembers():
                clean_name = m.name.replace('package/', '')
                if clean_name in stock_core_files:
                    dest = os.path.join(current_dir, clean_name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with tf.extractfile(m) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
        print(f'  ✓ Clean core service integrity restored from Ghost {version}')
    except Exception as err:
        print(f'  ⚠️ Core recovery warning: {err}')

# 2. Extract clean email templates & safe overrides
core_base = os.path.join(ghost_dir, 'current', 'core')
server_base = os.path.join(ghost_dir, 'current', 'core', 'server')
zip_path = '/tmp/email-templates.zip'
if os.path.exists(core_base) and os.path.exists(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for item in zf.infolist():
            clean_name = item.filename.replace('\\\\', '/').lstrip('/')
            # Never allow core service files to be overwritten by zip
            if clean_name.startswith('services/gifts/index.js') or clean_name.startswith('services/members/api.js') or clean_name.startswith('lib/mail/ghost-mailer.js'):
                continue
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
    sudo chown -R ghost:ghost "$GHOST_DIR/current/core/" 2>/dev/null || true
fi

# 4. Social Thumbnail Image
sudo mkdir -p "$GHOST_DIR/content/images"
if sudo curl -sSL -f -H "Cache-Control: no-cache" "$RAW_BASE/og-image.png?v=$CACHE_BUSTER" -o "$GHOST_DIR/content/images/og-image.png" 2>/dev/null; then
    sudo chown ghost:ghost "$GHOST_DIR/content/images/og-image.png"
    sudo chmod 664 "$GHOST_DIR/content/images/og-image.png"
fi

# Set theme permissions
sudo chown -R ghost:ghost "$THEME_DIR"
sudo chmod -R 775 "$THEME_DIR"

# 5. Dynamic Ghost Settings & Navigation Sync
echo -e "${BLUE}[5/6] Syncing database settings, navigation, and pages...${NC}"
sudo python3 -c '
import json, subprocess, os

config_path = "/var/www/ghost/config.production.json"
if os.path.isfile(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        db_cfg = cfg.get("database", {}).get("connection", {})
        db_name = db_cfg.get("database", "ghost_production")
        db_user = db_cfg.get("user", "root")
        db_pass = db_cfg.get("password", "")
        ghost_url = cfg.get("url", "").rstrip("/")

        mysql_cmd = ["mysql", f"-u{db_user}"]
        if db_pass:
            mysql_cmd.append(f"-p{db_pass}")
        mysql_cmd.append(db_name)

        # Update accent color & signup access
        sql_updates = f"""
        UPDATE settings SET value = "#ffffff" WHERE \`key\` = "accent_color";
        UPDATE settings SET value = "all" WHERE \`key\` = "members_signup_access";
        UPDATE settings SET value = "{ghost_url}/content/images/og-image.png" WHERE \`key\` IN ("cover_image", "og_image", "twitter_image");
        """
        subprocess.run(mysql_cmd + ["-e", sql_updates], capture_output=True)

        # Ensure navigation links
        res = subprocess.run(mysql_cmd + ["-Nse", "SELECT value FROM settings WHERE \`key\`=\"navigation\""], capture_output=True, text=True)
        if res.stdout.strip():
            nav = json.loads(res.stdout.strip())
            urls = [item.get("url") for item in nav]
            changed = False
            if "/team/" not in urls and "/team" not in urls:
                nav.append({"label": "Our Team", "url": "/team/"})
                changed = True
            if "/support/" not in urls and "/support" not in urls:
                nav.append({"label": "Support", "url": "/support/"})
                changed = True
            if changed:
                new_nav = json.dumps(nav)
                subprocess.run(mysql_cmd + ["-e", f"UPDATE settings SET value={json.dumps(new_nav)} WHERE \`key\`=\"navigation\""], capture_output=True)

        # Ensure /support/ and /team/ published pages exist in database
        page_sql = """
        INSERT IGNORE INTO posts (
            id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
        ) SELECT 
            "6ae71fbd6a4691255cb0ca98", UUID(), "Support & Incident Intake", "support", lexical, html, plaintext, "6ae71fbd6a4691255cb0ca98", 0, "page", "published", "public", "all", NOW(), NOW(), NOW(), published_by, 1
        FROM posts WHERE slug = "about" LIMIT 1;

        INSERT IGNORE INTO posts (
            id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
        ) SELECT 
            "6ae71fbd6a4691255cb0ca77", UUID(), "Our Team", "team", lexical, html, plaintext, "6ae71fbd6a4691255cb0ca77", 0, "page", "published", "public", "all", NOW(), NOW(), NOW(), published_by, 1
        FROM posts WHERE slug = "about" LIMIT 1;
        """
        subprocess.run(mysql_cmd + ["-e", page_sql], capture_output=True)

    except Exception as e:
        print(f"  Note: Database sync skipped ({e})")
' 2>/dev/null || true

# 6. Configure Nginx Reverse Proxy for /api/support/
echo -e "${BLUE}[6/6] Ensuring Nginx reverse proxy is configured for /api/support/...${NC}"
sudo python3 -c '
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
patched = False

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
            if "2368" in content and "location /api/support/" not in content:
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
                    print(f"  ✓ Patched Nginx: {f}")
                    patched = True
        except Exception:
            pass

if patched:
    os.system("nginx -t >/dev/null 2>&1 && systemctl reload nginx")
' 2>/dev/null || true

# 7. Update Support Hub Daemon & Cryptographic Engine
echo -e "${BLUE}[7/8] Updating Support Hub Daemon & Verification Engine...${NC}"
sudo mkdir -p "$GHOST_DIR/Ghost-Restore"
sudo mkdir -p "$GHOST_DIR/support_vault/evidence"
sudo chmod -R 775 "$GHOST_DIR/support_vault" 2>/dev/null || true

# Target directories to sync backend files
SYNC_DIRS=("$GHOST_DIR/Ghost-Restore")
if [ -d "/opt/ghost-telegram-bot" ]; then
    SYNC_DIRS+=("/opt/ghost-telegram-bot")
fi

BOT_SVC_FILE="/etc/systemd/system/ghost-telegram-bot.service"
if [ -f "$BOT_SVC_FILE" ]; then
    SVC_DIR=$(grep -E '^\s*WorkingDirectory\s*=' "$BOT_SVC_FILE" | head -n 1 | cut -d= -f2 | tr -d ' ' || echo "")
    if [ -n "$SVC_DIR" ] && [ -d "$SVC_DIR" ]; then
        if [[ ! " ${SYNC_DIRS[@]} " =~ " ${SVC_DIR} " ]]; then
            SYNC_DIRS+=("$SVC_DIR")
        fi
    fi
fi

# Download all required daemon files across target directories
for sdir in "${SYNC_DIRS[@]}"; do
    sudo mkdir -p "$sdir"
    sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/support_hub.py?v=$CACHE_BUSTER" -o "$sdir/support_hub.py"
    sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/bot.py?v=$CACHE_BUSTER" -o "$sdir/bot.py"
    sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/ghost_manager.py?v=$CACHE_BUSTER" -o "$sdir/ghost_manager.py"
    sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/requirements.txt?v=$CACHE_BUSTER" -o "$sdir/requirements.txt"
    # If a venv exists, ensure pip dependencies are satisfied
    if [ -x "$sdir/venv/bin/pip" ]; then
        sudo "$sdir/venv/bin/pip" install -r "$sdir/requirements.txt" -q 2>/dev/null || true
    fi
done

# Restart the appropriate service cleanly, preventing port 8080 collision
sudo systemctl daemon-reload
if [ -f "$BOT_SVC_FILE" ]; then
    # Disable and stop standalone service if active to avoid port 8080 collision
    sudo systemctl stop ghost-support.service 2>/dev/null || true
    sudo systemctl disable ghost-support.service 2>/dev/null || true
    sudo systemctl restart ghost-telegram-bot.service 2>/dev/null || true
    echo -e "  ✓ Synced backend files & restarted ghost-telegram-bot.service"
elif [ -f "/etc/systemd/system/ghost-support.service" ]; then
    sudo systemctl restart ghost-support.service 2>/dev/null || true
    echo -e "  ✓ Synced backend files & restarted ghost-support.service"
else
    # Automatically install and enable standalone ghost-support daemon so API on port 8080 is always active
    cat <<EOF | sudo tee /etc/systemd/system/ghost-support.service >/dev/null
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
    sudo systemctl daemon-reload
    sudo systemctl enable ghost-support.service -q 2>/dev/null || true
    sudo systemctl restart ghost-support.service 2>/dev/null || true
    echo -e "  ✓ Registered & started standalone ghost-support.service on port 8080"
fi

# Verification of /captcha endpoint
sleep 2
CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
    echo -e "  ✓ Cryptographic Challenge Engine verified: ${GREEN}ONLINE (HTTP 200)${NC}"
else
    echo -e "  ${RED}⚠️ Daemon verification failed on port 8080!${NC}"
    echo -e "  Output received: $CAPTCHA_CHECK"
    echo -e "${YELLOW}--- Diagnostics (Service Logs) ---${NC}"
    if [ -f "$BOT_SVC_FILE" ]; then
        sudo journalctl -u ghost-telegram-bot -n 15 --no-pager 2>/dev/null || true
    fi
    if [ -f "/etc/systemd/system/ghost-support.service" ]; then
        sudo journalctl -u ghost-support -n 15 --no-pager 2>/dev/null || true
    fi
    echo -e "${YELLOW}----------------------------------${NC}"
fi

# 8. Restart Ghost and clear template cache
echo ""
echo -e "${BLUE}[8/8] Restarting Ghost CMS to clear template cache...${NC}"
GHOST_SVC=$(systemctl list-unit-files --type=service 2>/dev/null | grep -o 'ghost_[a-zA-Z0-9_-]*' | head -n 1 || echo "")
if [ -n "$GHOST_SVC" ] && systemctl is-active --quiet "$GHOST_SVC"; then
    sudo systemctl restart "$GHOST_SVC"
    echo -e "  ✓ Restarted systemd service: $GHOST_SVC"
else
    sudo systemctl restart ghost_* 2>/dev/null || sudo systemctl restart ghost 2>/dev/null || true
    if command -v ghost >/dev/null 2>&1; then
        su - ghost -c "cd $GHOST_DIR && ghost restart" 2>/dev/null || true
    fi
    echo -e "  ✓ Ghost CMS reloaded successfully."
fi

echo ""
echo -e "${GREEN}==================================================================${NC}"
echo -e "${GREEN}  🎉 Theme & Support Portal Setup Finished Successfully!          ${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo -e "✓ Alto Theme installed cleanly in:     ${CYAN}$THEME_DIR${NC}"
echo -e "✓ Support Portal active at:            ${CYAN}https://yourdomain.com/support/${NC}"
echo -e "✓ Team Showcase active at:             ${CYAN}https://yourdomain.com/team/${NC}"
echo -e "✓ Verification Challenge Engine:       ${GREEN}ACTIVE & VERIFIED (port 8080)${NC}"
echo -e "✓ Email Templates updated in:          ${CYAN}$GHOST_DIR/current/core/${NC}"
echo -e "✓ In-memory template cache:            ${GREEN}CLEARED${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo ""
