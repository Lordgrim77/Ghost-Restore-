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

# Ensure clean page-support.hbs is in place
sudo curl -sSL -H "Cache-Control: no-cache" "$RAW_BASE/page-support.hbs?v=$CACHE_BUSTER" -o "$THEME_DIR/page-support.hbs"

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
import zipfile, os
core_base = '$GHOST_DIR/current/core'
server_base = '$GHOST_DIR/current/core/server'
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

# 7. Restart Ghost and clear template cache
echo ""
echo -e "${BLUE}Restarting Ghost CMS to clear template cache...${NC}"
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
echo -e "✓ Alto Theme installed cleanly in: ${CYAN}$THEME_DIR${NC}"
echo -e "✓ Support Portal active at:        ${CYAN}https://yourdomain.com/support/${NC}"
echo -e "✓ Team Showcase active at:         ${CYAN}https://yourdomain.com/team/${NC}"
echo -e "✓ Email Templates updated in:      ${CYAN}$GHOST_DIR/current/core/${NC}"
echo -e "✓ In-memory template cache:        ${GREEN}CLEARED${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo ""
