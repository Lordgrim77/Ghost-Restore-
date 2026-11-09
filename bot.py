from __future__ import annotations
#!/usr/bin/env python3
"""
Ghost Telegram Bot
Interactive Telegram Bot for 1-Click Ghost CMS Backup and Restore.
Author: Lordgrim77
Repository: https://github.com/Lordgrim77/Ghost-Restore-
"""

import os
import sys
import shutil
import socket
import ipaddress
import zipfile
import logging
import asyncio
import datetime
import urllib.request
import urllib.parse
import re
from typing import Optional, Dict, Any, List
from pathlib import Path

# Safe multi-location environment loading (excludes untrusted cwd to prevent .env hijacking)
def load_all_environments() -> List[str]:
    """Load configuration from trusted candidate .env files across installation directories."""
    candidates = [
        os.getenv("GHOST_ENV_FILE", ""),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        "/var/www/ghost/Ghost-Restore/.env",
        "/opt/ghost-telegram-bot/.env",
        "/var/www/ghost/.env",
    ]
    seen = set()
    valid_paths = []
    for c in candidates:
        if c and not os.path.islink(c) and os.path.isfile(c):
            real = os.path.realpath(c)
            if real not in seen:
                seen.add(real)
                valid_paths.append(real)

    try:
        from dotenv import load_dotenv
        for vp in valid_paths:
            load_dotenv(vp, override=False)
    except (ImportError, ModuleNotFoundError):
        pass

    # Pure Python fallback parser to ensure values are loaded even without python-dotenv
    for vp in valid_paths:
        try:
            with open(vp, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

    return valid_paths

_loaded_env_files = load_all_environments()

# Safe telegram imports (falls back gracefully if python-telegram-bot is missing)
try:
    from telegram import (
        Update,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
    )
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    HAS_TELEGRAM = True
except (ImportError, ModuleNotFoundError):
    HAS_TELEGRAM = False
    Update = Any  # type: ignore
    InlineKeyboardButton = Any  # type: ignore
    InlineKeyboardMarkup = Any  # type: ignore
    class ParseMode:  # type: ignore
        HTML = "HTML"
        MARKDOWN = "Markdown"
        MARKDOWN_V2 = "MarkdownV2"
    Application = Any  # type: ignore
    ApplicationBuilder = Any  # type: ignore
    CommandHandler = Any  # type: ignore
    CallbackQueryHandler = Any  # type: ignore
    MessageHandler = Any  # type: ignore
    ContextTypes = Any  # type: ignore
    filters = Any  # type: ignore

from ghost_manager import GhostManager
from support_hub import init_support_hub, SupportApiServer

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("ghost-bot")


def _parse_int(val, default=0) -> int:
    try:
        s = str(val or "").strip()
        return int(s) if s else default
    except (ValueError, TypeError):
        return default


BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip().strip("'\"")
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]
GHOST_DIR = os.getenv("GHOST_DIR", "/var/www/ghost")
BACKUPS_DIR = os.getenv("BACKUPS_DIR", os.path.join(GHOST_DIR, "backups"))
ADMIN_CHAT_ID = _parse_int(os.getenv("ADMIN_CHAT_ID"), ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 0)
SUPPORT_PORT = _parse_int(os.getenv("SUPPORT_PORT"), 8080)
SUPPORT_HOST = os.getenv("SUPPORT_HOST", "127.0.0.1")

# Global reference to Support REST API daemon
support_api_server: SupportApiServer = None

# Initialize Ghost Manager
ghost_mgr = GhostManager(ghost_dir=GHOST_DIR, backups_dir=BACKUPS_DIR)


def md_escape(val: Any) -> str:
    """Escape Telegram legacy Markdown v1 metacharacters in dynamic prose strings."""
    s = str(val if val is not None else "")
    return (
        s.replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "'")
        .replace("[", "(")
    )


def md_code(val: Any) -> str:
    """Sanitize a dynamic value placed inside single-backtick Markdown code spans."""
    s = str(val if val is not None else "")
    return s.replace("`", "'").replace("\r", " ").replace("\n", " ")


def is_authorized(user_id: int) -> bool:
    """Check if the requesting user ID is authorized (fails closed for security)."""
    has_positive_admin = bool(ADMIN_CHAT_ID and ADMIN_CHAT_ID > 0)
    if not ALLOWED_USER_IDS and not has_positive_admin:
        logger.warning(
            "Access denied for user %s: ALLOWED_USER_IDS and positive ADMIN_CHAT_ID are not set in .env. Failing closed.",
            user_id
        )
        return False
    if has_positive_admin and user_id == ADMIN_CHAT_ID:
        return True
    return user_id in ALLOWED_USER_IDS


def find_backup_file(file_name: str) -> Optional[str]:
    """Search for a valid .zip backup file in trusted storage locations (excludes /tmp and symlinks)."""
    if not file_name:
        return None
    clean_name = os.path.basename(file_name)
    candidates = [
        os.path.join(BACKUPS_DIR, clean_name),
        os.path.join("/home/ubuntu", clean_name),
        os.path.join(GHOST_DIR, clean_name),
    ]
    # Allow explicit path only if it resolves inside trusted directories
    if os.path.isabs(file_name):
        candidates.insert(0, file_name)

    trusted_roots = [
        os.path.realpath(BACKUPS_DIR),
        os.path.realpath("/home/ubuntu"),
        os.path.realpath(GHOST_DIR),
    ]
    for c in candidates:
        if not c or os.path.islink(c) or not str(c).lower().endswith(".zip"):
            continue
        if os.path.isfile(c):
            real = os.path.realpath(c)
            if any(real == r or real.startswith(r + os.sep) for r in trusted_roots):
                if zipfile.is_zipfile(real):
                    return real
    return None


def _update_env_file(key_values: dict, env_path: str = None):
    """Safely updates or appends key-value pairs in .env with strict 0600 permissions."""
    if not env_path:
        for f in _loaded_env_files:
            if os.path.isfile(f) and not os.path.islink(f):
                env_path = f
                break
        if not env_path:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    # Update in-memory environment immediately
    for k, v in key_values.items():
        os.environ[str(k)] = str(v)

    lines = []
    if os.path.exists(env_path) and not os.path.islink(env_path):
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in key_values:
                clean_val = str(key_values[k]).replace("\r", "").replace("\n", "")
                new_lines.append(f"{k}={clean_val}\n")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in key_values.items():
        if k not in updated_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            clean_val = str(v).replace("\r", "").replace("\n", "")
            new_lines.append(f"{k}={clean_val}\n")

    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass


def get_main_menu_keyboard():
    """Build the main interactive inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📦 Create Backup", callback_data="menu_backup"),
            InlineKeyboardButton("♻️ Restore Backup", callback_data="menu_restore_list"),
        ],
        [
            InlineKeyboardButton("🐙 GitHub Sync (Private)", callback_data="menu_github"),
            InlineKeyboardButton("📊 Ghost Status", callback_data="menu_status"),
        ],
        [
            InlineKeyboardButton("🛡️ Support Cases", callback_data="menu_cases_list"),
            InlineKeyboardButton("📑 List Backups", callback_data="menu_backups_list"),
        ],
        [
            InlineKeyboardButton("🔄 Restart Ghost", callback_data="menu_restart_confirm"),
            InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_unauthorized(update: Update):
    """Notify unauthorized user with clear authorization instructions."""
    uid = update.effective_user.id if update.effective_user else "Unknown"
    text = (
        f"⛔ *Access Denied*\n\n"
        f"Your Telegram User ID is `{uid}`.\n\n"
        f"This bot enforces fail-closed authorization for security. To authorize your account, add your ID to `.env`:\n"
        f"`ALLOWED_USER_IDS={uid}`\n"
        f"`ADMIN_CHAT_ID={uid}`\n\n"
        f"Then restart the service:\n"
        f"`sudo systemctl restart ghost-telegram-bot`"
    )
    if update.callback_query:
        await update.callback_query.answer("⛔ Access Denied", show_alert=True)
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /menu commands."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    status = ghost_mgr.get_status()
    state_emoji = "🟢 Online" if status.get("running") else "🔴 Offline / Inactive"

    welcome_text = (
        f"👻 *Ghost Publication Manager*\n\n"
        f"Welcome, *{md_escape(user.first_name)}*! Use the buttons below to manage, "
        f"backup, and restore your Ghost CMS installation.\n\n"
        f"🌐 *Status:* {state_emoji}\n"
        f"🔗 *URL:* `{md_code(status.get('url', 'N/A'))}`\n"
        f"📁 *Ghost Directory:* `{md_code(GHOST_DIR)}`\n"
        f"💾 *Total Backups:* `{status.get('total_backups', 0)}`\n"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline button callback queries."""
    query = update.callback_query
    user = update.effective_user
    try:
        await query.answer()
    except Exception:
        pass

    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    data = query.data

    # Return to Main Menu
    if data == "main_menu":
        status = ghost_mgr.get_status()
        state_emoji = "🟢 Online" if status.get("running") else "🔴 Offline / Inactive"
        welcome_text = (
            f"👻 *Ghost Publication Manager*\n\n"
            f"🌐 *Status:* {state_emoji}\n"
            f"🔗 *URL:* `{md_code(status.get('url', 'N/A'))}`\n"
            f"📁 *Ghost Directory:* `{md_code(GHOST_DIR)}`\n"
            f"💾 *Total Backups:* `{status.get('total_backups', 0)}`\n"
        )
        await query.edit_message_text(
            welcome_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 1. CREATE BACKUP
    elif data == "menu_backup":
        await query.edit_message_text(
            "⏳ *Starting Ghost Backup Process...*\n\n"
            "Please wait while we archive themes, media, settings, and database...",
            parse_mode=ParseMode.MARKDOWN
        )

        loop = asyncio.get_running_loop()
        last_reported = ""

        def progress_cb(msg: str):
            nonlocal last_reported
            if msg == last_reported:
                return
            last_reported = msg
            async def do_edit():
                try:
                    await query.edit_message_text(
                        f"⏳ *Ghost Backup in progress...*\n\n{md_escape(msg)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.create_backup, progress_callback=progress_cb)

        if not res.get("success"):
            err_msg = (
                f"❌ *Backup Failed!*\n\n"
                f"Error: `{md_code(res.get('error', 'Unknown error'))}`"
            )
            keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
            await query.edit_message_text(
                err_msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        file_path = res["file_path"]
        file_name = res["file_name"]
        size_mb = res["size_mb"]
        size_bytes = res["size_bytes"]

        success_text = (
            f"✅ *Backup Completed Successfully!*\n\n"
            f"📦 *File:* `{md_code(file_name)}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"🕒 *Timestamp:* `{md_code(res.get('timestamp'))}`\n"
            f"💾 *Saved at:* `{md_code(file_path)}`\n\n"
        )

        keyboard = [
            [InlineKeyboardButton("♻️ Restore This Backup", callback_data=f"restore_ask_{file_name}")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ]

        # Direct Telegram delivery if <= 48 MB
        if size_bytes < 48 * 1024 * 1024:
            await query.edit_message_text(
                success_text + "📤 *Uploading backup archive to Telegram chat...*",
                parse_mode=ParseMode.MARKDOWN
            )
            try:
                with open(file_path, "rb") as doc:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=doc,
                        filename=file_name,
                        caption=f"📦 Ghost Backup ({size_mb} MB) - {res.get('timestamp')}",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                try:
                    await query.delete_message()
                except Exception:
                    pass
                return
            except Exception as e:
                logger.error(f"Failed to upload document to Telegram: {e}")
                success_text += f"\n*(Notice: Direct Telegram upload skipped: {md_escape(e)})*"

        await query.edit_message_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 2. STATUS
    elif data == "menu_status":
        status = ghost_mgr.get_status()
        state_emoji = "🟢 Running" if status.get("running") else "🔴 Stopped / Offline"
        themes_str = ", ".join(status.get("themes", [])) or "None detected"

        text = (
            f"📊 *Ghost Publication Status*\n\n"
            f"• *Status:* {state_emoji}\n"
            f"• *Site URL:* `{md_code(status.get('url', 'N/A'))}`\n"
            f"• *Ghost Dir:* `{md_code(status.get('ghost_dir'))}`\n"
            f"• *Database Engine:* `{md_code(status.get('db_client'))}`\n"
            f"• *Execution User:* `{md_code(status.get('ghost_user'))}`\n"
            f"• *Installed Themes:* `{md_code(themes_str)}`\n"
            f"• *Total Backups:* `{status.get('total_backups')}`\n"
            f"• *Latest Backup:* `{md_code(status.get('latest_backup'))}`\n"
        )

        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="menu_status"),
                InlineKeyboardButton("🔄 Restart Ghost", callback_data="menu_restart_confirm")
            ],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 3. LIST BACKUPS / SELECT FOR RESTORE
    elif data in ("menu_restore_list", "menu_backups_list"):
        backups = ghost_mgr.list_backups()
        if not backups:
            text = (
                "📁 *No Backups Found*\n\n"
                f"No backup archives were found in `{md_code(BACKUPS_DIR)}` or `/home/ubuntu`.\n\n"
                "💡 *Options:*\n"
                "• Tap *Create Backup* to create one right now.\n"
                "• Upload a backup zip directly to this chat.\n"
                "• Send `/url <download_link>` to fetch from Google Drive, Dropbox, or file.io.\n"
                "• Upload via GCP SSH to `/home/ubuntu/` and type `/restore <filename>`."
            )
            keyboard = [
                [InlineKeyboardButton("📦 Create Backup Now", callback_data="menu_backup")],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
            ]
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        text = (
            f"📑 *Available Backups* ({len(backups)} found)\n\n"
            f"Select a backup below to restore it:\n"
            f"_(Or send `/url <link>` or `/restore <path>`)_"
        )

        keyboard = []
        for b in backups[:8]:  # Show latest 8
            keyboard.append([
                InlineKeyboardButton(
                    f"📦 {b['name']} ({b['size_mb']} MB)",
                    callback_data=f"restore_ask_{b['name']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 4. CONFIRM RESTORE QUESTION
    elif data.startswith("restore_ask_"):
        file_name = data.replace("restore_ask_", "")
        real_path = find_backup_file(file_name)

        if not real_path:
            await query.edit_message_text(
                f"❌ File `{md_code(file_name)}` not found on server in any trusted storage path.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_restore_list")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        size_mb = round(os.path.getsize(real_path) / (1024 * 1024), 2)
        confirm_text = (
            f"⚠️ *Confirm Ghost Publication Restore*\n\n"
            f"📦 *Archive:* `{md_code(os.path.basename(real_path))}`\n"
            f"📁 *Path:* `{md_code(real_path)}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n\n"
            f"🚨 *Warning:* This operation will:\n"
            f"1. Gracefully stop Ghost\n"
            f"2. Restore custom themes, images, and routes\n"
            f"3. Restore database posts, pages, tags, and settings\n"
            f"4. Correct file permissions and restart Ghost\n\n"
            f"Do you want to proceed?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Yes, Restore Now", callback_data=f"restore_do_{os.path.basename(real_path)}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="menu_restore_list")]
        ]
        await query.edit_message_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 5. EXECUTE RESTORE
    elif data.startswith("restore_do_"):
        file_name = data.replace("restore_do_", "")
        real_path = find_backup_file(file_name)

        if not real_path:
            await query.edit_message_text(
                f"❌ File `{md_code(file_name)}` not found on server.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        await query.edit_message_text(
            f"⏳ *Starting Restore for `{md_code(os.path.basename(real_path))}`...*\n\n"
            f"Please wait while Ghost restores your publication...",
            parse_mode=ParseMode.MARKDOWN
        )

        loop = asyncio.get_running_loop()
        last_reported = ""

        def progress_cb(msg: str):
            nonlocal last_reported
            if msg == last_reported:
                return
            last_reported = msg
            async def do_edit():
                try:
                    await query.edit_message_text(
                        f"⏳ *Restoring Ghost publication...*\n\n{md_escape(msg)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.restore_backup, real_path, progress_callback=progress_cb)

        if not res.get("success"):
            err_text = (
                f"❌ *Restore Failed!*\n\n"
                f"Error: `{md_code(res.get('error', 'Unknown error'))}`"
            )
            keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
            await query.edit_message_text(
                err_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        success_text = (
            f"🎉 *Ghost Publication Successfully Restored!*\n\n"
            f"✅ Themes, media, settings, and database synced.\n"
            f"✅ Linux permissions secured.\n"
            f"✅ Ghost service restarted and running."
        )
        keyboard = [
            [InlineKeyboardButton("📊 Check Status", callback_data="menu_status")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 6. RESTART CONFIRMATION
    elif data == "menu_restart_confirm":
        confirm_text = (
            "🔄 *Restart Ghost Service*\n\n"
            "Are you sure you want to restart Ghost now?\n"
            "The site may be briefly unreachable for a few seconds."
        )
        keyboard = [
            [InlineKeyboardButton("✅ Confirm Restart", callback_data="restart_do")],
            [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 7. EXECUTE RESTART
    elif data == "restart_do":
        await query.edit_message_text("⏳ Restarting Ghost...", parse_mode=ParseMode.MARKDOWN)
        res = await asyncio.to_thread(ghost_mgr.control_service, "restart")
        if res.get("success"):
            text = "✅ *Ghost successfully restarted!*"
        else:
            text = f"⚠️ *Restart notice / output:*\n```\n{res.get('stderr') or res.get('stdout')}\n```"

        keyboard = [
            [InlineKeyboardButton("📊 View Status", callback_data="menu_status")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 8. SUPPORT & INCIDENT CASES
    elif data == "menu_cases_list":
        if not support_api_server or not support_api_server.vault:
            try:
                await query.answer("⚠️ Support Hub Vault is initializing or offline.", show_alert=True)
            except Exception:
                pass
            await query.edit_message_text(
                "⚠️ *Support Hub Vault is initializing or offline.*",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        cases = support_api_server.vault.list_recent_cases(limit=8)
        if not cases:
            text = (
                "🛡️ *Confidential Support & Incident Cases*\n\n"
                "ℹ️ No cases currently recorded.\n"
                "New submissions from the `/support/` portal will alert you directly here in real time."
            )
            keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
            try:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                if "Message is not modified" not in str(e):
                    raise
            return

        text = (
            "🛡️ *Confidential Support & Incident Cases*\n\n"
            "Select an incident case to review, download evidence, or message the reporter:"
        )
        keyboard = []
        for c in cases:
            c_status = str(c.get("status") or "SUBMITTED").upper()
            status_tag = "🟡" if c_status == "SUBMITTED" else ("🟠" if c_status == "IN_REVIEW" else "🟢")
            c_subj = str(c.get("subject") or "Untitled")[:22]
            c_code = str(c.get("case_code") or "CASE")
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_tag} #{c_code} - {c_subj}",
                    callback_data=f"case_view:{c_code}"
                )
            ])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")])
        try:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise

    # 9. CASE ACTIONS (View, Review, Close, Reject, Evidence, Reply)
    elif data.startswith("case_"):
        if support_api_server and support_api_server.bridge:
            try:
                await support_api_server.bridge.handle_callback(update, context)
            except Exception as e:
                logger.exception("Error in support bridge handle_callback: %s", e)
                try:
                    await query.answer(f"⚠️ Error: {str(e)[:180]}", show_alert=True)
                except Exception:
                    pass
        else:
            try:
                await query.answer("⚠️ Support Hub Vault is initializing or offline.", show_alert=True)
            except Exception:
                pass
            await query.edit_message_text(
                "⚠️ *Support Hub Vault is initializing or offline.*",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN
            )

    # 10. GITHUB PRIVATE SYNC HUB
    elif data == "menu_github":
        gh_status = ghost_mgr.get_github_status()
        is_cfg = gh_status.get("configured", False)
        state_tag = "🟢 Configured" if is_cfg else "⚠️ Not Configured"

        text = (
            "🐙 *GitHub Sync Hub (Private Repository)*\n\n"
            "Keep an unzipped, human-readable archive of your publication on a private GitHub repository:\n"
            "• 📝 Individual JSON for each post & page (`posts/*.json`, `pages/*.json`)\n"
            "• 🖼️ Unzipped media images preserving folder layout\n"
            "• 💾 Complete database backup (`database/ghost_database.sql`)\n"
            "• 🎨 Custom themes and route definitions\n"
            "• 🔒 *Strict Privacy:* Incident support vault & evidence files are NEVER synced.\n\n"
            f"• *Status:* {state_tag}\n"
            f"• *Repository:* `{md_code(gh_status.get('repo', 'N/A'))}`\n"
            f"• *Branch:* `{md_code(gh_status.get('branch', 'main'))}`\n"
            f"• *Token:* `{md_code(gh_status.get('token_status', 'Not Set'))}`\n"
            f"• *Last Commit:* `{md_code(gh_status.get('last_commit', 'No sync recorded yet'))}`\n"
        )

        keyboard = [
            [
                InlineKeyboardButton("📤 Backup to GitHub Now", callback_data="gh_backup_now"),
                InlineKeyboardButton("📥 Restore from GitHub", callback_data="gh_restore_ask"),
            ],
            [
                InlineKeyboardButton("⚙️ Setup Instructions", callback_data="gh_setup_info"),
                InlineKeyboardButton("🔄 Refresh", callback_data="menu_github"),
            ],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # 11. GITHUB BACKUP EXECUTE
    elif data == "gh_backup_now":
        gh_status = ghost_mgr.get_github_status()
        if not gh_status["configured"]:
            text = (
                "⚠️ *GitHub Sync Not Configured*\n\n"
                "Please configure your private GitHub repository and token first:\n\n"
                "`/github_setup <repo_url> <token> [branch]`\n\n"
                "*Example:*\n"
                "`/github_setup https://github.com/Lordgrim77/my-backup.git ghp_xxxx main`"
            )
            keyboard = [
                [InlineKeyboardButton("⚙️ Setup Guide", callback_data="gh_setup_info")],
                [InlineKeyboardButton("⬅️ Back", callback_data="menu_github")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
            return

        await query.edit_message_text(
            "⏳ *Starting GitHub Backup Process...*\n\n"
            "Please wait while Ghost exports unzipped posts, pages, images, and database...",
            parse_mode=ParseMode.MARKDOWN
        )

        loop = asyncio.get_running_loop()
        last_reported = ""

        def progress_cb(msg: str):
            nonlocal last_reported
            if msg == last_reported:
                return
            last_reported = msg
            async def do_edit():
                try:
                    await query.edit_message_text(
                        f"⏳ *Ghost GitHub Backup in progress...*\n\n{md_escape(msg)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.backup_to_github, progress_callback=progress_cb)

        if not res.get("success"):
            err_text = f"❌ *GitHub Backup Failed!*\n\nError: `{md_code(res.get('error', 'Unknown error'))}`"
            keyboard = [[InlineKeyboardButton("⬅️ Back to GitHub Menu", callback_data="menu_github")]]
            await query.edit_message_text(err_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
            return

        if res.get("unchanged"):
            keyboard = [
                [InlineKeyboardButton("🐙 GitHub Menu", callback_data="menu_github")],
                [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
            ]
            await query.edit_message_text(
                "ℹ️ *Repository is Already Up to Date*\n\n"
                f"No changes detected since last backup. All {res.get('posts', 0)} posts and {res.get('pages', 0)} pages are synchronized.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        success_text = (
            f"✅ *GitHub Backup Completed Successfully!*\n\n"
            f"🐙 *Repository:* `{md_code(res.get('repo'))}`\n"
            f"🌿 *Branch:* `{md_code(res.get('branch'))}`\n"
            f"📦 *Commit:* `{md_code(res.get('commit'))}`\n"
            f"📝 *Posts Synced:* `{res.get('posts')}`\n"
            f"📄 *Pages Synced:* `{res.get('pages')}`\n"
            f"🕒 *Timestamp:* `{md_code(res.get('timestamp'))}`\n\n"
            f"🔒 *Privacy Guarantee:* Incident support cases and evidence files were strictly excluded."
        )
        keyboard = [
            [InlineKeyboardButton("📥 Restore from GitHub", callback_data="gh_restore_ask")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    # 12. GITHUB RESTORE CONFIRMATION
    elif data == "gh_restore_ask":
        gh_status = ghost_mgr.get_github_status()
        if not gh_status["configured"]:
            await query.edit_message_text(
                "⚠️ *GitHub Sync Not Configured*\n\nPlease set up with `/github_setup <repo_url> <token>`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_github")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        confirm_text = (
            f"⚠️ *Confirm Restore from Private GitHub Repository*\n\n"
            f"🐙 *Repository:* `{md_code(gh_status['repo'])}`\n"
            f"🌿 *Branch:* `{md_code(gh_status['branch'])}`\n\n"
            f"🚨 *Warning:* This operation will:\n"
            f"1. Gracefully stop Ghost\n"
            f"2. Pull the latest unzipped commit from GitHub\n"
            f"3. Restore database schema, posts, pages, and settings\n"
            f"4. Restore media images and custom themes\n"
            f"5. Secure Linux permissions and restart Ghost\n\n"
            f"Do you want to proceed with restoring from GitHub?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Restore from GitHub", callback_data="gh_restore_do")],
            [InlineKeyboardButton("❌ Cancel", callback_data="menu_github")]
        ]
        await query.edit_message_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    # 13. GITHUB RESTORE EXECUTE
    elif data == "gh_restore_do":
        await query.edit_message_text(
            "⏳ *Starting Restore from GitHub...*\n\nPlease wait while Ghost pulls and restores your publication...",
            parse_mode=ParseMode.MARKDOWN
        )

        loop = asyncio.get_running_loop()
        last_reported = ""

        def progress_cb(msg: str):
            nonlocal last_reported
            if msg == last_reported:
                return
            last_reported = msg
            async def do_edit():
                try:
                    await query.edit_message_text(
                        f"⏳ *Restoring Ghost from GitHub...*\n\n{md_escape(msg)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.restore_from_github, progress_callback=progress_cb)

        if not res.get("success"):
            err_text = f"❌ *GitHub Restore Failed!*\n\nError: `{md_code(res.get('error', 'Unknown error'))}`"
            keyboard = [[InlineKeyboardButton("⬅️ Back to GitHub Menu", callback_data="menu_github")]]
            await query.edit_message_text(err_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
            return

        success_text = (
            f"🎉 *Ghost Publication Successfully Restored from GitHub!*\n\n"
            f"✅ Restored from commit `{md_code(res.get('commit'))}` on branch `{md_code(res.get('branch'))}`.\n"
            f"✅ Database posts, pages, and settings synchronized.\n"
            f"✅ Uploaded media images and themes restored.\n"
            f"✅ Linux permissions secured & Ghost service active."
        )
        keyboard = [
            [InlineKeyboardButton("📊 Check Status", callback_data="menu_status")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    # 14. GITHUB SETUP GUIDE
    elif data == "gh_setup_info":
        info_text = (
            "⚙️ *GitHub Sync Setup Guide*\n\n"
            "1️⃣ **Create Private Repository**:\n"
            "Go to [github.com/new](https://github.com/new) and create a **Private** repository (e.g. `ghost-backup`).\n\n"
            "2️⃣ **Create Personal Access Token (PAT)**:\n"
            "Go to [github.com/settings/tokens](https://github.com/settings/tokens)\n"
            "Click *Generate new token (classic)* and check the `repo` scope.\n\n"
            "3️⃣ **Send Setup Command in Chat**:\n"
            "`/github_setup <repo_url> <token> [branch]`\n\n"
            "*Example:*\n"
            "`/github_setup https://github.com/Lordgrim77/ghost-backup.git ghp_yourSecretToken main`\n\n"
            "🔒 *Security:* Your message containing the secret token will be automatically deleted immediately upon receipt."
        )
        keyboard = [
            [InlineKeyboardButton("🐙 GitHub Menu", callback_data="menu_github")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

    # 15. HELP & INFO
    elif data == "menu_help":
        help_text = (
            "ℹ️ *Ghost Telegram Bot Help*\n\n"
            "• *📦 Create Backup:* Takes a complete snapshot of custom themes, uploaded images, "
            "routes, and database (MySQL/SQLite) into a single `.zip` archive. "
            "If under 48 MB, sends it directly in this chat!\n\n"
            "• *♻️ Restore Backup:* Restores a saved backup. Auto-fixes path slashes, protects default "
            "Ghost theme symlinks (`casper`/`source`), syncs database, and restarts Ghost.\n\n"
            "• *🐙 GitHub Sync (Private):* Save unzipped posts, pages, images, and database to a private GitHub repo. "
            "Never syncs support vault or evidence files. 1-click restore available directly from GitHub!\n\n"
            "• *🛡️ Support & Incident Cases:* View confidential incident cases submitted via the `/support/` portal, "
            "inspect metadata-scrubbed evidence files, update status (In Review, Closed, Rejected), and chat directly with reporters.\n\n"
            "• *🔗 URL Download:* Send `/url <link>` to download and restore any backup hosted online "
            "(Google Drive, Dropbox, file.io, etc.).\n\n"
            "• *📁 Local Restore:* Send `/restore /path/to/backup.zip` to restore any file on the server.\n\n"
            "• *📊 Status:* Shows Ghost uptime, active themes, and database details."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming documents/files sent by authorized users."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    # Check if document is sent within an active case reply session or reply to case message
    if support_api_server and support_api_server.bridge:
        bridge = support_api_server.bridge
        user_id = user.id
        reply_to = update.message.reply_to_message
        is_case_session = (user_id in bridge.active_reply_sessions) or (reply_to and reply_to.message_id in bridge.msg_to_case)
        if is_case_session:
            await bridge.handle_admin_message(update, context)
            return

    doc = update.message.document
    if not doc:
        return

    file_name = doc.file_name or "unknown.zip"
    if not file_name.lower().endswith(".zip"):
        await update.message.reply_text(
            "⚠️ Please upload a `.zip` Ghost backup archive.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    file_size_bytes = doc.file_size or 0
    size_mb = round(file_size_bytes / (1024 * 1024), 2)

    progress_msg = await update.message.reply_text(
        f"📥 *Receiving backup archive `{md_code(file_name)}` ({size_mb} MB)...*",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        raw_leaf = Path(file_name).name
        clean_name = re.sub(r"[^\w.\-]", "_", raw_leaf)[:80] or "backup.zip"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_name = f"uploaded_{timestamp}_{clean_name}"
        target_path = os.path.join(BACKUPS_DIR, target_name)

        # Extended timeouts for large archive transfers
        tg_file = await doc.get_file(read_timeout=600, write_timeout=600, connect_timeout=120)
        await tg_file.download_to_drive(custom_path=target_path, read_timeout=600, write_timeout=600)
        try:
            os.chmod(target_path, 0o600)
        except Exception:
            pass
        if not zipfile.is_zipfile(target_path):
            try:
                os.unlink(target_path)
            except Exception:
                pass
            raise ValueError("Uploaded file is not a valid ZIP archive.")

        text = (
            f"📥 *Backup File Uploaded Successfully!*\n\n"
            f"📦 *Name:* `{md_code(clean_name)}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"💾 *Saved as:* `{md_code(target_name)}`\n\n"
            f"Would you like to restore your Ghost blog using this archive right now?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Yes, Restore This Backup", callback_data=f"restore_ask_{target_name}")],
            [InlineKeyboardButton("❌ Keep in Storage Only", callback_data="menu_restore_list")]
        ]

        await progress_msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error handling document upload: {e}")
        err_msg = str(e).lower()
        safe_fn = md_code(Path(file_name).name)
        if "file is too big" in err_msg or "fileisttoobig" in str(type(e)).lower():
            limit_msg = (
                f"⚠️ *File Exceeds Telegram Cloud Bot Limit ({size_mb} MB)*\n\n"
                f"Telegram's default cloud API restricts bot downloads exceeding 20 MB (unless using a self-hosted Local Bot API server).\n\n"
                f"💡 *Easy Alternatives to Restore This File:*\n\n"
                f"1️⃣ **Direct URL Download**:\n"
                f"Send: `/url <direct_download_link>` (fetches archives of any size directly onto the server)\n\n"
                f"2️⃣ **Server Upload**:\n"
                f"Upload via SSH/SCP to `/home/ubuntu/{safe_fn}` and send: `/restore /home/ubuntu/{safe_fn}`"
            )
            await progress_msg.edit_text(limit_msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await progress_msg.edit_text(
                f"❌ *Failed to download backup file:*\n`{md_code(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos from authorized users, routing to active case chat."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    if support_api_server and support_api_server.bridge:
        bridge = support_api_server.bridge
        user_id = user.id
        reply_to = update.message.reply_to_message
        is_case_session = (user_id in bridge.active_reply_sessions) or (reply_to and reply_to.message_id in bridge.msg_to_case)
        if is_case_session:
            await bridge.handle_admin_message(update, context)
            return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages from authorized admins, routing active case replies."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    if support_api_server and support_api_server.bridge:
        bridge = support_api_server.bridge
        user_id = user.id
        reply_to = update.message.reply_to_message
        is_case_session = (user_id in bridge.active_reply_sessions) or (reply_to and reply_to.message_id in bridge.msg_to_case)
        if is_case_session:
            await bridge.handle_admin_message(update, context)
            return

    if update.message.text:
        await update.message.reply_text(
            "ℹ️ Use the menu buttons below to manage Ghost, or type /start.",
            reply_markup=get_main_menu_keyboard()
        )


async def cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    if support_api_server and support_api_server.bridge:
        await support_api_server.bridge.cases_command(update, context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return
    if support_api_server and support_api_server.bridge:
        await support_api_server.bridge.cancel_command(update, context)


def _is_forbidden_ip(ip_str: str) -> bool:
    """Return True if IP is loopback, private, link-local, metadata, multicast, or reserved."""
    clean_ip = ip_str.split("%")[0]
    ip_obj = ipaddress.ip_address(clean_ip)
    if getattr(ip_obj, "ipv4_mapped", None):
        ip_obj = ip_obj.ipv4_mapped
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _validate_public_http_url(target_url: str) -> str:
    """Validate URL scheme/host and reject internal, loopback, or cloud metadata IPs (SSRF defense)."""
    parsed = urllib.parse.urlparse(target_url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("Only http:// and https:// download URLs are permitted.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not permitted.")
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid URL hostname.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addr_infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception as e:
        raise ValueError(f"DNS resolution failed for {host}: {e}")
    if not addr_infos:
        raise ValueError(f"Could not resolve hostname: {host}")
    for info in addr_infos:
        sockaddr = info[4]
        if sockaddr and _is_forbidden_ip(sockaddr[0]):
            raise ValueError(f"Blocked connection to non-public IP address ({sockaddr[0]}).")
    return target_url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect destination against SSRF blocklists before following."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        _validate_public_http_url(resolved_url)
        return super().redirect_request(req, fp, code, msg, headers, resolved_url)


async def url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download backup archive directly from a validated public URL."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    if not context.args or not context.args[0].startswith(("https://", "http://")):
        await update.message.reply_text(
            "ℹ️ *Usage:*\n`/url <download_link>`\n\n"
            "Example: `/url https://file.io/xxxxxx` or a Dropbox/Google Drive share link.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    raw_url = context.args[0].strip()
    # Normalize Dropbox links to direct download
    if "dropbox.com" in raw_url:
        raw_url = raw_url.replace("dl=0", "dl=1")

    # Normalize Google Drive sharing links to direct download
    if "drive.google.com" in raw_url:
        gdrive_match = re.search(r"/d/([a-zA-Z0-9_-]+)", raw_url) or re.search(r"id=([a-zA-Z0-9_-]+)", raw_url)
        if gdrive_match:
            raw_url = f"https://drive.google.com/uc?export=download&id={gdrive_match.group(1)}&confirm=t"

    status_msg = await update.message.reply_text(
        "⏳ *Validating URL & downloading backup archive directly to server...*",
        parse_mode=ParseMode.MARKDOWN
    )

    target_path = None
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_name = f"url_backup_{timestamp}.zip"
        target_path = os.path.join(BACKUPS_DIR, target_name)
        max_download_bytes = 2 * 1024 * 1024 * 1024  # 2 GB cap

        def do_download():
            _validate_public_http_url(raw_url)
            opener = urllib.request.build_opener(_SafeRedirectHandler())
            req = urllib.request.Request(
                raw_url,
                headers={"User-Agent": "GhostRestoreBot/1.0"}
            )
            fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            downloaded = 0
            with opener.open(req, timeout=600) as resp, os.fdopen(fd, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_download_bytes:
                        raise ValueError("Download exceeds maximum allowed archive size (2 GB).")
                    out.write(chunk)
            try:
                os.chmod(target_path, 0o600)
            except Exception:
                pass
            if not zipfile.is_zipfile(target_path):
                raise ValueError("Downloaded resource is not a valid ZIP archive.")

        await asyncio.to_thread(do_download)

        size_mb = round(os.path.getsize(target_path) / (1024 * 1024), 2)
        text = (
            f"📥 *Backup Downloaded Successfully!*\n\n"
            f"📦 *Name:* `{md_code(target_name)}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"💾 *Saved to:* `{md_code(target_path)}`\n\n"
            f"Would you like to restore your Ghost publication with this archive right now?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Restore Now", callback_data=f"restore_ask_{target_name}")],
            [InlineKeyboardButton("❌ Keep in Storage", callback_data="menu_restore_list")]
        ]
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        if target_path and os.path.exists(target_path):
            try:
                os.unlink(target_path)
            except Exception:
                pass
        logger.error(f"Download failed: {e}")
        await status_msg.edit_text(f"❌ *Download Failed:*\n`{md_code(e)}`", parse_mode=ParseMode.MARKDOWN)


async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore from a specific local path or filename on the server."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    if not context.args:
        # Show list of backups
        backups = ghost_mgr.list_backups()
        if not backups:
            await update.message.reply_text(
                "📁 No backups found.\nUsage: `/restore /path/to/backup.zip`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        keyboard = []
        for b in backups[:8]:
            keyboard.append([InlineKeyboardButton(f"📦 {b['name']} ({b['size_mb']} MB)", callback_data=f"restore_ask_{b['name']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")])
        await update.message.reply_text("Select a backup to restore:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    target = " ".join(context.args).strip()
    real_path = find_backup_file(target)

    if not real_path:
        await update.message.reply_text(f"❌ Valid `.zip` backup file not found in trusted storage:\n`{md_code(target)}`", parse_mode=ParseMode.MARKDOWN)
        return

    size_mb = round(os.path.getsize(real_path) / (1024 * 1024), 2)
    name = os.path.basename(real_path)
    text = (
        f"⚠️ *Confirm Restore from Server File*\n\n"
        f"📦 *Name:* `{md_code(name)}`\n"
        f"📁 *Path:* `{md_code(real_path)}`\n"
        f"⚖️ *Size:* `{size_mb} MB`\n\n"
        f"Are you sure you want to restore Ghost using this archive?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Restore Now", callback_data=f"restore_ask_{name}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


async def github_setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configures the private GitHub backup repository and token."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "ℹ️ *GitHub Sync Setup Usage:*\n"
            "`/github_setup <repo_url> <personal_access_token> [branch]`\n\n"
            "*Example:*\n"
            "`/github_setup https://github.com/Lordgrim77/my-backup.git ghp_xxxx main`\n\n"
            "💡 *Token Requirements:* A GitHub Personal Access Token (classic) with `repo` scope.\n"
            "Create one at: https://github.com/settings/tokens",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    repo_url = context.args[0].strip()
    token = context.args[1].strip()
    branch = context.args[2].strip() if len(context.args) > 2 else "main"

    # Immediately delete message containing the token for security
    try:
        await update.message.delete()
    except Exception:
        pass

    try:
        branch = GhostManager._validate_git_branch(branch)
    except ValueError as ve:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Invalid Branch Name:* `{md_code(ve)}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ *Testing GitHub connection & validating permissions...*",
        parse_mode=ParseMode.MARKDOWN
    )

    clean_repo = ghost_mgr._build_authenticated_git_url(repo_url)
    valid, err_or_ok = await asyncio.to_thread(ghost_mgr.test_github_connection, clean_repo, token)
    if not valid:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]
        await status_msg.edit_text(
            f"❌ *GitHub Connection Failed!*\n\n"
            f"Error: `{md_code(err_or_ok)}`\n\n"
            f"Please verify that the repository URL exists and your token has `repo` permissions.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    _update_env_file({
        "GITHUB_BACKUP_REPO": clean_repo,
        "GITHUB_TOKEN": token,
        "GITHUB_BRANCH": branch
    })
    os.environ["GITHUB_BACKUP_REPO"] = clean_repo
    os.environ["GITHUB_TOKEN"] = token
    os.environ["GITHUB_BRANCH"] = branch

    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "Configured"

    keyboard = [
        [InlineKeyboardButton("📤 Backup to GitHub Now", callback_data="gh_backup_now")],
        [InlineKeyboardButton("🐙 GitHub Menu", callback_data="menu_github")]
    ]
    await status_msg.edit_text(
        f"✅ *GitHub Backup Configured Successfully!*\n\n"
        f"🐙 *Repository:* `{md_code(clean_repo)}`\n"
        f"🌿 *Branch:* `{md_code(branch)}`\n"
        f"🔑 *Token:* `{md_code(masked_token)}` (Validated)\n\n"
        f"🔒 _(Your message containing the secret token was automatically deleted from chat for security)_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )


async def github_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers an unzipped publication backup directly to GitHub."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    status = ghost_mgr.get_github_status()
    if not status["configured"]:
        await update.message.reply_text(
            "⚠️ *GitHub Not Configured*\n\n"
            "Please configure your repository and token first:\n"
            "`/github_setup <repo_url> <token> [branch]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    status_msg = await update.message.reply_text(
        "⏳ *Starting Ghost GitHub Backup Process...*",
        parse_mode=ParseMode.MARKDOWN
    )

    loop = asyncio.get_running_loop()
    last_reported = ""

    def progress_cb(msg: str):
        nonlocal last_reported
        if msg == last_reported:
            return
        last_reported = msg
        async def do_edit():
            try:
                await status_msg.edit_text(
                    f"⏳ *Ghost GitHub Backup in progress...*\n\n{md_escape(msg)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(do_edit(), loop)

    res = await asyncio.to_thread(ghost_mgr.backup_to_github, progress_callback=progress_cb)
    if not res.get("success"):
        keyboard = [[InlineKeyboardButton("🐙 GitHub Menu", callback_data="menu_github")]]
        await status_msg.edit_text(
            f"❌ *GitHub Backup Failed!*\n\nError: `{md_code(res.get('error', 'Unknown error'))}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if res.get("unchanged"):
        keyboard = [[InlineKeyboardButton("🐙 GitHub Menu", callback_data="menu_github")]]
        await status_msg.edit_text(
            f"ℹ️ *Repository is Already Up to Date*\n\nNo changes detected since last backup.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    success_text = (
        f"✅ *GitHub Backup Completed Successfully!*\n\n"
        f"🐙 *Repository:* `{md_code(res.get('repo'))}`\n"
        f"🌿 *Branch:* `{md_code(res.get('branch'))}`\n"
        f"📦 *Commit:* `{md_code(res.get('commit'))}`\n"
        f"📝 *Posts Synced:* `{res.get('posts')}`\n"
        f"📄 *Pages Synced:* `{res.get('pages')}`\n"
        f"🕒 *Timestamp:* `{md_code(res.get('timestamp'))}`\n\n"
        f"🔒 *Privacy Note:* Evidence files and support cases were strictly excluded."
    )
    keyboard = [
        [InlineKeyboardButton("📥 Restore from GitHub", callback_data="gh_restore_ask")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
    ]
    await status_msg.edit_text(success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


async def github_restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers restore from private GitHub repository."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    status = ghost_mgr.get_github_status()
    if not status["configured"]:
        await update.message.reply_text(
            "⚠️ *GitHub Not Configured*\n\n"
            "Please configure your repository and token first:\n"
            "`/github_setup <repo_url> <token> [branch]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    confirm_text = (
        f"⚠️ *Confirm Restore from Private GitHub Repository*\n\n"
        f"🐙 *Repository:* `{md_code(status['repo'])}`\n"
        f"🌿 *Branch:* `{md_code(status['branch'])}`\n\n"
        f"🚨 *Warning:* This operation will:\n"
        f"1. Gracefully stop Ghost\n"
        f"2. Pull the latest unzipped commit from GitHub\n"
        f"3. Restore database schema, posts, pages, and settings\n"
        f"4. Restore media images and custom themes\n"
        f"5. Secure Linux permissions and restart Ghost\n\n"
        f"Do you want to proceed?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Restore Now", callback_data="gh_restore_do")],
        [InlineKeyboardButton("❌ Cancel", callback_data="menu_github")]
    ]
    await update.message.reply_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


async def github_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows current configuration and sync status of GitHub repository."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    gh_status = ghost_mgr.get_github_status()
    state_tag = "🟢 Configured" if gh_status["configured"] else "⚠️ Not Configured"

    text = (
        f"🐙 *GitHub Sync Status*\n\n"
        f"• *Status:* {state_tag}\n"
        f"• *Repository:* `{md_code(gh_status['repo'])}`\n"
        f"• *Branch:* `{md_code(gh_status['branch'])}`\n"
        f"• *Token:* `{md_code(gh_status['token_status'])}`\n"
        f"• *Last Commit:* `{md_code(gh_status['last_commit'])}`\n"
    )
    keyboard = [
        [
            InlineKeyboardButton("📤 Backup Now", callback_data="gh_backup_now"),
            InlineKeyboardButton("📥 Restore", callback_data="gh_restore_ask"),
        ],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


def _effective_allowed_user_ids() -> set:
    allowed = set(ALLOWED_USER_IDS)
    if ADMIN_CHAT_ID and ADMIN_CHAT_ID > 0:
        allowed.add(ADMIN_CHAT_ID)
    return allowed


async def post_init(application: Application):
    """Start Support Hub API server and register bot bridge on the asyncio event loop."""
    global support_api_server
    try:
        support_api_server = init_support_hub(
            application=application,
            ghost_dir=GHOST_DIR,
            admin_chat_id=ADMIN_CHAT_ID,
            port=SUPPORT_PORT,
            host=SUPPORT_HOST,
            allowed_user_ids=_effective_allowed_user_ids(),
            auth_callback=is_authorized,
        )
        await support_api_server.start()
        logger.info(f"Support REST API daemon listening on http://{SUPPORT_HOST}:{SUPPORT_PORT}")
    except Exception as e:
        logger.error(f"Failed to start Support API server: {e}")


async def post_shutdown(application: Application):
    """Gracefully shutdown Support Hub API server."""
    global support_api_server
    if support_api_server:
        try:
            await support_api_server.stop()
            logger.info("Support REST API daemon stopped.")
        except Exception as e:
            logger.error(f"Error stopping Support API server: {e}")


def main():
    """Start the Telegram bot application, or fallback to standalone Support API server."""
    if not HAS_TELEGRAM or not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("==================================================")
        if not HAS_TELEGRAM:
            print(" [INFO] python-telegram-bot is not installed.")
            print(" Running Support REST API daemon in standalone mode.")
        else:
            print(" [WARNING] TELEGRAM_BOT_TOKEN not configured in .env")
            print(" Starting Support REST API server in fallback mode.")
        print("==================================================")
        print(f"Ghost Directory:     {GHOST_DIR}")
        print(f"Backups Directory:   {BACKUPS_DIR}")
        print(f"Support REST API:    http://{SUPPORT_HOST}:{SUPPORT_PORT}")
        if _loaded_env_files:
            print(f"Loaded Configs:      {', '.join(_loaded_env_files)}")
        if HAS_TELEGRAM:
            print("(Add your bot token to .env to enable Telegram bot polling)")
        else:
            print("(Install python-telegram-bot in virtualenv to enable Telegram bot polling)")
        print("--------------------------------------------------")

        server = init_support_hub(
            application=None,
            ghost_dir=GHOST_DIR,
            admin_chat_id=ADMIN_CHAT_ID,
            port=SUPPORT_PORT,
            host=SUPPORT_HOST,
            allowed_user_ids=_effective_allowed_user_ids(),
            auth_callback=is_authorized,
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.start())
            loop.run_forever()
        except KeyboardInterrupt:
            loop.run_until_complete(server.stop())
        except Exception as e:
            logger.error("Standalone Support API daemon error: %s", e)
        return

    print("==================================================")
    print("   Ghost Backup & Restore Telegram Bot Service    ")
    print("==================================================")
    print(f"Ghost Directory:     {GHOST_DIR}")
    print(f"Backups Directory:   {BACKUPS_DIR}")
    print(f"Authorized User IDs: {_effective_allowed_user_ids() or 'None Configured (Locked / Fail-Closed)'}")
    print(f"Admin Alert Chat ID: {ADMIN_CHAT_ID or 'Not Set'}")
    print(f"Support REST API:    http://{SUPPORT_HOST}:{SUPPORT_PORT}")
    if _loaded_env_files:
        print(f"Loaded Configs:      {', '.join(_loaded_env_files)}")
    print("--------------------------------------------------")
    print("Bot is starting polling...")

    builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    custom_api_url = os.getenv("TELEGRAM_API_URL") or os.getenv("LOCAL_BOT_API_URL")
    if custom_api_url:
        clean_url = custom_api_url.rstrip("/")
        if not clean_url.endswith("/bot"):
            clean_url = f"{clean_url}/bot"
        builder = builder.base_url(clean_url)
        clean_file_url = custom_api_url.rstrip("/")
        if not clean_file_url.endswith("/file/bot"):
            clean_file_url = f"{clean_file_url}/file/bot"
        builder = builder.base_file_url(clean_file_url)
        print(f"Custom Telegram Bot API Endpoint: {custom_api_url}")
    app = builder.build()

    # Handlers
    app.add_handler(CommandHandler(["start", "menu"], start_command))
    app.add_handler(CommandHandler(["github_setup", "gh_setup"], github_setup_command))
    app.add_handler(CommandHandler(["github_backup", "gh_backup"], github_backup_command))
    app.add_handler(CommandHandler(["github_restore", "gh_restore"], github_restore_command))
    app.add_handler(CommandHandler(["github_status", "gh_status"], github_status_command))
    app.add_handler(CommandHandler("cases", cases_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("url", url_command))
    app.add_handler(CommandHandler("restore", restore_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    try:
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error("Telegram bot polling stopped due to error: %s", e, exc_info=True)
        print(f"\n[ERROR] Telegram bot polling encountered an unhandled exception: {e}")
        print("[INFO] Fallback: Ensuring Support REST API daemon remains active on port 8080...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        fallback_server = init_support_hub(
            application=None,
            ghost_dir=GHOST_DIR,
            admin_chat_id=ADMIN_CHAT_ID,
            port=SUPPORT_PORT,
            host=SUPPORT_HOST,
            allowed_user_ids=_effective_allowed_user_ids(),
            auth_callback=is_authorized,
        )
        try:
            loop.run_until_complete(fallback_server.start())
            loop.run_forever()
        except KeyboardInterrupt:
            loop.run_until_complete(fallback_server.stop())
        except Exception as fbe:
            logger.error("Fallback Support API server error: %s", fbe)


if __name__ == "__main__":
    main()
