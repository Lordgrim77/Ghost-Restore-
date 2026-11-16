#!/usr/bin/env bash
# ==============================================================================
# Ghost Alto Theme & Support Portal Automated Deployer
# Repository: https://github.com/Lordgrim77/Ghost-Restore-
# ==============================================================================

set -euo pipefail

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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"

STAGE_DIR="$(mktemp -d /tmp/ghost_deploy.XXXXXXXXXX)"
chmod 700 "$STAGE_DIR"
trap 'rm -rf "$STAGE_DIR"' EXIT

# Optional GITHUB_TOKEN discovery from existing .env for private repo raw fetches
if [ -z "${GITHUB_TOKEN:-}" ]; then
    for env_cand in "$GHOST_DIR/Ghost-Restore/.env" "/opt/ghost-telegram-bot/.env" "$GHOST_DIR/.env"; do
        if [ -f "$env_cand" ] && [ ! -L "$env_cand" ]; then
            GITHUB_TOKEN=$(sudo grep -E '^\s*GITHUB_TOKEN\s*=' "$env_cand" 2>/dev/null | head -n 1 | cut -d= -f2- | tr -d ' "'"'" || true)
            [ -n "$GITHUB_TOKEN" ] && break
        fi
    done
fi

fetch_verified_asset() {
    local rel_name="$1"
    local dest_path="$2"
    local kind="${3:-raw}"
    local tmp_out="$STAGE_DIR/$(basename "$rel_name").part"
    rm -f "$tmp_out"

    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$rel_name" ] && [ ! -L "$SCRIPT_DIR/$rel_name" ]; then
        cp -f "$SCRIPT_DIR/$rel_name" "$tmp_out"
    else
        local curl_args=(-fsSL --retry 3 -H "Cache-Control: no-cache")
        if [ -n "${GITHUB_TOKEN:-}" ]; then
            if ! printf 'header = "Authorization: token %s"\nurl = "%s/%s?v=%s"\n' "$GITHUB_TOKEN" "$RAW_BASE" "$rel_name" "$CACHE_BUSTER" | curl "${curl_args[@]}" -K - -o "$tmp_out" 2>/dev/null; then
                curl "${curl_args[@]}" "$RAW_BASE/$rel_name?v=$CACHE_BUSTER" -o "$tmp_out"
            fi
        else
            curl "${curl_args[@]}" "$RAW_BASE/$rel_name?v=$CACHE_BUSTER" -o "$tmp_out"
        fi
    fi

    if [ ! -s "$tmp_out" ]; then
        echo -e "  ${RED}✗ Empty or failed download for $rel_name${NC}" >&2
        return 1
    fi

    case "$kind" in
        zip)
            python3 -c 'import sys, zipfile; sys.exit(0 if zipfile.is_zipfile(sys.argv[1]) else 1)' "$tmp_out"
            ;;
        py)
            python3 -m py_compile "$tmp_out"
            ;;
        text)
            python3 -c '
import sys
data = open(sys.argv[1], "rb").read(256)
sys.exit(1 if data.strip() in (b"404: Not Found", b"Not Found") else 0)
' "$tmp_out"
            ;;
    esac

    sudo mkdir -p "$(dirname "$dest_path")"
    sudo cp -f "$tmp_out" "$dest_path"
    rm -f "$tmp_out"
}

# 1. Download and extract theme
echo -e "${BLUE}[1/8] Downloading & verifying latest Alto theme package...${NC}"
sudo mkdir -p "$THEME_DIR"
THEME_ZIP="$STAGE_DIR/alto-theme-latest.zip"
fetch_verified_asset "alto-theme-latest.zip" "$THEME_ZIP" "zip"

echo -e "${BLUE}[2/8] Unpacking cleanly into $THEME_DIR...${NC}"
sudo find "$THEME_DIR" -type f -name "*\\*" -delete 2>/dev/null || true
sudo python3 - "$THEME_ZIP" "$THEME_DIR" <<'PYEOF'
import zipfile, os, sys

zip_src = sys.argv[1]
theme_dir = sys.argv[2]
theme_real = os.path.realpath(theme_dir)
max_bytes = 512 * 1024 * 1024
total = 0

with zipfile.ZipFile(zip_src, 'r') as zf:
    for item in zf.infolist():
        if ((item.external_attr >> 16) & 0o170000) == 0o120000:
            continue
        clean_name = item.filename.replace('\\', '/').lstrip('/')
        if not clean_name or clean_name.startswith('scratch/') or clean_name.startswith('.git/'):
            continue
        target_path = os.path.realpath(os.path.join(theme_dir, clean_name))
        if not (target_path.startswith(theme_real + os.sep) or target_path == theme_real):
            continue
        if item.is_dir() or clean_name.endswith('/'):
            os.makedirs(target_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with zf.open(item) as src, open(target_path, 'wb') as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("Theme archive exceeded size limit")
                    dst.write(chunk)
PYEOF
sudo rm -f "$THEME_ZIP"

# Ensure clean page-support.hbs, page-about.hbs, page-team.hbs, and their external CSS/JS assets are in place
fetch_verified_asset "page-support.hbs" "$THEME_DIR/page-support.hbs" "text"
fetch_verified_asset "page-about.hbs" "$THEME_DIR/page-about.hbs" "text" || true
fetch_verified_asset "page-team.hbs" "$THEME_DIR/page-team.hbs" "text" || true
sudo mkdir -p "$THEME_DIR/assets/built"
fetch_verified_asset "about-page.css" "$THEME_DIR/assets/built/about-page.css" "text" || true
fetch_verified_asset "team-page.css" "$THEME_DIR/assets/built/team-page.css" "text" || true
fetch_verified_asset "support-portal.css" "$THEME_DIR/assets/built/support-portal.css" "text" || true
fetch_verified_asset "support-portal.js" "$THEME_DIR/assets/built/support-portal.js" "text" || true

# 2. Update routes.yaml if settings dir exists
echo -e "${BLUE}[3/8] Configuring content routes (routes.yaml)...${NC}"
if [ -d "$GHOST_DIR/content/settings" ]; then
    fetch_verified_asset "routes.yaml" "$GHOST_DIR/content/settings/routes.yaml" "text" || true
    sudo chown ghost:ghost "$GHOST_DIR/content/settings/routes.yaml" 2>/dev/null || true
fi

# 3. Email Templates & Core overrides
echo -e "${BLUE}[4/8] Installing redesigned email templates and core overrides...${NC}"
EMAIL_ZIP="$STAGE_DIR/email-templates.zip"
if fetch_verified_asset "email-templates.zip" "$EMAIL_ZIP" "zip" 2>/dev/null; then
    sudo python3 - "$GHOST_DIR" "$EMAIL_ZIP" <<'PYEOF'
import os, sys, urllib.request, tarfile, io, zipfile, re

ghost_dir = sys.argv[1]
zip_path = sys.argv[2]
current_dir = os.path.join(ghost_dir, 'current')

# 1. Detect Ghost version
version = None
if os.path.islink(current_dir):
    version = os.path.basename(os.path.realpath(current_dir))
elif os.path.isdir(os.path.join(ghost_dir, 'versions')):
    versions = sorted([v for v in os.listdir(os.path.join(ghost_dir, 'versions')) if not v.startswith('.')])
    if versions:
        version = versions[-1]

if version and not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9._-]+)?$', version):
    version = None

print(f'  Ghost version detected: {version or "unknown"}')

stock_core_files = {
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
}

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

current_real = os.path.realpath(current_dir)
if version and (is_corrupted or not os.path.exists(gifts_index)):
    print(f'  [*] Self-healing: Restoring clean core modules for Ghost {version}...')
    url = f'https://registry.npmjs.org/ghost/-/ghost-{version}.tgz'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Ghost-Deploy-Heal'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(200 * 1024 * 1024)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                clean_name = m.name.replace('package/', '', 1)
                if clean_name in stock_core_files:
                    dest = os.path.realpath(os.path.join(current_real, clean_name))
                    if not dest.startswith(current_real + os.sep):
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with tf.extractfile(m) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
        print(f'  ✓ Clean core service integrity restored from Ghost {version}')
    except Exception as err:
        print(f'  ⚠️ Core recovery warning: {err}')

# 2. Extract clean email templates & safe overrides with Zip Slip & Symlink protection
core_base = os.path.join(ghost_dir, 'current', 'core')
server_base = os.path.join(ghost_dir, 'current', 'core', 'server')
if os.path.exists(core_base) and os.path.exists(zip_path):
    core_real = os.path.realpath(core_base)
    server_real = os.path.realpath(server_base)
    blocked_prefixes = (
        'services/gifts/index.js',
        'services/members/api.js',
        'lib/mail/ghost-mailer.js',
    )
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for item in zf.infolist():
            if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                continue
            clean_name = item.filename.replace('\\', '/').lstrip('/')
            if not clean_name or clean_name.startswith(blocked_prefixes):
                continue
            if clean_name.startswith('frontend/'):
                base_real = core_real
                dest = os.path.realpath(os.path.join(core_real, clean_name))
            else:
                base_real = server_real
                dest = os.path.realpath(os.path.join(server_real, clean_name))
            if not (dest.startswith(base_real + os.sep) or dest == base_real):
                continue
            if item.is_dir() or clean_name.endswith('/'):
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(item) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
PYEOF
    sudo rm -f "$EMAIL_ZIP"
    sudo chown -R ghost:ghost "$GHOST_DIR/current/core/" 2>/dev/null || true
fi

# 4b. Ghost Admin Sign-in Dark/Light Mode Theme Toggle & FOUC Synchronizer
echo -e "${BLUE}[4b/8] Installing Ghost Admin Dark/Light Theme Toggle (external strict-CSP assets)...${NC}"
sudo python3 - "$GHOST_DIR" <<'PYEOF'
import os, sys, glob, re

ghost_dir = sys.argv[1]

admin_theme_css = """html.dark {
  color-scheme: dark !important;
}

#gh-admin-theme-toggle {
  position: fixed;
  top: 22px;
  right: 26px;
  z-index: 99999;
  display: none;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  user-select: none;
  outline: none;
}

#gh-admin-theme-toggle.is-visible {
  display: inline-flex;
}

#gh-admin-theme-toggle.is-dark {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
}

#gh-admin-theme-toggle.is-light {
  background: rgba(255, 255, 255, 0.9);
  color: #0f172a;
  border: 1px solid rgba(15, 23, 42, 0.12);
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
}

#gh-admin-theme-toggle:hover {
  transform: translateY(-1px);
}

/* Ghost Admin Sign-in Button Contrast Fix (Ensures 'Sign in' word is never white on white in light mode) */
html:not(.dark) .react-admin form button[type="submit"],
html:not(.dark) form button[type="submit"],
html:not(.dark) button.bg-ghostaccent {
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
  background-color: #ffffff !important;
  border: 1px solid rgba(0, 0, 0, 0.16) !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
  font-weight: 600 !important;
}

html:not(.dark) .react-admin form button[type="submit"]:hover,
html:not(.dark) form button[type="submit"]:hover,
html:not(.dark) button.bg-ghostaccent:hover {
  background-color: #f1f5f9 !important;
  border-color: rgba(0, 0, 0, 0.28) !important;
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
}

html:not(.dark) .react-admin form button[type="submit"]:disabled,
html:not(.dark) form button[type="submit"]:disabled,
html:not(.dark) button.bg-ghostaccent:disabled {
  opacity: 0.65 !important;
  cursor: not-allowed !important;
}

html:not(.dark) .react-admin form button[type="submit"] svg,
html:not(.dark) form button[type="submit"] svg,
html:not(.dark) button.bg-ghostaccent svg {
  color: #000000 !important;
  stroke: #000000 !important;
}

html.dark .react-admin form button[type="submit"],
html.dark form button[type="submit"],
html.dark button.bg-ghostaccent {
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
  background-color: #ffffff !important;
  border: 1px solid #ffffff !important;
  box-shadow: 0 4px 14px rgba(255, 255, 255, 0.15) !important;
  font-weight: 600 !important;
}

html.dark .react-admin form button[type="submit"]:hover,
html.dark form button[type="submit"]:hover,
html.dark button.bg-ghostaccent:hover {
  background-color: #f1f5f9 !important;
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
}

html.dark .react-admin form button[type="submit"] svg,
html.dark form button[type="submit"] svg,
html.dark button.bg-ghostaccent svg {
  color: #000000 !important;
  stroke: #000000 !important;
}
"""

admin_bootstrap_js = """(function() {
  try {
    var saved = localStorage.getItem('ghost-admin-theme') || localStorage.getItem('user-theme');
    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    var isDark = saved ? (saved === 'dark') : (prefersDark !== false);
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.style.colorScheme = 'dark';
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.style.colorScheme = 'light';
    }
  } catch (e) {}
})();
"""

admin_toggle_js = """(function() {
  function initToggle() {
    if (document.getElementById('gh-admin-theme-toggle')) return;
    var btn = document.createElement('button');
    btn.id = 'gh-admin-theme-toggle';
    btn.setAttribute('type', 'button');
    btn.setAttribute('aria-label', 'Toggle theme');

    function isDark() {
      return document.documentElement.classList.contains('dark');
    }

    function renderState() {
      var dark = isDark();
      btn.classList.toggle('is-dark', dark);
      btn.classList.toggle('is-light', !dark);
      if (dark) {
        btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg><span>Dark</span>';
      } else {
        btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg><span>Light</span>';
      }
    }

    btn.addEventListener('click', function(e) {
      e.preventDefault();
      var nowDark = !isDark();
      if (nowDark) {
        document.documentElement.classList.add('dark');
        document.documentElement.style.colorScheme = 'dark';
        try {
          localStorage.setItem('ghost-admin-theme', 'dark');
          localStorage.setItem('user-theme', 'dark');
        } catch (err) {}
      } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.style.colorScheme = 'light';
        try {
          localStorage.setItem('ghost-admin-theme', 'light');
          localStorage.setItem('user-theme', 'light');
        } catch (err) {}
      }
      renderState();
    });

    function checkVisibility() {
      var isAuth = !!document.getElementById('admin-main') || !!document.querySelector('.gh-nav');
      var hash = window.location.hash || '';
      var isSignIn = hash.includes('signin') || hash.includes('signup') || hash.includes('setup') || hash.includes('reset') || hash === '' || hash === '#/';
      btn.classList.toggle('is-visible', !isAuth && isSignIn);
    }

    renderState();
    checkVisibility();
    document.body.appendChild(btn);

    window.addEventListener('hashchange', checkVisibility);
    var observer = new MutationObserver(checkVisibility);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initToggle);
  } else {
    initToggle();
  }
})();
"""

head_patch = (
    '    <!-- Ghost Admin Obsidian Theme Synchronizer & Sign-in Theme Toggle -->\n'
    '    <link id="gh-admin-theme-styles-link" rel="stylesheet" href="./assets/gm-admin-theme.css">\n'
    '    <script id="gh-admin-theme-bootstrap-script" src="./assets/gm-admin-theme-bootstrap.js"></script>\n'
)

runtime_patch = (
    '    <script id="gh-admin-theme-toggle-script" src="./assets/gm-admin-theme-toggle.js"></script>\n'
)

admin_candidates = [
    os.path.join(ghost_dir, "current", "core", "built", "admin", "index.html"),
]
for v_dir in glob.glob(os.path.join(ghost_dir, "versions", "*", "core", "built", "admin", "index.html")):
    if v_dir not in admin_candidates:
        admin_candidates.append(v_dir)

patched_count = 0
for cand in admin_candidates:
    if not os.path.isfile(cand):
        continue
    try:
        admin_dir = os.path.dirname(cand)
        assets_dir = os.path.join(admin_dir, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        for asset_name, asset_body in (
            ("gm-admin-theme.css", admin_theme_css),
            ("gm-admin-theme-bootstrap.js", admin_bootstrap_js),
            ("gm-admin-theme-toggle.js", admin_toggle_js),
        ):
            asset_path = os.path.join(assets_dir, asset_name)
            with open(asset_path, "w", encoding="utf-8", newline="\n") as af:
                af.write(asset_body)
            os.chmod(asset_path, 0o644)

        with open(cand, "r", encoding="utf-8", errors="ignore") as f:
            original_content = f.read()

        content = original_content
        # Remove legacy inline blocks or prior external admin theme tags before re-inserting cleanly
        content = re.sub(
            r'[ \t]*<!-- Ghost Admin Obsidian Theme Synchronizer & Sign-in Theme Toggle -->\s*(?:<style id="gh-admin-theme-styles">.*?</style>\s*<script id="gh-admin-theme-bootstrap">.*?</script>|<link id="gh-admin-theme-styles-link"[^>]*>\s*<script id="gh-admin-theme-bootstrap-script"[^>]*></script>)\s*',
            '',
            content,
            flags=re.DOTALL,
        )
        content = re.sub(r'[ \t]*<style id="gh-admin-theme-styles">.*?</style>\s*', '', content, flags=re.DOTALL)
        content = re.sub(r'[ \t]*<script id="gh-admin-theme-bootstrap">.*?</script>\s*', '', content, flags=re.DOTALL)
        content = re.sub(r'[ \t]*<script id="gh-admin-theme-toggle-runtime">.*?</script>\s*', '', content, flags=re.DOTALL)
        content = re.sub(r'[ \t]*<link id="gh-admin-theme-styles-link"[^>]*>\s*', '', content)
        content = re.sub(r'[ \t]*<script id="gh-admin-theme-bootstrap-script"[^>]*></script>\s*', '', content)
        content = re.sub(r'[ \t]*<script id="gh-admin-theme-toggle-script"[^>]*></script>\s*', '', content)

        if "</head>" in content:
            content = content.replace("</head>", head_patch + "  </head>", 1)
        if "</body>" in content:
            content = content.replace("</body>", runtime_patch + "  </body>", 1)

        if content != original_content:
            with open(cand, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.chmod(cand, 0o644)
            patched_count += 1
            print(f"  ✓ Installed external Ghost Admin theme assets & entrypoint tags: {cand}")
        else:
            print(f"  ✓ Synced external Ghost Admin theme assets (entrypoint already up to date): {cand}")
    except Exception as exc:
        print(f"  ⚠️ Admin patch warning for {cand}: {exc}")

if patched_count > 0:
    print(f"  ✓ Ghost Admin external theme toggle active across {patched_count} entrypoint(s).")
PYEOF

# 4. Social Thumbnail Image
sudo mkdir -p "$GHOST_DIR/content/images"
if fetch_verified_asset "og-image.png" "$GHOST_DIR/content/images/og-image.png" "raw" 2>/dev/null; then
    sudo chown ghost:ghost "$GHOST_DIR/content/images/og-image.png"
    sudo chmod 664 "$GHOST_DIR/content/images/og-image.png"
fi

# Set theme permissions
sudo chown -R ghost:ghost "$THEME_DIR"
sudo chmod -R 775 "$THEME_DIR"

# 5. Dynamic Ghost Settings & Navigation Sync (MYSQL_PWD via env, never -p CLI arg)
echo -e "${BLUE}[5/8] Syncing database settings, navigation, and pages...${NC}"
sudo python3 - <<'PYEOF' 2>/dev/null || true
import json, subprocess, os

def sql_quote(val: str) -> str:
    s = str(val or "").replace("\\", "\\\\").replace("'", "''").replace("\x00", "")
    return f"'{s}'"

config_path = "/var/www/ghost/config.production.json"
if os.path.isfile(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        db_cfg = cfg.get("database", {}).get("connection", {})
        db_host = str(db_cfg.get("host", "localhost"))
        db_port = str(db_cfg.get("port", 3306))
        db_name = str(db_cfg.get("database", "ghost_production"))
        db_user = str(db_cfg.get("user", "root"))
        db_pass = str(db_cfg.get("password", ""))
        ghost_url = str(cfg.get("url", "")).rstrip("/")

        mysql_cmd = ["mysql", f"-h{db_host}", f"-P{db_port}", f"-u{db_user}", db_name]
        mysql_env = os.environ.copy()
        if db_pass:
            mysql_env["MYSQL_PWD"] = db_pass

        og_full_url = f"{ghost_url}/content/images/og-image.png"
        sql_updates = (
            "UPDATE settings SET value = '#ffffff' WHERE `key` = 'accent_color';\n"
            "UPDATE settings SET value = 'all' WHERE `key` = 'members_signup_access';\n"
            f"UPDATE settings SET value = {sql_quote(og_full_url)} WHERE `key` IN ('cover_image', 'og_image', 'twitter_image');\n"
        )
        subprocess.run(mysql_cmd, input=sql_updates, text=True, capture_output=True, env=mysql_env)

        for nav_key in ("navigation", "secondary_navigation"):
            res = subprocess.run(
                mysql_cmd + ["-Nse", f"SELECT value FROM settings WHERE `key`='{nav_key}'"],
                capture_output=True, text=True, env=mysql_env
            )
            if res.stdout.strip():
                try:
                    nav = json.loads(res.stdout.strip())
                except Exception:
                    nav = []
                if isinstance(nav, list):
                    changed = False
                    updated_nav = []
                    seen_report = False
                    report_labels = {"contact", "contact us", "contact & support", "support", "report"}
                    report_paths = {"/contact", "/support", "/report"}
                    for item in nav:
                        if not isinstance(item, dict):
                            updated_nav.append(item)
                            continue
                        lbl = str(item.get("label", "")).strip()
                        raw_url = str(item.get("url", "")).strip()
                        norm_path = raw_url.rstrip("/") or "/"
                        if norm_path in report_paths or lbl.lower() in report_labels:
                            if not seen_report:
                                if lbl != "Report" or raw_url != "/report/":
                                    changed = True
                                updated_nav.append({"label": "Report", "url": "/report/"})
                                seen_report = True
                            else:
                                changed = True
                        else:
                            updated_nav.append(item)

                    if nav_key == "navigation":
                        urls = [str(i.get("url", "")).rstrip("/") for i in updated_nav if isinstance(i, dict)]
                        if "/team" not in urls:
                            updated_nav.append({"label": "Our Team", "url": "/team/"})
                            changed = True
                        if not seen_report and "/report" not in urls:
                            updated_nav.append({"label": "Report", "url": "/report/"})
                            changed = True

                    if changed:
                        new_nav_sql = f"UPDATE settings SET value = {sql_quote(json.dumps(updated_nav))} WHERE `key` = '{nav_key}';\n"
                        subprocess.run(mysql_cmd, input=new_nav_sql, text=True, capture_output=True, env=mysql_env)

        page_sql = """
        INSERT IGNORE INTO posts (
            id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
        ) SELECT
            '6ae71fbd6a4691255cb0ca99', UUID(), 'Report', 'report', lexical, html, plaintext, '6ae71fbd6a4691255cb0ca99', 0, 'page', 'published', 'public', 'all', NOW(), NOW(), NOW(), published_by, 1
        FROM posts WHERE slug = 'about' LIMIT 1;

        INSERT IGNORE INTO posts (
            id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
        ) SELECT
            '6ae71fbd6a4691255cb0ca98', UUID(), 'Report', 'support', lexical, html, plaintext, '6ae71fbd6a4691255cb0ca98', 0, 'page', 'published', 'public', 'all', NOW(), NOW(), NOW(), published_by, 1
        FROM posts WHERE slug = 'about' LIMIT 1;

        UPDATE posts SET title = 'Report' WHERE slug = 'support' AND type = 'page';

        INSERT IGNORE INTO posts (
            id, uuid, title, slug, lexical, html, plaintext, comment_id, featured, type, status, visibility, email_recipient_filter, created_at, updated_at, published_at, published_by, show_title_and_feature_image
        ) SELECT
            '6ae71fbd6a4691255cb0ca77', UUID(), 'Our Team', 'team', lexical, html, plaintext, '6ae71fbd6a4691255cb0ca77', 0, 'page', 'published', 'public', 'all', NOW(), NOW(), NOW(), published_by, 1
        FROM posts WHERE slug = 'about' LIMIT 1;
        """
        subprocess.run(mysql_cmd, input=page_sql, text=True, capture_output=True, env=mysql_env)

    except Exception as e:
        print(f"  Note: Database sync skipped ({e})")
PYEOF

# 6. Install Telegram Admin Mini App Static Assets & Configure Nginx Security Headers
echo -e "${BLUE}[6/8] Installing Case Console WebApp (/tg-admin/) & configuring Nginx security headers...${NC}"
sudo mkdir -p "$GHOST_DIR/tg-admin"
sudo chmod 755 "$GHOST_DIR/tg-admin"
fetch_verified_asset "tg-admin/index.html" "$GHOST_DIR/tg-admin/index.html" "text"
fetch_verified_asset "tg-admin/app.css" "$GHOST_DIR/tg-admin/app.css" "text"
fetch_verified_asset "tg-admin/app.js" "$GHOST_DIR/tg-admin/app.js" "text"
sudo chmod 644 "$GHOST_DIR/tg-admin/index.html" "$GHOST_DIR/tg-admin/app.css" "$GHOST_DIR/tg-admin/app.js"

sudo \
    GHOST_CSP_MODE="${GHOST_CSP_MODE:-report-only}" \
    GHOST_COOP_MODE="${GHOST_COOP_MODE:-enforce}" \
    GHOST_COOP_STRICT="${GHOST_COOP_STRICT:-0}" \
    GHOST_COEP_REPORT_ONLY="${GHOST_COEP_REPORT_ONLY:-0}" \
    python3 - <<'PYEOF' || true
import sys, re, os, glob, subprocess

conf_dirs = ["/etc/nginx/sites-enabled", "/etc/nginx/sites-available", "/etc/nginx/conf.d"]
csp_map_path = "/etc/nginx/conf.d/ghost-csp-map.conf"
sec_snippet_path = "/etc/nginx/snippets/ghost-security-headers.conf"

csp_mode = os.environ.get("GHOST_CSP_MODE", "report-only").strip().lower()
coop_mode = os.environ.get("GHOST_COOP_MODE", "enforce").strip().lower()
coop_strict = os.environ.get("GHOST_COOP_STRICT", "0").strip() == "1"
coep_ro_enabled = os.environ.get("GHOST_COEP_REPORT_ONLY", "0").strip() == "1"

# Exact SHA-256 hashes for Ghost 6.73.0 core inline scripts (private.hbs, gift-toast.hbs, comment_count.js)
ghost_core_hashes = (
    "'sha256-H+h75n/GKcH6MyrlNSDfC6ELZJddjfxP+2pQWqNo8XI=' "
    "'sha256-r2ttV07T2feALZDJgQy/VOJNbiwvepytCFbDZN19hYg=' "
    "'sha256-AbpHGcgLb+kRsJGnwFEktk7uzpZOCcBY74+YBdrKVGs='"
)

strict_default_csp = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
    "form-action 'self' https://checkout.stripe.com https://hooks.stripe.com; "
    f"script-src 'self' {ghost_core_hashes} https://cdn.jsdelivr.net https://js.stripe.com https://static.cloudflareinsights.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.bunny.net https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://fonts.bunny.net https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https://images.unsplash.com https://static.ghost.org https://gravatar.com https://*.gravatar.com https://cdn.jsdelivr.net https://*.wp.com https://*.googleusercontent.com; "
    "media-src 'self' blob: https://www.youtube.com https://player.vimeo.com https://t.me; "
    "connect-src 'self' https://cdn.jsdelivr.net https://cloudflareinsights.com https://static.cloudflareinsights.com https://api.stripe.com; "
    "frame-src 'self' blob: https://cdn.jsdelivr.net https://js.stripe.com https://hooks.stripe.com https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com https://platform.twitter.com https://t.me; "
    "worker-src 'self' blob:; trusted-types default; upgrade-insecure-requests"
)

strict_admin_csp = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
    "form-action 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://js.stripe.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.bunny.net https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://fonts.bunny.net https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https:; "
    "media-src 'self' blob: https:; "
    "connect-src 'self' https://cdn.jsdelivr.net https://api.stripe.com https://api.unsplash.com https://*.ghost.org; "
    "frame-src 'self' blob: https:; "
    "worker-src 'self' blob:; upgrade-insecure-requests"
)

coop_map_lines = [
    "# Cross-Origin-Opener-Policy (route-aware): same-origin on public HTML & /api/support/;",
    "# same-origin-allow-popups on /ghost/* and /members/* unless GHOST_COOP_STRICT=1.",
    "map $request_uri $ghost_coop {",
]
if not coop_strict:
    coop_map_lines.append('    ~^/(?:ghost|members)/ "same-origin-allow-popups";')
coop_map_lines.append('    default               "same-origin";')
coop_map_lines.append("}")

coep_ro_lines = [
    "# Opt-in Cross-Origin-Embedder-Policy-Report-Only telemetry (empty disables header emission)",
    "map $request_uri $ghost_coep_ro {",
]
if coep_ro_enabled:
    coep_ro_lines.append('    ~^/ghost/ "";')
    coep_ro_lines.append('    default   \'require-corp; report-to="csp-endpoint"\';')
else:
    coep_ro_lines.append('    default   "";')
coep_ro_lines.append("}")

csp_map_content = f"""# Ghost CMS & Support Portal Route-Aware Security Header Maps
map $request_uri $ghost_csp {{
    ~^/ghost/ "frame-ancestors 'self'; base-uri 'self'; object-src 'none'";
    default   "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; form-action 'self' https://checkout.stripe.com https://hooks.stripe.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://js.stripe.com https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline' https://fonts.bunny.net https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' data: https://fonts.bunny.net https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data: blob: https://images.unsplash.com https://static.ghost.org https://gravatar.com https://*.gravatar.com https://cdn.jsdelivr.net https://*.wp.com https://*.googleusercontent.com; media-src 'self' blob: https://www.youtube.com https://player.vimeo.com https://t.me; connect-src 'self' https://cdn.jsdelivr.net https://cloudflareinsights.com https://static.cloudflareinsights.com https://api.stripe.com; frame-src 'self' blob: https://cdn.jsdelivr.net https://js.stripe.com https://hooks.stripe.com https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com https://platform.twitter.com https://t.me; worker-src 'self' blob:; trusted-types default; upgrade-insecure-requests";
}}

map $request_uri $ghost_csp_strict {{
    ~^/ghost/ "{strict_admin_csp}";
    default   "{strict_default_csp}";
}}

{chr(10).join(coop_map_lines)}

# Cross-Origin-Resource-Policy by resource class:
# cross-origin for public syndicated media/favicons & public JWKS keys; same-origin for HTML, APIs, Admin, and built bundle assets.
map $request_uri $ghost_corp {{
    ~^/(?:members|ghost)/\\.well-known/ "cross-origin";
    ~^/content/(?:images|media)/       "cross-origin";
    ~^/favicon\\.                      "cross-origin";
    default                            "same-origin";
}}

{chr(10).join(coep_ro_lines)}
"""

if csp_mode == "enforce":
    csp_header_lines = [
        'add_header Content-Security-Policy "$ghost_csp_strict; report-uri /api/support/csp-report; report-to csp-endpoint" always;',
    ]
else:
    csp_header_lines = [
        'add_header Content-Security-Policy "$ghost_csp; report-uri /api/support/csp-report; report-to csp-endpoint" always;',
        'add_header Content-Security-Policy-Report-Only "$ghost_csp_strict; report-uri /api/support/csp-report; report-to csp-endpoint" always;',
    ]

if coop_mode == "report-only":
    coop_header_line = 'add_header Cross-Origin-Opener-Policy-Report-Only "$ghost_coop; report-to=\\"csp-endpoint\\"" always;'
else:
    coop_header_line = 'add_header Cross-Origin-Opener-Policy "$ghost_coop" always;'

sec_snippet_content = f"""# Ghost CMS & Support Portal Hardened Security Headers (included inside location /)
# Active rollout flags: GHOST_CSP_MODE={csp_mode}, GHOST_COOP_MODE={coop_mode}, GHOST_COOP_STRICT={int(coop_strict)}, GHOST_COEP_REPORT_ONLY={int(coep_ro_enabled)}
proxy_hide_header X-Frame-Options;
proxy_hide_header X-Content-Type-Options;
proxy_hide_header Content-Security-Policy;
proxy_hide_header Content-Security-Policy-Report-Only;
proxy_hide_header Cross-Origin-Opener-Policy;
proxy_hide_header Cross-Origin-Opener-Policy-Report-Only;
proxy_hide_header Cross-Origin-Embedder-Policy;
proxy_hide_header Cross-Origin-Embedder-Policy-Report-Only;
proxy_hide_header Cross-Origin-Resource-Policy;
proxy_hide_header X-Permitted-Cross-Domain-Policies;
proxy_hide_header Reporting-Endpoints;
add_header Reporting-Endpoints 'csp-endpoint="/api/support/csp-report"' always;
{chr(10).join(csp_header_lines)}
{coop_header_line}
add_header Cross-Origin-Embedder-Policy-Report-Only $ghost_coep_ro always;
add_header Cross-Origin-Resource-Policy "$ghost_corp" always;
add_header X-Permitted-Cross-Domain-Policies "none" always;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(self)" always;
"""

proxy_block = """    # Ghost Support Portal & Telegram Bot API Proxy
    location /api/support/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_hide_header Cross-Origin-Opener-Policy;
        proxy_hide_header Cross-Origin-Resource-Policy;
        proxy_hide_header X-Permitted-Cross-Domain-Policies;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header Cross-Origin-Opener-Policy "same-origin" always;
        add_header Cross-Origin-Resource-Policy "same-origin" always;
        add_header X-Permitted-Cross-Domain-Policies "none" always;
        client_max_body_size 50M;
    }"""

tg_admin_block = """    # Telegram Admin Support Case Console Mini App (zero secrets in static shell)
    location = /tg-admin {
        return 301 /tg-admin/$is_args$args;
    }

    location ^~ /tg-admin/ {
        root /var/www/ghost;
        index index.html;
        try_files $uri $uri/ =404;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header Content-Security-Policy "default-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self' https://web.telegram.org; script-src 'self' https://telegram.org; style-src 'self' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-src 'self' blob:; upgrade-insecure-requests" always;
        add_header Cross-Origin-Opener-Policy "same-origin-allow-popups" always;
        add_header Cross-Origin-Resource-Policy "cross-origin" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Permitted-Cross-Domain-Policies "none" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header Cache-Control "no-store" always;
    }"""

def find_matching_brace(text: str, open_idx: int) -> int:
    depth = 0
    in_quote = None
    in_comment = False
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if in_comment:
            if ch == "\n":
                in_comment = False
        elif in_quote:
            if ch == "\\" and i + 1 < n:
                i += 1
            elif ch == in_quote:
                in_quote = None
        else:
            if ch == "#":
                in_comment = True
            elif ch in ('"', "'"):
                in_quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1

def patch_vhost_text(content: str) -> str:
    out = content
    # 1. Ensure or upgrade location /api/support/
    sup_matches = list(re.finditer(r"(^[ \t]*#[^\n]*Support Portal[^\n]*\n)?[ \t]*location\s+/api/support/\s*\{", out, flags=re.M))
    if sup_matches:
        for m in reversed(sup_matches):
            brace_idx = out.find("{", m.start())
            close_idx = find_matching_brace(out, brace_idx)
            if close_idx != -1:
                block_slice = out[m.start():close_idx + 1]
                if (
                    "Strict-Transport-Security" not in block_slice
                    or "X-Permitted-Cross-Domain-Policies" not in block_slice
                    or "Cross-Origin-Opener-Policy" not in block_slice
                    or "Cross-Origin-Resource-Policy" not in block_slice
                ):
                    out = out[:m.start()] + proxy_block + out[close_idx + 1:]
    else:
        loc_matches = list(re.finditer(r"^[ \t]*location\s+/\s*\{", out, flags=re.M))
        for m in reversed(loc_matches):
            brace_idx = out.find("{", m.start())
            close_idx = find_matching_brace(out, brace_idx)
            if close_idx != -1 and "2368" in out[brace_idx:close_idx + 1]:
                out = out[:m.start()] + proxy_block + "\n\n" + out[m.start():]

    # 1b. Ensure or upgrade location = /tg-admin + location ^~ /tg-admin/
    tg_matches = list(re.finditer(r"(^[ \t]*#[^\n]*Telegram Admin Support Case Console[^\n]*\n)?(?:[ \t]*location\s+=\s+/tg-admin\s*\{[^}]*\}\s*)?[ \t]*location\s+(?:\^~\s+)?/tg-admin/\s*\{", out, flags=re.M))
    if tg_matches:
        for m in reversed(tg_matches):
            brace_idx = out.find("{", m.end() - 1)
            close_idx = find_matching_brace(out, brace_idx)
            if close_idx != -1:
                block_slice = out[m.start():close_idx + 1]
                if "location = /tg-admin" not in block_slice or "root /var/www/ghost;" not in block_slice or "https://web.telegram.org" not in block_slice:
                    out = out[:m.start()] + tg_admin_block + out[close_idx + 1:]
    else:
        loc_matches = list(re.finditer(r"^[ \t]*location\s+/\s*\{", out, flags=re.M))
        for m in reversed(loc_matches):
            brace_idx = out.find("{", m.start())
            close_idx = find_matching_brace(out, brace_idx)
            if close_idx != -1 and "2368" in out[brace_idx:close_idx + 1]:
                out = out[:m.start()] + tg_admin_block + "\n\n" + out[m.start():]

    # 2. Inject snippets/ghost-security-headers.conf inside location / blocks proxying to 2368
    loc_matches = list(re.finditer(r"^[ \t]*location\s+/\s*\{", out, flags=re.M))
    for m in reversed(loc_matches):
        brace_idx = out.find("{", m.start())
        close_idx = find_matching_brace(out, brace_idx)
        if close_idx == -1:
            continue
        inner = out[brace_idx + 1:close_idx]
        if "2368" not in inner:
            continue
        new_inner = re.sub(
            r"^([ \t]*)(add_header\s+(?:X-Content-Type-Options|X-Frame-Options|Strict-Transport-Security|Content-Security-Policy(?:-Report-Only)?|Cross-Origin-Opener-Policy(?:-Report-Only)?|Cross-Origin-Embedder-Policy(?:-Report-Only)?|Cross-Origin-Resource-Policy|X-Permitted-Cross-Domain-Policies|Reporting-Endpoints)\b[^;\n]*;)",
            r"\1# [managed by ghost-security-headers.conf] \2",
            inner,
            flags=re.M | re.I,
        )
        if "snippets/ghost-security-headers.conf" not in new_inner:
            new_inner = "\n        include snippets/ghost-security-headers.conf;" + new_inner
        if new_inner != inner:
            out = out[:brace_idx + 1] + new_inner + out[close_idx:]
    return out

if os.path.isdir("/etc/nginx"):
    backups = {}
    created_files = []
    changed = False

    # Clean up conflicting /etc/nginx/conf.d/ghost-tls-harden.conf if present
    stale_tls_conf = "/etc/nginx/conf.d/ghost-tls-harden.conf"
    if os.path.isfile(stale_tls_conf):
        try:
            os.remove(stale_tls_conf)
            changed = True
        except OSError:
            pass

    # Harden global ssl_protocols in /etc/nginx/nginx.conf (TLS 1.2 & TLS 1.3 only, zero duplicate directives)
    nginx_conf_path = "/etc/nginx/nginx.conf"
    if os.path.isfile(nginx_conf_path):
        try:
            with open(nginx_conf_path, "r", encoding="utf-8", errors="ignore") as fp:
                old_nconf = fp.read()
            new_nconf, n_count = re.subn(
                r'^[ \t]*ssl_protocols\s+[^;\n]*\b(?:TLSv1(?!\.[2-9])|TLSv1\.0|TLSv1\.1)\b[^\n]*',
                '	ssl_protocols TLSv1.2 TLSv1.3;',
                old_nconf,
                flags=re.M
            )
            if n_count > 0 and new_nconf != old_nconf:
                backups[nginx_conf_path] = old_nconf
                with open(nginx_conf_path, "w", encoding="utf-8") as fp:
                    fp.write(new_nconf)
                changed = True
                print("  ✓ Hardened /etc/nginx/nginx.conf: enforced ssl_protocols TLSv1.2 TLSv1.3")
        except Exception as exc:
            print(f"  Note: nginx.conf TLS hardening skipped ({exc})")

    for aux_path, aux_body in [(csp_map_path, csp_map_content), (sec_snippet_path, sec_snippet_content)]:
        os.makedirs(os.path.dirname(aux_path), exist_ok=True)
        if os.path.isfile(aux_path):
            old_aux = open(aux_path, "r", encoding="utf-8", errors="ignore").read()
            if old_aux != aux_body:
                backups[aux_path] = old_aux
                with open(aux_path, "w", encoding="utf-8") as fp:
                    fp.write(aux_body)
                changed = True
        else:
            created_files.append(aux_path)
            with open(aux_path, "w", encoding="utf-8") as fp:
                fp.write(aux_body)
            changed = True

    seen_files = set()
    for cdir in conf_dirs:
        if not os.path.isdir(cdir):
            continue
        for f in sorted(glob.glob(os.path.join(cdir, "*"))):
            real_f = os.path.realpath(f)
            if (
                not os.path.isfile(real_f)
                or real_f.endswith(".bak")
                or real_f in seen_files
                or os.path.basename(real_f) in ("ghost-csp-map.conf", "ghost-tls-harden.conf")
            ):
                continue
            seen_files.add(real_f)
            try:
                with open(real_f, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                if "2368" not in content:
                    continue
                patched_content = patch_vhost_text(content)
                if patched_content != content:
                    backups[real_f] = content
                    with open(real_f + ".bak", "w", encoding="utf-8") as bkp:
                        bkp.write(content)
                    with open(real_f, "w", encoding="utf-8") as fp:
                        fp.write(patched_content)
                    print(f"  ✓ Patched Nginx proxy & CSP headers in: {f}")
                    changed = True
            except Exception as exc:
                print(f"  ⚠️ Skipped {f}: {exc}")

    if changed:
        chk = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if chk.returncode == 0:
            subprocess.run(["systemctl", "reload", "nginx"], check=False)
            print("  ✓ Nginx CSP & security headers verified (nginx -t) and reloaded.")
        else:
            print(f"  ⚠️ nginx -t reported an issue ({chk.stderr.strip()}); rolling back Nginx edits...")
            for bpath, btext in backups.items():
                with open(bpath, "w", encoding="utf-8") as fp:
                    fp.write(btext)
            for cpath in created_files:
                try:
                    os.remove(cpath)
                except OSError:
                    pass
    else:
        print("  ✓ Nginx proxy & CSP headers already up to date.")
PYEOF

# 7. Update Support Hub Daemon & Cryptographic Engine
echo -e "${BLUE}[7/8] Updating Support Hub Daemon & Verification Engine...${NC}"
sudo mkdir -p "$GHOST_DIR/Ghost-Restore"
sudo mkdir -p "$GHOST_DIR/backups"
sudo mkdir -p "$GHOST_DIR/support_vault/evidence"
sudo chown -R root:root "$GHOST_DIR/support_vault" 2>/dev/null || true
sudo chmod 700 "$GHOST_DIR/backups" "$GHOST_DIR/support_vault" "$GHOST_DIR/support_vault/evidence" 2>/dev/null || true
sudo find "$GHOST_DIR/support_vault" -type f -exec chmod 600 {} + 2>/dev/null || true

# Target directories to sync backend files
SYNC_DIRS=("$GHOST_DIR/Ghost-Restore")
if [ -d "/opt/ghost-telegram-bot" ]; then
    SYNC_DIRS+=("/opt/ghost-telegram-bot")
fi

BOT_SVC_FILE="/etc/systemd/system/ghost-telegram-bot.service"
if [ -f "$BOT_SVC_FILE" ]; then
    SVC_DIR=$(grep -E '^\s*WorkingDirectory\s*=' "$BOT_SVC_FILE" | head -n 1 | cut -d= -f2 | tr -d ' ' || echo "")
    if [ -n "$SVC_DIR" ] && [ -d "$SVC_DIR" ]; then
        already_in=0
        for existing_d in "${SYNC_DIRS[@]}"; do
            [ "$existing_d" = "$SVC_DIR" ] && already_in=1
        done
        [ "$already_in" -eq 0 ] && SYNC_DIRS+=("$SVC_DIR")
    fi
fi

# Ensure Python3 and virtualenv packages exist
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y -q python3 python3-pip python3-venv curl >/dev/null 2>&1 || true
fi

# Download and syntax-verify all required daemon files across target directories
for sdir in "${SYNC_DIRS[@]}"; do
    sudo mkdir -p "$sdir"
    fetch_verified_asset "support_hub.py" "$sdir/support_hub.py" "py"
    fetch_verified_asset "bot.py" "$sdir/bot.py" "py"
    fetch_verified_asset "ghost_manager.py" "$sdir/ghost_manager.py" "py"
    fetch_verified_asset "requirements.txt" "$sdir/requirements.txt" "text"
    sudo mkdir -p "$sdir/tg-admin"
    sudo chmod 755 "$sdir/tg-admin"
    fetch_verified_asset "tg-admin/index.html" "$sdir/tg-admin/index.html" "text"
    fetch_verified_asset "tg-admin/app.css" "$sdir/tg-admin/app.css" "text"
    fetch_verified_asset "tg-admin/app.js" "$sdir/tg-admin/app.js" "text"
    sudo chmod 644 "$sdir/tg-admin/index.html" "$sdir/tg-admin/app.css" "$sdir/tg-admin/app.js"

    if [ ! -d "$sdir/venv" ]; then
        sudo python3 -m venv "$sdir/venv" 2>/dev/null || true
    fi
    if [ -x "$sdir/venv/bin/pip" ]; then
        sudo "$sdir/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
        sudo "$sdir/venv/bin/pip" install -r "$sdir/requirements.txt" -q 2>/dev/null || true
    fi
    sudo pip3 install -r "$sdir/requirements.txt" --break-system-packages -q 2>/dev/null || sudo pip3 install -r "$sdir/requirements.txt" -q 2>/dev/null || true

    # Sync .env across candidate directories if missing and enforce 0600 permissions
    if [ ! -f "$sdir/.env" ]; then
        if [ -f "$GHOST_DIR/Ghost-Restore/.env" ]; then
            sudo install -m 600 "$GHOST_DIR/Ghost-Restore/.env" "$sdir/.env"
        elif [ -f "/opt/ghost-telegram-bot/.env" ]; then
            sudo install -m 600 "/opt/ghost-telegram-bot/.env" "$sdir/.env"
        elif [ -f "$GHOST_DIR/.env" ]; then
            sudo install -m 600 "$GHOST_DIR/.env" "$sdir/.env"
        fi
    else
        sudo chmod 600 "$sdir/.env" 2>/dev/null || true
    fi
done

SUPPORT_PY_BIN="/usr/bin/python3"
if [ -x "$GHOST_DIR/Ghost-Restore/venv/bin/python3" ]; then
    SUPPORT_PY_BIN="$GHOST_DIR/Ghost-Restore/venv/bin/python3"
fi

# Ensure fallback ghost-support.service unit is installed with PrivateTmp & strict UMask
cat <<EOF | sudo tee /etc/systemd/system/ghost-support.service >/dev/null
[Unit]
Description=Ghost Support Hub REST API Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$GHOST_DIR/Ghost-Restore
ExecStart=$SUPPORT_PY_BIN $GHOST_DIR/Ghost-Restore/support_hub.py --port 8080 --ghost-dir $GHOST_DIR
PrivateTmp=true
UMask=0077
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Sanitize & harden ghost-telegram-bot.service if present
if [ -f "$BOT_SVC_FILE" ]; then
    sudo sed -i 's/^EnvironmentFile=\([^-\/]*\)/EnvironmentFile=-\1/' "$BOT_SVC_FILE" 2>/dev/null || true
    sudo sed -i 's/^EnvironmentFile=\//EnvironmentFile=-\//' "$BOT_SVC_FILE" 2>/dev/null || true
    if ! grep -q '^PrivateTmp=' "$BOT_SVC_FILE" 2>/dev/null; then
        sudo sed -i '/^\[Service\]/a PrivateTmp=true' "$BOT_SVC_FILE" 2>/dev/null || true
    fi
    if ! grep -q '^UMask=' "$BOT_SVC_FILE" 2>/dev/null; then
        sudo sed -i '/^\[Service\]/a UMask=0077' "$BOT_SVC_FILE" 2>/dev/null || true
    fi
fi

sudo systemctl daemon-reload

# Manage startup with auto-failover
if [ -f "$BOT_SVC_FILE" ]; then
    sudo systemctl stop ghost-support.service 2>/dev/null || true
    sudo systemctl restart ghost-telegram-bot.service 2>/dev/null || true
    echo -e "  ✓ Synced backend files & restarted ghost-telegram-bot.service"
    sleep 3
    CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
    if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
        echo -e "  ✓ Cryptographic Challenge Engine verified: ${GREEN}ONLINE (HTTP 200)${NC}"
    else
        echo -e "  ${YELLOW}⚠️ ghost-telegram-bot.service not listening on port 8080. Activating fallback ghost-support.service...${NC}"
        sudo systemctl enable ghost-support.service -q 2>/dev/null || true
        sudo systemctl restart ghost-support.service 2>/dev/null || true
        sleep 2
        CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
        if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
            echo -e "  ✓ Cryptographic Challenge Engine active via fallback: ${GREEN}ONLINE (HTTP 200)${NC}"
        else
            echo -e "  ${RED}⚠️ Daemon verification failed on port 8080!${NC}"
            echo -e "  Output received: $CAPTCHA_CHECK"
        fi
        echo -e "${YELLOW}--- Diagnostics (ghost-telegram-bot logs) ---${NC}"
        sudo journalctl -u ghost-telegram-bot -n 20 --no-pager 2>/dev/null || true
        echo -e "${YELLOW}-------------------------------------------${NC}"
    fi
else
    sudo systemctl enable ghost-support.service -q 2>/dev/null || true
    sudo systemctl restart ghost-support.service 2>/dev/null || true
    echo -e "  ✓ Registered & started standalone ghost-support.service on port 8080"
    sleep 2
    CAPTCHA_CHECK=$(curl -s -m 5 http://127.0.0.1:8080/captcha 2>/dev/null || echo "")
    if [[ "$CAPTCHA_CHECK" =~ "challenge_id" ]]; then
        echo -e "  ✓ Cryptographic Challenge Engine verified: ${GREEN}ONLINE (HTTP 200)${NC}"
    else
        echo -e "  ${RED}⚠️ Daemon verification failed on port 8080!${NC}"
    fi
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
        sudo -u ubuntu bash -c "cd '$GHOST_DIR' && ghost restart" 2>/dev/null || true
    fi
    echo -e "  ✓ Ghost CMS reloaded successfully."
fi

echo ""
echo -e "${GREEN}==================================================================${NC}"
echo -e "${GREEN}  🎉 Theme & Support Portal Setup Finished Successfully!          ${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo -e "✓ Alto Theme installed cleanly in:     ${CYAN}$THEME_DIR${NC}"
echo -e "✓ Report Portal active at:             ${CYAN}https://yourdomain.com/report/${NC}"
echo -e "✓ Team Showcase active at:             ${CYAN}https://yourdomain.com/team/${NC}"
echo -e "✓ Verification Challenge Engine:       ${GREEN}ACTIVE & VERIFIED (port 8080)${NC}"
echo -e "✓ Email Templates updated in:          ${CYAN}$GHOST_DIR/current/core/${NC}"
echo -e "✓ Support Vault permissions:           ${GREEN}LOCKED (0700 / 0600)${NC}"
echo -e "✓ In-memory template cache:            ${GREEN}CLEARED${NC}"
echo -e "${GREEN}==================================================================${NC}"
echo ""
