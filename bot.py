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
import logging
import asyncio
import datetime
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from ghost_manager import GhostManager

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("ghost-bot")

# Load environment configuration
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]
GHOST_DIR = os.getenv("GHOST_DIR", "/var/www/ghost")
BACKUPS_DIR = os.getenv("BACKUPS_DIR", os.path.join(GHOST_DIR, "backups"))

# Initialize Ghost Manager
ghost_mgr = GhostManager(ghost_dir=GHOST_DIR, backups_dir=BACKUPS_DIR)


def is_authorized(user_id: int) -> bool:
    """Check if the requesting user ID is authorized."""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def find_backup_file(file_name: str) -> str:
    """Search for backup file in known locations."""
    clean_name = os.path.basename(file_name)
    candidates = [
        file_name,
        os.path.join(BACKUPS_DIR, clean_name),
        os.path.join("/tmp", clean_name),
        os.path.join("/home/ubuntu", clean_name),
        os.path.join(GHOST_DIR, clean_name),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def get_main_menu_keyboard():
    """Build the main interactive inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📦 Create Backup", callback_data="menu_backup"),
            InlineKeyboardButton("♻️ Restore Backup", callback_data="menu_restore_list"),
        ],
        [
            InlineKeyboardButton("📊 Ghost Status", callback_data="menu_status"),
            InlineKeyboardButton("📑 List Backups", callback_data="menu_backups_list"),
        ],
        [
            InlineKeyboardButton("🔄 Restart Ghost", callback_data="menu_restart_confirm"),
            InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_unauthorized(update: Update):
    """Notify unauthorized user."""
    uid = update.effective_user.id if update.effective_user else "Unknown"
    text = (
        f"⛔ *Access Denied*\n\n"
        f"Your Telegram User ID is `{uid}`.\n"
        f"It is not present in `ALLOWED_USER_IDS` in `.env`."
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
        f"Welcome, *{user.first_name}*! Use the buttons below to manage, "
        f"backup, and restore your Ghost CMS installation.\n\n"
        f"🌐 *Status:* {state_emoji}\n"
        f"🔗 *URL:* `{status.get('url', 'N/A')}`\n"
        f"📁 *Ghost Directory:* `{GHOST_DIR}`\n"
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
    await query.answer()

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
            f"🔗 *URL:* `{status.get('url', 'N/A')}`\n"
            f"📁 *Ghost Directory:* `{GHOST_DIR}`\n"
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
                        f"⏳ *Ghost Backup in progress...*\n\n{msg}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.create_backup, progress_callback=progress_cb)

        if not res.get("success"):
            err_msg = (
                f"❌ *Backup Failed!*\n\n"
                f"Error: `{res.get('error', 'Unknown error')}`"
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
            f"📦 *File:* `{file_name}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"🕒 *Timestamp:* `{res.get('timestamp')}`\n"
            f"💾 *Saved at:* `{file_path}`\n\n"
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
                success_text += f"\n*(Notice: Direct Telegram upload skipped: {e})*"

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
            f"• *Site URL:* `{status.get('url', 'N/A')}`\n"
            f"• *Ghost Dir:* `{status.get('ghost_dir')}`\n"
            f"• *Database Engine:* `{status.get('db_client')}`\n"
            f"• *Execution User:* `{status.get('ghost_user')}`\n"
            f"• *Installed Themes:* `{themes_str}`\n"
            f"• *Total Backups:* `{status.get('total_backups')}`\n"
            f"• *Latest Backup:* `{status.get('latest_backup')}`\n"
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
                f"No backup archives were found in `{BACKUPS_DIR}`, `/tmp`, or `/home/ubuntu`.\n\n"
                "💡 *Options:*\n"
                "• Tap *Create Backup* to create one right now.\n"
                "• Upload a zip under 20 MB directly to this chat.\n"
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
                f"❌ File `{file_name}` not found on server in any storage path.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu_restore_list")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        size_mb = round(os.path.getsize(real_path) / (1024 * 1024), 2)
        confirm_text = (
            f"⚠️ *Confirm Ghost Publication Restore*\n\n"
            f"📦 *Archive:* `{os.path.basename(real_path)}`\n"
            f"📁 *Path:* `{real_path}`\n"
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
                f"❌ File `{file_name}` not found on server.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        await query.edit_message_text(
            f"⏳ *Starting Restore for `{os.path.basename(real_path)}`...*\n\n"
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
                        f"⏳ *Restoring Ghost publication...*\n\n{msg}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            asyncio.run_coroutine_threadsafe(do_edit(), loop)

        res = await asyncio.to_thread(ghost_mgr.restore_backup, real_path, progress_callback=progress_cb)

        if not res.get("success"):
            err_text = (
                f"❌ *Restore Failed!*\n\n"
                f"Error: `{res.get('error', 'Unknown error')}`"
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
        res = await asyncio.to_thread(ghost_mgr.run_ghost_cli, "restart")
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

    # 8. HELP & INFO
    elif data == "menu_help":
        help_text = (
            "ℹ️ *Ghost Telegram Bot Help*\n\n"
            "• *📦 Create Backup:* Takes a complete snapshot of custom themes, uploaded images, "
            "routes, and database (MySQL/SQLite) into a single `.zip` archive. "
            "If under 48 MB, sends it directly in this chat!\n\n"
            "• *♻️ Restore Backup:* Restores a saved backup. Auto-fixes path slashes, protects default "
            "Ghost theme symlinks (`casper`/`source`), syncs database, and restarts Ghost.\n\n"
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
    """Handle incoming .zip backup files sent by authorized users."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
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

    # Check 20 MB Telegram Bot API download limit
    file_size_bytes = doc.file_size or 0
    size_mb = round(file_size_bytes / (1024 * 1024), 2)

    if file_size_bytes > 20 * 1024 * 1024:
        limit_msg = (
            f"⚠️ *File is Too Large for Telegram Direct Upload ({size_mb} MB)*\n\n"
            f"Telegram limits bots to downloading files of *up to 20 MB*.\n\n"
            f"💡 *2 Easy Ways to Restore This Backup:*\n\n"
            f"1️⃣ **Direct URL Download (Fastest)**:\n"
            f"Upload your backup to [file.io](https://www.file.io), Google Drive, or Dropbox, and send:\n"
            f"`/url <download_link>`\n\n"
            f"2️⃣ **Upload via GCP Web Terminal**:\n"
            f"In your GCP SSH browser window, click the **Gear Icon ⚙️ (top-right)** ➔ **Upload file**.\n"
            f"Once uploaded to `/home/ubuntu/{file_name}`, send:\n"
            f"`/restore /home/ubuntu/{file_name}`\n"
            f"*(or tap ♻️ Restore Backup in the menu)*"
        )
        await update.message.reply_text(limit_msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        return

    progress_msg = await update.message.reply_text(
        f"📥 *Receiving backup archive `{file_name}` ({size_mb} MB)...*",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        clean_name = Path(file_name).name
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_name = f"uploaded_{timestamp}_{clean_name}"
        target_path = os.path.join(BACKUPS_DIR, target_name)

        tg_file = await doc.get_file()
        await tg_file.download_to_drive(custom_path=target_path)

        text = (
            f"📥 *Backup File Uploaded Successfully!*\n\n"
            f"📦 *Name:* `{clean_name}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"💾 *Saved as:* `{target_name}`\n\n"
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
        await progress_msg.edit_text(
            f"❌ *Failed to download backup file:*\n`{e}`",
            parse_mode=ParseMode.MARKDOWN
        )


async def url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download backup archive directly from a given URL."""
    user = update.effective_user
    if not is_authorized(user.id):
        await send_unauthorized(update)
        return

    if not context.args or not context.args[0].startswith("http"):
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

    status_msg = await update.message.reply_text(
        "⏳ *Downloading backup archive from URL directly to server...*",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_name = f"url_backup_{timestamp}.zip"
        target_path = os.path.join(BACKUPS_DIR, target_name)

        def do_download():
            req = urllib.request.Request(
                raw_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp, open(target_path, "wb") as out:
                shutil.copyfileobj(resp, out)

        await asyncio.to_thread(do_download)

        size_mb = round(os.path.getsize(target_path) / (1024 * 1024), 2)
        text = (
            f"📥 *Backup Downloaded Successfully!*\n\n"
            f"📦 *Name:* `{target_name}`\n"
            f"⚖️ *Size:* `{size_mb} MB`\n"
            f"💾 *Saved to:* `{target_path}`\n\n"
            f"Would you like to restore your Ghost publication with this archive right now?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Restore Now", callback_data=f"restore_ask_{target_name}")],
            [InlineKeyboardButton("❌ Keep in Storage", callback_data="menu_restore_list")]
        ]
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Download failed: {e}")
        await status_msg.edit_text(f"❌ *Download Failed:*\n`{e}`", parse_mode=ParseMode.MARKDOWN)


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
        await update.message.reply_text(f"❌ File not found on server:\n`{target}`", parse_mode=ParseMode.MARKDOWN)
        return

    size_mb = round(os.path.getsize(real_path) / (1024 * 1024), 2)
    name = os.path.basename(real_path)
    text = (
        f"⚠️ *Confirm Restore from Server File*\n\n"
        f"📦 *Name:* `{name}`\n"
        f"📁 *Path:* `{real_path}`\n"
        f"⚖️ *Size:* `{size_mb} MB`\n\n"
        f"Are you sure you want to restore Ghost using this archive?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Restore Now", callback_data=f"restore_ask_{name}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


def main():
    """Start the Telegram bot application."""
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("[ERROR] TELEGRAM_BOT_TOKEN is not configured in .env!")
        print("Please set your bot token from @BotFather in .env.")
        sys.exit(1)

    print("==================================================")
    print("   Ghost Backup & Restore Telegram Bot Service    ")
    print("==================================================")
    print(f"Ghost Directory:     {GHOST_DIR}")
    print(f"Backups Directory:   {BACKUPS_DIR}")
    print(f"Authorized User IDs: {ALLOWED_USER_IDS or 'All Users (Open)'}")
    print("--------------------------------------------------")
    print("Bot is starting polling...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler(["start", "menu"], start_command))
    app.add_handler(CommandHandler("url", url_command))
    app.add_handler(CommandHandler("restore", restore_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.run_polling()


if __name__ == "__main__":
    main()
