import os
import shutil
import zipfile
import sys
sys.stdout.reconfigure(encoding='utf-8')

THEME_SRC = r"C:\Users\LordgrimxDJay\.gemini\antigravity\scratch\ghost-blog\content\themes\alto"
GHOST_CORE = r"C:\Users\LordgrimxDJay\.gemini\antigravity\scratch\ghost-blog\current\core"
GHOST_CORE_SERVER = r"C:\Users\LordgrimxDJay\.gemini\antigravity\scratch\ghost-blog\current\core\server"
REPO_DIR = r"C:\Users\LordgrimxDJay\.gemini\antigravity\scratch\Ghost-Restore"
EMAIL_TEMPLATES_SRC = os.path.join(REPO_DIR, "email-templates")

THEME_ZIP_DST = os.path.join(REPO_DIR, "alto-theme-latest.zip")
EMAIL_ZIP_DST = os.path.join(REPO_DIR, "email-templates.zip")

# Mapping of local template file -> target in ghost core
SYNC_MAP = {
    # Members
    os.path.join("members", "signin.js"): os.path.join("services", "members", "emails", "signin.js"),
    os.path.join("members", "signup.js"): os.path.join("services", "members", "emails", "signup.js"),
    os.path.join("members", "signup-paid.js"): os.path.join("services", "members", "emails", "signup-paid.js"),
    os.path.join("members", "subscribe.js"): os.path.join("services", "members", "emails", "subscribe.js"),
    os.path.join("members", "update-email.js"): os.path.join("services", "members", "emails", "update-email.js"),
    # Mail
    os.path.join("mail", "invite-user.html"): os.path.join("lib", "mail", "templates", "invite-user.html"),
    os.path.join("mail", "reset-password.html"): os.path.join("lib", "mail", "templates", "reset-password.html"),
    os.path.join("mail", "welcome.html"): os.path.join("lib", "mail", "templates", "welcome.html"),
    os.path.join("mail", "test.html"): os.path.join("lib", "mail", "templates", "test.html"),
    os.path.join("mail", "invite-user-by-api-key.html"): os.path.join("lib", "mail", "templates", "invite-user-by-api-key.html"),
    os.path.join("mail", "notification.html"): os.path.join("lib", "mail", "templates", "notification.html"),
    # Newsletter
    os.path.join("newsletter", "email-wrapper.hbs"): os.path.join("lib", "email-rendering", "partials", "email-wrapper.hbs"),
    os.path.join("newsletter", "styles.hbs"): os.path.join("services", "email-service", "email-templates", "partials", "styles.hbs"),
    os.path.join("newsletter", "template.hbs"): os.path.join("services", "email-service", "email-templates", "template.hbs"),
    os.path.join("newsletter", "verify-email.js"): os.path.join("services", "newsletters", "emails", "verify-email.js"),
    # Comments
    os.path.join("comments", "new-comment.hbs"): os.path.join("services", "comments", "email-templates", "new-comment.hbs"),
    os.path.join("comments", "new-comment-reply.hbs"): os.path.join("services", "comments", "email-templates", "new-comment-reply.hbs"),
    os.path.join("comments", "report.hbs"): os.path.join("services", "comments", "email-templates", "report.hbs"),
    # Staff
    os.path.join("staff", "styles.hbs"): os.path.join("services", "staff", "email-templates", "partials", "styles.hbs"),
    os.path.join("staff", "preview.hbs"): os.path.join("services", "staff", "email-templates", "partials", "preview.hbs"),
    os.path.join("staff", "donation.hbs"): os.path.join("services", "staff", "email-templates", "donation.hbs"),
    os.path.join("staff", "gift.hbs"): os.path.join("services", "staff", "email-templates", "gift.hbs"),
    os.path.join("staff", "new-free-signup.hbs"): os.path.join("services", "staff", "email-templates", "new-free-signup.hbs"),
    os.path.join("staff", "new-gift-subscription.hbs"): os.path.join("services", "staff", "email-templates", "new-gift-subscription.hbs"),
    os.path.join("staff", "new-milestone-received.hbs"): os.path.join("services", "staff", "email-templates", "new-milestone-received.hbs"),
    os.path.join("staff", "new-paid-cancellation.hbs"): os.path.join("services", "staff", "email-templates", "new-paid-cancellation.hbs"),
    os.path.join("staff", "new-paid-started.hbs"): os.path.join("services", "staff", "email-templates", "new-paid-started.hbs"),
    os.path.join("staff", "recommendation-received.hbs"): os.path.join("services", "staff", "email-templates", "recommendation-received.hbs"),
    # Gifts
    os.path.join("gifts", "gift-delivery.hbs"): os.path.join("services", "gifts", "email-templates", "gift-delivery.hbs"),
    os.path.join("gifts", "gift-purchase-confirmation.hbs"): os.path.join("services", "gifts", "email-templates", "gift-purchase-confirmation.hbs"),
    os.path.join("gifts", "gift-reminder.hbs"): os.path.join("services", "gifts", "email-templates", "gift-reminder.hbs"),
    os.path.join("gifts", "gift-buyer-notice-layout.hbs"): os.path.join("services", "gifts", "email-templates", "gift-buyer-notice-layout.hbs"),
    os.path.join("gifts", "gift-delivery-failure.hbs"): os.path.join("services", "gifts", "email-templates", "gift-delivery-failure.hbs"),
    os.path.join("gifts", "gift-sent-confirmation.hbs"): os.path.join("services", "gifts", "email-templates", "gift-sent-confirmation.hbs"),
    # Member Welcome Emails
    os.path.join("welcome", "wrapper.hbs"): os.path.join("services", "member-welcome-emails", "email-templates", "wrapper.hbs"),
}

def sync_editable_email_templates_to_core():
    print(f"[*] Syncing editable email templates from {EMAIL_TEMPLATES_SRC} into Ghost core...")
    if not os.path.exists(EMAIL_TEMPLATES_SRC):
        print("  ! email-templates directory not found, skipping sync.")
        return

    count = 0
    for src_rel, dst_rel in SYNC_MAP.items():
        src_path = os.path.join(EMAIL_TEMPLATES_SRC, src_rel)
        dst_path = os.path.join(GHOST_CORE_SERVER, dst_rel)
        if os.path.exists(src_path):
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            count += 1
    print(f"  ✓ Synchronized {count} email template files from repo into Ghost core.")

    author_model_src = os.path.join(REPO_DIR, "models", "author.js")
    author_model_dst = os.path.join(GHOST_CORE_SERVER, "models", "author.js")
    if os.path.exists(author_model_src):
        os.makedirs(os.path.dirname(author_model_dst), exist_ok=True)
        shutil.copy2(author_model_src, author_model_dst)
        print("  ✓ Synchronized models/author.js into Ghost core.")


def sync_repo_theme_files_to_theme_src():
    print(f"[*] Syncing updated repo theme templates & scripts into {THEME_SRC}...")
    theme_sync_map = {
        "page-support.hbs": ["page-support.hbs"],
        "page-about.hbs": ["page-about.hbs"],
        "page-team.hbs": ["page-team.hbs"],
        "team.json": [os.path.join("assets", "data", "team.json")],
        "portal-theme.js": [
            os.path.join("assets", "built", "portal-theme.js"),
            os.path.join("assets", "js", "portal-theme.js"),
        ],
        "team-page.js": [
            os.path.join("assets", "built", "team-page.js"),
            os.path.join("assets", "js", "team-page.js"),
        ],
    }
    synced = 0
    for repo_rel, theme_rels in theme_sync_map.items():
        src_path = os.path.join(REPO_DIR, repo_rel)
        if not os.path.exists(src_path):
            continue
        for idx, dst_rel in enumerate(theme_rels):
            dst_path = os.path.join(THEME_SRC, dst_rel)
            # Always write primary target (idx == 0); write secondary source copy if parent exists
            if idx == 0 or os.path.exists(dst_path):
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                synced += 1
    print(f"  ✓ Synchronized {synced} theme asset target(s) into {THEME_SRC}.")


def package_theme():
    print(f"[*] Packaging Alto theme from {THEME_SRC}...")
    with zipfile.ZipFile(THEME_ZIP_DST, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(THEME_SRC):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', 'scratch', '.github']]
            for file in sorted(files):
                if file.startswith('.') or file.endswith('.pyc'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, THEME_SRC)
                clean_name = rel_path.replace('\\', '/')
                zf.write(full_path, clean_name)
    print(f"✓ Theme package created: {THEME_ZIP_DST} ({os.path.getsize(THEME_ZIP_DST)} bytes)")

def package_emails():
    print(f"[*] Packaging Email Templates and Safe Core Overrides from {EMAIL_TEMPLATES_SRC}...")
    with zipfile.ZipFile(EMAIL_ZIP_DST, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Pack all 35 redesigned templates from email-templates/
        for src_rel, dst_rel in sorted(SYNC_MAP.items()):
            src_path = os.path.join(EMAIL_TEMPLATES_SRC, src_rel)
            if os.path.exists(src_path):
                clean_name = dst_rel.replace('\\', '/')
                zf.write(src_path, clean_name)
                print(f"  + {clean_name}")
            else:
                print(f"  ! WARNING: Missing source template {src_path}")

        # Pack models/author.js (allows team members with 0 posts to appear on /team/)
        author_path = os.path.join(REPO_DIR, "models", "author.js")
        if os.path.exists(author_path):
            zf.write(author_path, "models/author.js")
            print("  + models/author.js")

    print(f"✓ Email & Core package created: {EMAIL_ZIP_DST} ({os.path.getsize(EMAIL_ZIP_DST)} bytes)")

if __name__ == "__main__":
    sync_editable_email_templates_to_core()
    sync_repo_theme_files_to_theme_src()
    package_theme()
    package_emails()
