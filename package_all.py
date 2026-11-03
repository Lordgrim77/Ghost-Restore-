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

def sync_editable_email_templates_to_core():
    print(f"[*] Syncing editable email templates from {EMAIL_TEMPLATES_SRC} into Ghost core...")
    if not os.path.exists(EMAIL_TEMPLATES_SRC):
        print("  ! email-templates directory not found, skipping sync.")
        return

    # Mapping of local editable file -> target in ghost core
    sync_map = {
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

    count = 0
    for src_rel, dst_rel in sync_map.items():
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

def package_theme():
    print(f"[*] Packaging Alto theme from {THEME_SRC}...")
    with zipfile.ZipFile(THEME_ZIP_DST, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(THEME_SRC):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules']]
            for file in sorted(files):
                if file.startswith('.') or file.endswith('.pyc'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, THEME_SRC)
                clean_name = rel_path.replace('\\', '/')
                zf.write(full_path, clean_name)
    print(f"✓ Theme package created: {THEME_ZIP_DST} ({os.path.getsize(THEME_ZIP_DST)} bytes)")

def package_emails():
    print(f"[*] Packaging Email Templates and Core Overrides from {GHOST_CORE}...")
    files_to_pack = [
        # Mail
        "lib/mail/ghost-mailer.js",
        "lib/mail/email-content-generator.js",
        "lib/mail/index.js",
        "lib/mail/templates/invite-user.html",
        "lib/mail/templates/reset-password.html",
        "lib/mail/templates/welcome.html",
        "lib/mail/templates/test.html",
        "lib/mail/templates/invite-user-by-api-key.html",
        "lib/mail/templates/notification.html",
        # Members
        "services/members/api.js",
        "services/members/emails/signin.js",
        "services/members/emails/signup.js",
        "services/members/emails/signup-paid.js",
        "services/members/emails/subscribe.js",
        "services/members/emails/update-email.js",
        # Newsletter
        "services/newsletters/emails/verify-email.js",
        "services/settings/emails/verify-email.js",
        "services/email-service/email-renderer.js",
        "services/email-service/email-templates/template.hbs",
        "services/email-service/email-templates/partials/styles.hbs",
        "lib/email-rendering/partials/email-wrapper.hbs",
        # Comments
        "services/comments/comments-service-emails.js",
        "services/comments/email-templates/new-comment.hbs",
        "services/comments/email-templates/new-comment-reply.hbs",
        "services/comments/email-templates/report.hbs",
        # Staff
        "services/staff/staff-service-emails.js",
        "services/staff/email-templates/partials/styles.hbs",
        "services/staff/email-templates/partials/preview.hbs",
        "services/staff/email-templates/donation.hbs",
        "services/staff/email-templates/gift.hbs",
        "services/staff/email-templates/new-free-signup.hbs",
        "services/staff/email-templates/new-gift-subscription.hbs",
        "services/staff/email-templates/new-milestone-received.hbs",
        "services/staff/email-templates/new-paid-cancellation.hbs",
        "services/staff/email-templates/new-paid-started.hbs",
        "services/staff/email-templates/recommendation-received.hbs",
        # Gifts
        "services/gifts/index.js",
        "services/gifts/gift-email-service.js",
        "services/gifts/email-templates/gift-delivery.hbs",
        "services/gifts/email-templates/gift-purchase-confirmation.hbs",
        "services/gifts/email-templates/gift-reminder.hbs",
        "services/gifts/email-templates/gift-buyer-notice-layout.hbs",
        "services/gifts/email-templates/gift-delivery-failure.hbs",
        "services/gifts/email-templates/gift-sent-confirmation.hbs",
        # Member Welcome
        "services/member-welcome-emails/service.js",
        "services/member-welcome-emails/member-welcome-email-renderer.js",
        "services/member-welcome-emails/email-templates/wrapper.hbs",
        # Meta & Social
        "frontend/meta/og-image.js",
        "frontend/meta/twitter-image.js",
        # Core Models (Allow staff/admins with 0 posts on team page)
        "models/author.js",
    ]

    with zipfile.ZipFile(EMAIL_ZIP_DST, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel in files_to_pack:
            if rel.startswith("frontend/"):
                full_path = os.path.join(GHOST_CORE, rel.replace('/', os.sep))
            else:
                full_path = os.path.join(GHOST_CORE_SERVER, rel.replace('/', os.sep))
            if os.path.exists(full_path):
                clean_name = rel.replace('\\', '/')
                zf.write(full_path, clean_name)
                print(f"  + {clean_name}")
            else:
                print(f"  ! WARNING: Missing {full_path}")
    print(f"✓ Email & Core package created: {EMAIL_ZIP_DST} ({os.path.getsize(EMAIL_ZIP_DST)} bytes)")

if __name__ == "__main__":
    sync_editable_email_templates_to_core()
    package_theme()
    package_emails()
