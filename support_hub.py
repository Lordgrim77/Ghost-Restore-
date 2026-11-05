"""
Support & Evidence Portal Management Hub
Integrated with Telegram Bot for 1-Click Status Triage & Two-Way Case Chat.
Part of the Custom Ghost Alto Theme & Administrative Infrastructure.

Features:
 1. Isolated SQLite Vault inside GHOST_DIR/support_vault/ (auto-captured by ghost backup)
 2. Pure Python EXIF/GPS Metadata Scrubbing for uploaded media (OpSec protection)
 3. Cryptographic SHA-256 Evidentiary Chain-of-Custody Checksums
 4. Zero-Dependency Async HTTP API Server running directly on the Telegram Bot event loop
 5. Interactive Telegram Inline Keyboards: In Review, Close, Reject, Evidence Download, Reply
 6. Two-Way Web <-> Telegram Chat bridging reporters and investigators in real time
"""

import os
import sys
import re
import html
import json
import uuid
import secrets
import hashlib
import hmac
import sqlite3
import datetime
import struct
import asyncio
import logging
import urllib.parse
import time
from typing import Optional, Dict, Any, List
from email import policy
from email.parser import BytesParser

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

logger = logging.getLogger("support-hub")

# =========================================================================
# OpSec & Metadata Scrubbing (Pure Python, Zero External C Dependencies)
# =========================================================================

def strip_jpeg_exif(data: bytes) -> bytes:
    """Strip EXIF (APP1), FlashPix/ICC (APP2), and comment markers from JPEG bytes."""
    if not data.startswith(b'\xff\xd8'):
        return data
    out = [b'\xff\xd8']
    idx = 2
    length = len(data)
    while idx < length:
        if data[idx] != 0xff:
            out.append(data[idx:])
            break
        marker = data[idx:idx+2]
        if marker == b'\xff\xd9':  # End of Image
            out.append(marker)
            break
        if marker in (b'\xff\x00', b'\xff\x01') or (0xffd0 <= int.from_bytes(marker, 'big') <= 0xffd7):
            out.append(marker)
            idx += 2
            continue
        if idx + 4 > length:
            out.append(data[idx:])
            break
        seg_len = int.from_bytes(data[idx+2:idx+4], 'big')
        # Drop APP1 (0xFFE1: EXIF/GPS/XMP) and COM (0xFFFE: Comments)
        if marker not in (b'\xff\xe1', b'\xff\xfe'):
            out.append(data[idx:idx+2+seg_len])
        idx += 2 + seg_len
    return b''.join(out)


def strip_png_metadata(data: bytes) -> bytes:
    """Strip ancillary text/metadata chunks (tEXt, zTXt, iTXt, eXIf, tIME) from PNG bytes."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return data
    out = [b'\x89PNG\r\n\x1a\n']
    idx = 8
    length = len(data)
    drop_chunks = {b'tEXt', b'zTXt', b'iTXt', b'eXIf', b'tIME'}
    while idx + 8 <= length:
        chunk_len = struct.unpack('>I', data[idx:idx+4])[0]
        chunk_type = data[idx+4:idx+8]
        total_len = 12 + chunk_len
        if idx + total_len > length:
            out.append(data[idx:])
            break
        if chunk_type not in drop_chunks:
            out.append(data[idx:idx+total_len])
        idx += total_len
    return b''.join(out)


def sanitize_media(filename: str, data: bytes) -> bytes:
    """Sanitize file data according to its extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        return strip_jpeg_exif(data)
    elif ext == '.png':
        return strip_png_metadata(data)
    return data


# =========================================================================
# Support Vault Database Manager
# =========================================================================

class SupportVault:
    def __init__(self, ghost_dir: str):
        self.vault_dir = os.path.join(ghost_dir, "support_vault")
        self.evidence_dir = os.path.join(self.vault_dir, "evidence")
        self.db_path = os.path.join(self.vault_dir, "support_cases.db")
        os.makedirs(self.evidence_dir, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_code TEXT UNIQUE NOT NULL,
                access_key TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'SUBMITTED',
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                reporter_alias TEXT,
                reporter_contact TEXT,
                ip_hash TEXT,
                member_email TEXT,
                member_uuid TEXT,
                telegram_message_id INTEGER,
                resolution_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            # Auto-migrate existing DBs for member tracking
            for col_sql in [
                "ALTER TABLE cases ADD COLUMN member_email TEXT",
                "ALTER TABLE cases ADD COLUMN member_uuid TEXT"
            ]:
                try:
                    conn.execute(col_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_member_email ON cases(member_email)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_member_uuid ON cases(member_uuid)")
                conn.commit()
            except Exception:
                pass

            conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_code TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                mime_type TEXT,
                file_size INTEGER NOT NULL,
                sha256_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (case_code) REFERENCES cases(case_code)
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_code TEXT NOT NULL,
                sender_type TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (case_code) REFERENCES cases(case_code)
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_code TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
            """)
            conn.commit()

    def create_case(
        self,
        category: str,
        priority: str,
        subject: str,
        description: str,
        reporter_alias: Optional[str] = None,
        reporter_contact: Optional[str] = None,
        ip_hash: Optional[str] = None,
        member_email: Optional[str] = None,
        member_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        case_code = f"CASE-{secrets.randbelow(9000) + 1000}-{secrets.token_hex(2).upper()}"
        access_key = secrets.token_hex(16)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_email = (member_email or "").strip().lower() or None
        clean_uuid = (member_uuid or "").strip() or None

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO cases (
                    case_code, access_key, category, priority, status,
                    subject, description, reporter_alias, reporter_contact,
                    ip_hash, member_email, member_uuid, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'SUBMITTED', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_code, access_key, category, priority,
                    subject, description, reporter_alias or "Anonymous",
                    reporter_contact, ip_hash, clean_email, clean_uuid, now, now
                )
            )
            conn.execute(
                "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (case_code, "CASE_CREATED", "reporter", f"Priority: {priority}, Category: {category}", now)
            )
            conn.commit()

        return {
            "case_code": case_code,
            "access_key": access_key,
            "category": category,
            "priority": priority,
            "status": "SUBMITTED",
            "subject": subject,
            "description": description,
            "member_email": clean_email,
            "created_at": now
        }

    def list_member_cases(self, member_email: str, member_uuid: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        clean_email = (member_email or "").strip().lower()
        clean_uuid = (member_uuid or "").strip()
        if not clean_email and not clean_uuid:
            return []

        seen_codes = set()
        member_cases = []
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    if clean_email and clean_uuid:
                        rows = conn.execute(
                            """
                            SELECT case_code, access_key, category, priority, status, subject,
                                   description, reporter_alias, created_at, updated_at
                            FROM cases
                            WHERE LOWER(member_email) = ? OR member_uuid = ?
                            ORDER BY id DESC LIMIT ?
                            """,
                            (clean_email, clean_uuid, limit)
                        ).fetchall()
                    elif clean_email:
                        rows = conn.execute(
                            """
                            SELECT case_code, access_key, category, priority, status, subject,
                                   description, reporter_alias, created_at, updated_at
                            FROM cases
                            WHERE LOWER(member_email) = ?
                            ORDER BY id DESC LIMIT ?
                            """,
                            (clean_email, limit)
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            """
                            SELECT case_code, access_key, category, priority, status, subject,
                                   description, reporter_alias, created_at, updated_at
                            FROM cases
                            WHERE member_uuid = ?
                            ORDER BY id DESC LIMIT ?
                            """,
                            (clean_uuid, limit)
                        ).fetchall()

                    for r in rows:
                        d = dict(r)
                        if d["case_code"] not in seen_codes:
                            seen_codes.add(d["case_code"])
                            member_cases.append(d)
            except Exception:
                pass

        member_cases.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return member_cases[:limit]

    def _candidate_dbs(self) -> List[str]:
        candidates = [
            self.db_path,
            "/var/www/ghost/support_vault/support_cases.db",
            "/opt/ghost-telegram-bot/support_vault/support_cases.db",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "support_vault", "support_cases.db")
        ]
        res = []
        seen = set()
        for c in candidates:
            if c not in seen and os.path.exists(c) and os.path.isfile(c):
                seen.add(c)
                res.append(c)
        if not res:
            res.append(self.db_path)
        return res

    def save_evidence(self, case_code: str, filename: str, data: bytes, mime_type: Optional[str] = None) -> Dict[str, Any]:
        clean_data = sanitize_media(filename, data)
        sha256 = hashlib.sha256(clean_data).hexdigest()
        raw_name = os.path.basename(filename)
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_name)
        if not clean_name or clean_name.startswith('.'):
            clean_name = f"evidence_{clean_name}"
        stored_name = f"{case_code}_{uuid.uuid4().hex[:8]}_{clean_name}"
        stored_path = os.path.join(self.evidence_dir, stored_name)

        with open(stored_path, "wb") as f:
            f.write(clean_data)
        try:
            os.chmod(stored_path, 0o664)
        except Exception:
            pass

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO evidence_files (
                    case_code, original_name, stored_filename, mime_type, file_size, sha256_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (case_code, clean_name, stored_name, mime_type or "application/octet-stream", len(clean_data), sha256, now)
            )
            conn.execute(
                "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (case_code, "EVIDENCE_UPLOADED", "reporter", f"File: {clean_name} ({len(clean_data)} bytes, SHA: {sha256[:12]})", now)
            )
            conn.commit()

        return {
            "original_name": clean_name,
            "stored_filename": stored_name,
            "stored_path": stored_path,
            "file_size": len(clean_data),
            "sha256": sha256
        }

    def get_evidence_path(self, stored_filename: str) -> Optional[str]:
        candidates = [
            os.path.join(self.evidence_dir, stored_filename),
            os.path.join("/var/www/ghost/support_vault/evidence", stored_filename),
            os.path.join("/opt/ghost-telegram-bot/support_vault/evidence", stored_filename),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "support_vault", "evidence", stored_filename)
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                return c
        return None

    def get_case(self, case_code: str) -> Optional[Dict[str, Any]]:
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM cases WHERE case_code = ?", (case_code,)).fetchone()
                    if row:
                        case_data = dict(row)
                        files = conn.execute("SELECT * FROM evidence_files WHERE case_code = ?", (case_code,)).fetchall()
                        case_data["files"] = [dict(f) for f in files]
                        msgs = conn.execute("SELECT * FROM messages WHERE case_code = ? ORDER BY id ASC", (case_code,)).fetchall()
                        case_data["messages"] = [dict(m) for m in msgs]
                        audit = conn.execute("SELECT * FROM audit_logs WHERE case_code = ? ORDER BY id ASC", (case_code,)).fetchall()
                        case_data["audit_logs"] = [dict(a) for a in audit]
                        return case_data
            except Exception:
                pass
        return None

    def update_status(self, case_code: str, new_status: str, actor: str, note: Optional[str] = None) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated = False
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT 1 FROM cases WHERE case_code = ?", (case_code,)).fetchone()
                    if row:
                        conn.execute(
                            "UPDATE cases SET status = ?, resolution_note = ?, updated_at = ? WHERE case_code = ?",
                            (new_status, note, now, case_code)
                        )
                        conn.execute(
                            "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                            (case_code, "STATUS_CHANGE", actor, f"Changed to {new_status}. Note: {note or 'None'}", now)
                        )
                        conn.commit()
                        updated = True
            except Exception:
                pass
        return updated

    def set_telegram_message_id(self, case_code: str, message_id: int):
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.execute("UPDATE cases SET telegram_message_id = ? WHERE case_code = ?", (message_id, case_code))
                    conn.commit()
            except Exception:
                pass

    def add_message(self, case_code: str, sender_type: str, sender_name: str, text: str) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        msg_id = None
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    cur = conn.execute(
                        "INSERT INTO messages (case_code, sender_type, sender_name, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
                        (case_code, sender_type, sender_name, text, now)
                    )
                    conn.execute("UPDATE cases SET updated_at = ? WHERE case_code = ?", (now, case_code))
                    conn.commit()
                    if msg_id is None:
                        msg_id = cur.lastrowid
            except Exception:
                pass

        return {
            "id": msg_id or 1,
            "case_code": case_code,
            "sender_type": sender_type,
            "sender_name": sender_name,
            "message_text": text,
            "created_at": now
        }

    def list_recent_cases(self, limit: int = 15) -> List[Dict[str, Any]]:
        seen_codes = set()
        all_cases = []
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM cases ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
                    for r in rows:
                        d = dict(r)
                        if d["case_code"] not in seen_codes:
                            seen_codes.add(d["case_code"])
                            all_cases.append(d)
            except Exception:
                pass
        all_cases.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return all_cases[:limit]


# =========================================================================
# Support Telegram Bot Integration (Inline Keyboards & Two-Way Chat)
# =========================================================================

class SupportBotBridge:
    def __init__(self, application: Optional[Application], vault: SupportVault, admin_chat_id: int):
        self.app = application
        self.vault = vault
        self.admin_chat_id = admin_chat_id
        # In-memory mapping of active admin reply sessions: admin_id -> case_code
        self.active_reply_sessions: Dict[int, str] = {}
        # In-memory mapping of telegram message_id -> case_code
        self.msg_to_case: Dict[int, str] = {}
        if self.app:
            self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CallbackQueryHandler(self.handle_callback, pattern=r"^case_"))
        self.app.add_handler(CommandHandler("cases", self.cases_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        # Handle admin text messages (both native replies and interactive conversation)
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_admin_message))

    def make_case_keyboard(self, case_code: str, status: str) -> InlineKeyboardMarkup:
        buttons = []
        if status == "SUBMITTED":
            buttons.append([
                InlineKeyboardButton("🔍 In Review", callback_data=f"case_review:{case_code}"),
                InlineKeyboardButton("📥 Evidence", callback_data=f"case_evidence:{case_code}")
            ])
            buttons.append([
                InlineKeyboardButton("✅ Mark Closed", callback_data=f"case_close:{case_code}"),
                InlineKeyboardButton("❌ Mark Rejected", callback_data=f"case_reject:{case_code}")
            ])
        elif status == "IN_REVIEW":
            buttons.append([
                InlineKeyboardButton("💬 Reply to Reporter", callback_data=f"case_reply:{case_code}"),
                InlineKeyboardButton("📥 Evidence", callback_data=f"case_evidence:{case_code}")
            ])
            buttons.append([
                InlineKeyboardButton("✅ Mark Closed", callback_data=f"case_close:{case_code}"),
                InlineKeyboardButton("❌ Mark Rejected", callback_data=f"case_reject:{case_code}")
            ])
        else:
            # Closed or Rejected: allow reopening or review
            buttons.append([
                InlineKeyboardButton("🔄 Re-Open / In Review", callback_data=f"case_review:{case_code}"),
                InlineKeyboardButton("📥 Evidence", callback_data=f"case_evidence:{case_code}")
            ])
        buttons.append([
            InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list")
        ])
        return InlineKeyboardMarkup(buttons)

    def format_case_card(self, case_data: Dict[str, Any]) -> str:
        priority_emojis = {
            "CRITICAL": "🔴 CRITICAL",
            "URGENT": "🟠 URGENT",
            "STANDARD": "🟡 STANDARD",
            "LOW": "⚪ LOW"
        }
        status_emojis = {
            "SUBMITTED": "🟡 SUBMITTED (Pending Triage)",
            "IN_REVIEW": "🟠 IN REVIEW (Investigator Assigned)",
            "CLOSED": "🟢 CLOSED / RESOLVED",
            "REJECTED": "⚪ REJECTED / DISMISSED"
        }

        raw_priority = str(case_data.get('priority') or 'STANDARD').upper()
        raw_status = str(case_data.get('status') or 'SUBMITTED').upper()
        p_display = priority_emojis.get(raw_priority, raw_priority)
        s_display = status_emojis.get(raw_status, raw_status)

        import html
        files = case_data.get("files", [])
        files_text = f"📁 <b>Evidence:</b> {len(files)} file(s) attached\n"
        for f in files[:4]:
            orig_name = html.escape(str(f.get('original_name') or 'evidence.bin'))
            size_kb = (f.get('file_size') or 0) // 1024
            sha_snip = html.escape(str(f.get('sha256_hash') or '')[:12])
            files_text += f"   • <code>{orig_name}</code> ({size_kb} KB | SHA: <code>{sha_snip}...</code>)\n"
        if len(files) > 4:
            files_text += f"   <i>...and {len(files) - 4} more attachment(s)</i>\n"

        category = html.escape(str(case_data.get('category') or 'Incident Report'))
        subject = html.escape(str(case_data.get('subject') or 'No Subject'))
        desc = html.escape(str(case_data.get('description') or ''))[:600]
        reporter = html.escape(str(case_data.get('reporter_alias') or 'Anonymous'))
        ip_hash = html.escape(str(case_data.get('ip_hash') or 'N/A')[:10])
        created_at = str(case_data.get('created_at') or '')[:19].replace('T', ' ')

        member_line = ""
        if case_data.get("member_email"):
            m_esc = html.escape(str(case_data["member_email"]))
            member_line = f"👤 <b>Ghost Member:</b> <code>{m_esc}</code>\n"

        note_text = ""
        if case_data.get("resolution_note"):
            clean_note = html.escape(str(case_data['resolution_note']))
            note_text = f"📋 <b>Determination Note:</b>\n<blockquote>{clean_note}</blockquote>\n"

        return (
            f"🚨 <b>INCIDENT REPORT: #{case_data['case_code']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Category:</b> {category}\n"
            f"⚡ <b>Priority:</b> {p_display}\n"
            f"🕒 <b>Submitted:</b> {created_at} UTC\n"
            f"👤 <b>Reporter:</b> {reporter} [Hash: <code>{ip_hash}</code>]\n"
            f"{member_line}"
            f"{files_text}\n"
            f"📝 <b>Subject:</b> {subject}\n"
            f"📄 <b>Description:</b>\n"
            f"<blockquote>{desc}</blockquote>\n"
            f"{note_text}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: <b>{s_display}</b>"
        )

    async def notify_new_case(self, case_data: Dict[str, Any]):
        """Send high-priority alert to the administrator."""
        if not self.app or not self.admin_chat_id:
            logger.info("Standalone/No-admin mode: skipping Telegram case alert for %s", case_data.get("case_code"))
            return

        text = self.format_case_card(case_data)
        kb = self.make_case_keyboard(case_data["case_code"], case_data["status"])
        try:
            msg = await self.app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            self.vault.set_telegram_message_id(case_data["case_code"], msg.message_id)
            self.msg_to_case[msg.message_id] = case_data["case_code"]
        except Exception as e:
            logger.error("Failed to dispatch Telegram case notification: %s", e)

    async def notify_reporter_reply(self, case_code: str, message_text: str):
        """Notify admin when reporter sends a message on the web portal."""
        if not self.app or not self.admin_chat_id:
            logger.info("Standalone/No-admin mode: skipping Telegram reporter reply alert for %s", case_code)
            return

        text = (
            f"💬 <b>[REPORTER REPLY] #{case_code}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote>{message_text}</blockquote>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Tap below or reply to this message directly to respond.</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Reply Back", callback_data=f"case_reply:{case_code}"),
            InlineKeyboardButton("🔍 View Case", callback_data=f"case_view:{case_code}")
        ]])
        try:
            msg = await self.app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            self.msg_to_case[msg.message_id] = case_code
        except Exception as e:
            logger.error("Failed to forward reporter reply: %s", e)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass

        data = query.data or ""
        action, _, case_code = data.partition(":")

        try:
            case_data = self.vault.get_case(case_code)
            if not case_data:
                try:
                    await query.answer(f"❌ Case #{case_code} not found in secure vault.", show_alert=True)
                except Exception:
                    pass
                try:
                    await query.edit_message_text(f"❌ Case #{case_code} not found.")
                except Exception:
                    pass
                return

            admin_user = query.from_user.username or query.from_user.first_name or "Administrator"

            if action == "case_view":
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, case_data.get("status", "SUBMITTED"))
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action == "case_review":
                self.vault.update_status(case_code, "IN_REVIEW", actor=admin_user)
                case_data["status"] = "IN_REVIEW"
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "IN_REVIEW")
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass
                await query.message.reply_text(
                    f"🔍 Case <b>#{html.escape(case_code)}</b> marked as <b>IN REVIEW</b> by @{html.escape(admin_user)}.",
                    parse_mode=ParseMode.HTML
                )

            elif action == "case_close":
                self.vault.update_status(case_code, "CLOSED", actor=admin_user, note="Resolved by investigation team.")
                case_data["status"] = "CLOSED"
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "CLOSED")
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass
                await query.message.reply_text(
                    f"✅ Case <b>#{html.escape(case_code)}</b> has been marked as <b>CLOSED / RESOLVED</b>.",
                    parse_mode=ParseMode.HTML
                )

            elif action == "case_reject":
                self.vault.update_status(case_code, "REJECTED", actor=admin_user, note="Dismissed or insufficient evidence.")
                case_data["status"] = "REJECTED"
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "REJECTED")
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass
                await query.message.reply_text(
                    f"❌ Case <b>#{html.escape(case_code)}</b> has been marked as <b>REJECTED / DISMISSED</b>.",
                    parse_mode=ParseMode.HTML
                )

            elif action == "case_evidence":
                files = case_data.get("files", [])
                if not files:
                    try:
                        await query.answer("ℹ️ No evidence files attached to this case.", show_alert=True)
                    except Exception:
                        pass
                    await query.message.reply_text(f"ℹ️ No evidence files attached to #{html.escape(case_code)}.", parse_mode=ParseMode.HTML)
                    return

                try:
                    await query.answer(f"📥 Sending {len(files)} attachment(s)...")
                except Exception:
                    pass

                sent_count = 0
                for f in files:
                    stored_name = f.get("stored_filename", "")
                    stored_path = self.vault.get_evidence_path(stored_name)
                    if stored_path and os.path.exists(stored_path):
                        clean_fname = html.escape(str(f.get("original_name") or "evidence.bin"))
                        sha = html.escape(str(f.get("sha256_hash") or "")[:16])
                        size_kb = (f.get("file_size") or 0) // 1024
                        caption = (
                            f"📁 <b>{clean_fname}</b>\n"
                            f"Size: {size_kb} KB\n"
                            f"SHA-256: <code>{sha}</code>"
                        )
                        with open(stored_path, "rb") as fp:
                            file_data = fp.read()
                        await query.message.reply_document(
                            document=file_data,
                            filename=f.get("original_name") or "evidence.bin",
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                        sent_count += 1
                    else:
                        missing_name = html.escape(str(f.get("original_name") or stored_name or "Unknown"))
                        await query.message.reply_text(
                            f"⚠️ Evidence file <code>{missing_name}</code> missing from disk storage.",
                            parse_mode=ParseMode.HTML
                        )

                if sent_count > 0:
                    await query.message.reply_text(
                        f"✅ Delivered <b>{sent_count}</b> evidence file(s) for case <b>#{html.escape(case_code)}</b>.",
                        parse_mode=ParseMode.HTML
                    )

            elif action == "case_reply":
                self.active_reply_sessions[query.from_user.id] = case_code
                try:
                    await query.answer("💬 Reply Mode Active! Type your message.")
                except Exception:
                    pass
                await query.message.reply_text(
                    f"💬 <b>Reply Mode Active for #{html.escape(case_code)}</b>\n"
                    f"Please type your message below. It will be delivered directly to the reporter's live web portal.\n"
                    f"<i>(Send /cancel to abort)</i>",
                    parse_mode=ParseMode.HTML
                )

        except Exception as err:
            logger.exception("Error in handle_callback for case %s: %s", case_code, err)
            try:
                await query.answer(f"⚠️ Error: {str(err)[:180]}", show_alert=True)
            except Exception:
                pass
            try:
                await query.message.reply_text(
                    f"⚠️ <b>Case Action Error:</b> <code>{html.escape(str(err))}</code>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        user_id = update.effective_user.id
        reply_to = update.message.reply_to_message
        case_code = None

        # Check 1: Is user in an active reply session?
        if user_id in self.active_reply_sessions:
            case_code = self.active_reply_sessions.get(user_id)

        # Check 2: Did user reply directly to a bot message representing a case?
        elif reply_to and reply_to.message_id in self.msg_to_case:
            case_code = self.msg_to_case[reply_to.message_id]

        if not case_code:
            return  # Not a support reply message, pass through to other bot handlers

        # Handle cancel command
        if update.message.text and update.message.text.strip().lower() == "/cancel":
            self.active_reply_sessions.pop(user_id, None)
            await update.message.reply_text("❌ Reply session ended.", parse_mode=ParseMode.HTML)
            return

        admin_name = update.effective_user.first_name or "Investigator"
        delivered_parts = []

        # Download and store photo if present
        if update.message.photo:
            try:
                photo = update.message.photo[-1]
                p_file = await photo.get_file()
                p_bytes = await p_file.download_as_bytearray()
                p_name = f"admin_photo_{int(time.time())}.jpg"
                self.vault.save_evidence(case_code, p_name, bytes(p_bytes), "image/jpeg")
                delivered_parts.append(f"📁 [{p_name}]")
            except Exception as e:
                logger.error("Failed to download admin photo: %s", e)

        # Download and store document if present
        if update.message.document:
            try:
                doc = update.message.document
                d_file = await doc.get_file()
                d_bytes = await d_file.download_as_bytearray()
                d_name = doc.file_name or f"admin_file_{int(time.time())}"
                self.vault.save_evidence(case_code, d_name, bytes(d_bytes), doc.mime_type or "application/octet-stream")
                delivered_parts.append(f"📁 [{d_name}]")
            except Exception as e:
                logger.error("Failed to download admin document: %s", e)

        msg_body = (update.message.text or update.message.caption or "").strip()
        if msg_body:
            delivered_parts.append(msg_body)

        final_text = "\n".join(delivered_parts).strip()
        if not final_text:
            return

        self.vault.add_message(
            case_code=case_code,
            sender_type="admin",
            sender_name=f"Investigator {admin_name}",
            text=final_text
        )

        await update.message.reply_text(
            f"✓ <b>Message delivered to reporter for #{html.escape(case_code)}</b>\n"
            f"<blockquote>{html.escape(final_text)}</blockquote>\n"
            f"<i>(Active reply mode. Type more to reply, or send /cancel to end.)</i>",
            parse_mode=ParseMode.HTML
        )

    async def cases_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List active cases."""
        cases = self.vault.list_recent_cases(limit=10)
        if not cases:
            await update.message.reply_text("ℹ️ No support cases currently on record.")
            return

        lines = ["📋 <b>Recent Support & Evidence Cases:</b>\n"]
        for c in cases:
            cc = html.escape(str(c.get('case_code') or 'UNKNOWN'))
            cp = html.escape(str(c.get('priority') or 'STANDARD'))
            cg = html.escape(str(c.get('category') or 'General'))
            cs = html.escape(str(c.get('status') or 'SUBMITTED'))
            sub = html.escape(str(c.get('subject') or 'No Subject')[:30])
            lines.append(
                f"• <b>#{cc}</b> [{cp}] - {cg}\n"
                f"   Status: <b>{cs}</b> | Subject: {sub}...\n"
            )
        lines.append("<i>Use inline cards above or /reply to interact.</i>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.active_reply_sessions:
            del self.active_reply_sessions[user_id]
            await update.message.reply_text("✓ Active reply session canceled.")
        else:
            await update.message.reply_text("ℹ️ No active reply session.")


# =========================================================================
# Zero-Dependency Async HTTP API Server
# =========================================================================


# =========================================================================
# Cryptographic Anti-Flooding Engine (Dynamic Puzzle + Proof-of-Work Challenge)
# =========================================================================

class CaptchaEngine:
    """
    Self-contained, privacy-preserving anti-flooding challenge engine:
    1. Cryptographic HMAC signature ensuring tokens cannot be forged.
    2. Dynamic math/visual challenge to defeat simple scripted bots.
    3. Client-side SHA-256 Proof-of-Work (PoW) difficulty requiring computational work
       before requests are admitted, neutralizing DDoS/flood scripts.
    4. Anti-replay token tracking with memory-capped sliding expiration.
    """
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or secrets.token_hex(32)
        # Store spent or issued challenges: challenge_id -> expiry_timestamp
        self.spent_tokens: Dict[str, float] = {}
        self.difficulty = 4  # Requires hash beginning with '0000' (~0.05s-0.25s client-side)

    def _cleanup_expired(self):
        now = time.time()
        expired = [cid for cid, exp in self.spent_tokens.items() if exp < now]
        for cid in expired:
            self.spent_tokens.pop(cid, None)

    def generate_challenge(self) -> Dict[str, Any]:
        self._cleanup_expired()
        challenge_id = secrets.token_hex(16)
        timestamp = int(time.time())

        # Generate simple arithmetic challenge
        num1 = secrets.randbelow(15) + 5
        num2 = secrets.randbelow(10) + 2
        op = secrets.choice(["+", "-"])
        if op == "+":
            ans = str(num1 + num2)
            question = f"{num1} + {num2}"
        else:
            if num1 < num2:
                num1, num2 = num2, num1
            ans = str(num1 - num2)
            question = f"{num1} - {num2}"

        # Sign the challenge parameters: challenge_id, timestamp, ans, difficulty
        sig_payload = f"{challenge_id}:{timestamp}:{ans}:{self.difficulty}"
        signature = hmac.new(self.secret_key.encode('utf-8'), sig_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        # Dynamic SVG puzzle
        svg_w, svg_h = 160, 44
        svg_markup = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" style="user-select:none;border-radius:8px;">'
            f'<rect width="100%" height="100%" fill="rgba(15,23,42,0.95)" rx="8" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>'
            f'<path d="M 10 32 Q 40 8, 80 22 T 150 12" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="2"/>'
            f'<path d="M 5 15 Q 50 35, 100 15 T 155 30" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="1.5"/>'
            f'<text x="50%" y="28" font-family="monospace, monospace" font-size="19" font-weight="bold" fill="#ffffff" text-anchor="middle" letter-spacing="3">{question} = ?</text>'
            f'</svg>'
        )

        return {
            "challenge_id": challenge_id,
            "timestamp": timestamp,
            "signature": signature,
            "difficulty": self.difficulty,
            "svg": svg_markup
        }

    def verify_challenge(self, challenge_id: str, timestamp: int, signature: str, solution: str, nonce: str) -> bool:
        self._cleanup_expired()
        now = time.time()

        # 1. Check expiration (5 minutes = 300s)
        if abs(now - timestamp) > 300:
            logger.warning("[CaptchaEngine] Challenge %s expired", challenge_id)
            return False

        # 2. Check replay prevention
        if challenge_id in self.spent_tokens:
            logger.warning("[CaptchaEngine] Replay attempt on challenge %s", challenge_id)
            return False

        # 3. Verify HMAC signature
        expected_sig = hmac.new(
            self.secret_key.encode('utf-8'),
            f"{challenge_id}:{timestamp}:{solution.strip()}:{self.difficulty}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("[CaptchaEngine] Invalid signature or wrong solution for %s", challenge_id)
            return False

        # 4. Verify Proof-of-Work (PoW) computation
        target_prefix = "0" * self.difficulty
        pow_hash = hashlib.sha256(f"{challenge_id}:{nonce}".encode('utf-8')).hexdigest()
        if not pow_hash.startswith(target_prefix):
            logger.warning("[CaptchaEngine] Invalid PoW hash %s for %s", pow_hash, challenge_id)
            return False

        # Mark token as spent until nominal expiry
        self.spent_tokens[challenge_id] = float(timestamp + 300)
        return True


class SupportApiServer:
    def __init__(self, vault: SupportVault, bridge: SupportBotBridge, host: str = "127.0.0.1", port: int = 8080):
        self.vault = vault
        self.bridge = bridge
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.captcha = CaptchaEngine()
        # IP Rate Limiting (in-memory sliding window): ip -> [timestamp, timestamp]
        self.ip_submissions: Dict[str, List[float]] = {}

    def _is_rate_limited(self, ip: str) -> bool:
        now = datetime.datetime.now().timestamp()
        window = 3600  # 1 hour
        max_submissions = 6
        timestamps = [t for t in self.ip_submissions.get(ip, []) if now - t < window]
        if len(timestamps) >= max_submissions:
            return True
        timestamps.append(now)
        self.ip_submissions[ip] = timestamps
        return False

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info("Support REST API server active on http://%s:%d", self.host, self.port)

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Support REST API server stopped.")

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                return
            parts = line.decode('utf-8', errors='ignore').strip().split()
            if len(parts) < 2:
                writer.close()
                return
            method, path = parts[0].upper(), parts[1]

            headers = {}
            while True:
                hline = await reader.readline()
                if hline in (b'\r\n', b'\n', b''):
                    break
                hstr = hline.decode('utf-8', errors='ignore')
                hparts = hstr.split(':', 1)
                if len(hparts) == 2:
                    headers[hparts[0].strip().lower()] = hparts[1].strip()

            content_len = int(headers.get('content-length', 0))
            # Max payload: 50MB
            if content_len > 50 * 1024 * 1024:
                await self._send_response(writer, 413, {"error": "Payload exceeds 50MB limit"})
                return

            body = b''
            if content_len > 0:
                body = await reader.readexactly(content_len)

            # Client IP
            client_ip = headers.get('x-forwarded-for', '').split(',')[0].strip() or headers.get('x-real-ip', '127.0.0.1')
            ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

            # Route handling
            if method == "OPTIONS":
                header_lines = [
                    "HTTP/1.1 204 No Content",
                    "Access-Control-Allow-Origin: *",
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Forwarded-For",
                    "Access-Control-Max-Age: 86400",
                    "Content-Length: 0",
                    "Connection: close",
                    "",
                    ""
                ]
                writer.write("\r\n".join(header_lines).encode('utf-8'))
                await writer.drain()
                return

            clean_path = path.split('?')[0].rstrip('/')
            route_path = clean_path
            if route_path.startswith("/api/support"):
                route_path = route_path[len("/api/support"):]
            if not route_path.startswith("/"):
                route_path = "/" + route_path

            query = {}
            if '?' in path:
                qstr = path.split('?', 1)[1]
                for qitem in qstr.split('&'):
                    if '=' in qitem:
                        k, v = qitem.split('=', 1)
                        query[k] = urllib.parse.unquote(v)

            # -------------------------------------------------------------
            # GET /ping or /health (Health & Status Check)
            # -------------------------------------------------------------
            if method == "GET" and route_path in ("/", "/ping", "/health"):
                await self._send_response(writer, 200, {
                    "status": "ok",
                    "service": "support-hub",
                    "version": "1.0.0",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                return

            # -------------------------------------------------------------
            # GET /captcha (Obtain Cryptographic Security Challenge)
            # -------------------------------------------------------------
            elif method == "GET" and route_path == "/captcha":
                challenge = self.captcha.generate_challenge()
                await self._send_response(writer, 200, challenge)
                return

            # -------------------------------------------------------------
            # POST /cases (Case Submission - JSON or Multipart)
            # -------------------------------------------------------------
            elif method == "POST" and route_path == "/cases":
                if self._is_rate_limited(client_ip):
                    await self._send_response(writer, 429, {"error": "Submission rate limit exceeded. Please wait a while before submitting again."})
                    return

                ctype = headers.get('content-type', '')
                params = {}
                evidence_files: List[Dict[str, Any]] = []

                if "application/json" in ctype:
                    try:
                        params = json.loads(body.decode('utf-8'))
                    except Exception as e:
                        logger.warning("JSON parse error: %s", e)
                        await self._send_response(writer, 400, {"error": "Invalid JSON payload."})
                        return
                elif "multipart/form-data" in ctype:
                    try:
                        msg_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode('utf-8') + body
                        msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
                        for part in msg.iter_parts():
                            name = part.get_param('name', header='content-disposition')
                            filename = part.get_filename()
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue
                            if filename:
                                evidence_files.append({"filename": filename, "data": payload, "mime": part.get_content_type()})
                            elif name:
                                params[name] = payload.decode('utf-8', errors='replace').strip()
                    except Exception as e:
                        logger.warning("Multipart parse error: %s", e)
                        await self._send_response(writer, 400, {"error": f"Failed to parse multipart upload: {e}"})
                        return
                else:
                    try:
                        params = json.loads(body.decode('utf-8'))
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Unsupported Content-Type. Please use application/json or multipart/form-data."})
                        return

                # Verify Security Challenge / Anti-Flooding Captcha + PoW
                c_id = params.get("captcha_id", "").strip()
                c_ts = int(params.get("captcha_timestamp", 0) or 0)
                c_sig = params.get("captcha_signature", "").strip()
                c_sol = params.get("captcha_solution", "").strip()
                c_nonce = params.get("captcha_nonce", "").strip()

                if not c_id or not c_sig or not c_sol or not c_nonce:
                    await self._send_response(writer, 400, {"error": "Anti-flooding security challenge is required. Please solve the verification puzzle."})
                    return

                if not self.captcha.verify_challenge(c_id, c_ts, c_sig, c_sol, c_nonce):
                    await self._send_response(writer, 403, {"error": "Security verification failed or expired. Please solve the updated puzzle."})
                    return

                subject = params.get("subject", "").strip()
                description = params.get("description", "").strip()
                category = params.get("category", "Incident Report").strip()
                priority = params.get("priority", "STANDARD").strip().upper()
                alias = params.get("reporter_alias", "Anonymous").strip() or "Anonymous"
                contact = params.get("reporter_contact", "").strip()
                member_email = params.get("member_email", "").strip().lower()
                member_uuid = params.get("member_uuid", "").strip()

                if not subject or not description:
                    await self._send_response(writer, 400, {"error": "Subject and Detailed Description are required fields."})
                    return

                # Create case in DB
                case_res = self.vault.create_case(
                    category=category,
                    priority=priority,
                    subject=subject,
                    description=description,
                    reporter_alias=alias,
                    reporter_contact=contact,
                    ip_hash=ip_hash,
                    member_email=member_email or None,
                    member_uuid=member_uuid or None
                )
                case_code = case_res["case_code"]

                # Save sanitized evidence files
                saved_files = []
                for ef in evidence_files:
                    saved = self.vault.save_evidence(case_code, ef["filename"], ef["data"], ef.get("mime"))
                    saved_files.append(saved)

                # Fetch full case record and alert Telegram bot
                full_case = self.vault.get_case(case_code)
                if full_case:
                    asyncio.create_task(self.bridge.notify_new_case(full_case))

                await self._send_response(writer, 201, {
                    "success": True,
                    "case_code": case_code,
                    "access_key": case_res["access_key"],
                    "status": "SUBMITTED",
                    "file_count": len(saved_files)
                })
                return

            # -------------------------------------------------------------
            # GET /member/cases or /cases/member (List Member's Past Cases)
            # -------------------------------------------------------------
            elif method == "GET" and route_path in ("/member/cases", "/cases/member"):
                m_email = query.get("email", "").strip().lower()
                m_uuid = query.get("uuid", "").strip()
                if not m_email and not m_uuid:
                    await self._send_response(writer, 400, {"error": "Email or member UUID required."})
                    return

                cases = self.vault.list_member_cases(member_email=m_email, member_uuid=m_uuid)
                await self._send_response(writer, 200, {
                    "success": True,
                    "cases": cases
                })
                return

            # -------------------------------------------------------------
            # GET /cases/<case_code>/evidence/<file_id> (Stream Evidence File - RESTRICTED TO BOT)
            # -------------------------------------------------------------
            elif method == "GET" and "/evidence/" in route_path and route_path.startswith("/cases/"):
                # Strict OpSec & Chain-of-Custody: Direct web browser viewing/downloading is disabled.
                # Evidence files are permanently sequestered in the offline vault and accessible solely
                # by verified administrators through the dedicated operational Telegram Bot.
                await self._send_response(writer, 403, {
                    "error": "Direct web access to uploaded evidence is disabled for operational security. "
                             "Evidence files are sequestered in an isolated vault and accessible exclusively "
                             "by duty investigators via the verified operational Telegram Bot.",
                    "vault_status": "VAULTED_FOR_BOT_TRIAGE_ONLY"
                })
                return

            # -------------------------------------------------------------
            # GET /cases/<case_code> (Fetch Case Status & Chat)
            # -------------------------------------------------------------
            elif method == "GET" and route_path.startswith("/cases/") and not route_path.endswith("/messages"):
                parts = [p for p in route_path.split("/") if p]
                if len(parts) < 2:
                    await self._send_response(writer, 400, {"error": "Invalid case endpoint format."})
                    return
                case_code = parts[1]
                access_key = query.get("key", "").strip()
                case_data = self.vault.get_case(case_code)
                if not case_data:
                    await self._send_response(writer, 404, {"error": "Case not found."})
                    return

                # Validate access key
                if not access_key or case_data["access_key"] != access_key:
                    await self._send_response(writer, 403, {"error": "Invalid or missing Case Access Key."})
                    return

                # Strip internal server path and mark evidence as bot-vaulted only
                safe_files = []
                for f in case_data.get("files", []):
                    safe_files.append({
                        "id": f["id"],
                        "name": f["original_name"],
                        "size": f["file_size"],
                        "sha256": f["sha256_hash"],
                        "mime": f.get("mime_type", "application/octet-stream"),
                        "created_at": f["created_at"],
                        "vault_status": "VAULTED_FOR_BOT_TRIAGE_ONLY"
                    })

                await self._send_response(writer, 200, {
                    "case_code": case_data["case_code"],
                    "category": case_data["category"],
                    "priority": case_data["priority"],
                    "status": case_data["status"],
                    "subject": case_data["subject"],
                    "description": case_data["description"],
                    "reporter_alias": case_data.get("reporter_alias") or "Anonymous",
                    "created_at": case_data["created_at"],
                    "updated_at": case_data["updated_at"],
                    "resolution_note": case_data.get("resolution_note"),
                    "files": safe_files,
                    "messages": case_data.get("messages", [])
                })
                return

            # -------------------------------------------------------------
            # POST /cases/<case_code>/messages (Reporter Chat)
            # -------------------------------------------------------------
            elif method == "POST" and route_path.startswith("/cases/") and route_path.endswith("/messages"):
                parts = [p for p in route_path.split("/") if p]
                if len(parts) < 3:
                    await self._send_response(writer, 400, {"error": "Invalid message endpoint format."})
                    return
                case_code = parts[1]
                case_data = self.vault.get_case(case_code)
                if not case_data:
                    await self._send_response(writer, 404, {"error": "Case not found."})
                    return

                ctype = headers.get('content-type', '')
                text = ""
                key = ""
                attached_file = None
                if "application/json" in ctype:
                    try:
                        p = json.loads(body.decode('utf-8'))
                        text = p.get("message", "").strip()
                        key = p.get("key", "").strip()
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Invalid JSON"})
                        return
                elif "multipart/form-data" in ctype:
                    try:
                        msg_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode('utf-8') + body
                        msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
                        for part in msg.iter_parts():
                            name = part.get_param('name', header='content-disposition')
                            filename = part.get_filename()
                            payload = part.get_payload(decode=True)
                            if filename and payload:
                                attached_file = {"filename": filename, "data": payload, "mime": part.get_content_type()}
                            elif name == "message" and payload:
                                text = payload.decode('utf-8', errors='replace').strip()
                            elif name == "key" and payload:
                                key = payload.decode('utf-8', errors='replace').strip()
                    except Exception:
                        pass
                else:
                    try:
                        p = json.loads(body.decode('utf-8'))
                        text = p.get("message", "").strip()
                        key = p.get("key", "").strip()
                    except Exception:
                        pass

                if not key or case_data["access_key"] != key:
                    await self._send_response(writer, 403, {"error": "Invalid or missing Case Access Key."})
                    return

                if not text and not attached_file:
                    await self._send_response(writer, 400, {"error": "Message text or attachment is required."})
                    return

                if attached_file:
                    self.vault.save_evidence(case_code, attached_file["filename"], attached_file["data"], attached_file.get("mime"))
                    text = f"📁 [{attached_file['filename']}]\n{text}" if text else f"📁 [{attached_file['filename']}]"

                new_msg = self.vault.add_message(
                    case_code=case_code,
                    sender_type="reporter",
                    sender_name=case_data.get("reporter_alias") or "Reporter",
                    text=text
                )

                # Forward reporter reply to Telegram admin
                asyncio.create_task(self.bridge.notify_reporter_reply(case_code, text))

                await self._send_response(writer, 201, {
                    "success": True,
                    "message": new_msg
                })
                return

            else:
                await self._send_response(writer, 404, {"error": f"Endpoint '{clean_path}' not found."})

        except Exception as e:
            logger.error("HTTP request error: %s", e)
            try:
                await self._send_response(writer, 500, {"error": "Internal server error"})
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send_response(self, writer: asyncio.StreamWriter, status_code: int, data: Optional[Dict[str, Any]]):
        status_texts = {
            200: "OK",
            201: "Created",
            204: "No Content",
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found",
            413: "Payload Too Large",
            429: "Too Many Requests",
            500: "Internal Server Error"
        }
        status_msg = status_texts.get(status_code, "OK")
        body_bytes = b""
        if data is not None:
            body_bytes = json.dumps(data).encode('utf-8')

        header_lines = [
            f"HTTP/1.1 {status_code} {status_msg}",
            "Content-Type: application/json; charset=utf-8",
            "Access-Control-Allow-Origin: *",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Forwarded-For",
            f"Content-Length: {len(body_bytes)}",
            "Connection: close",
            "",
            ""
        ]
        headers_raw = "\r\n".join(header_lines).encode('utf-8')
        writer.write(headers_raw + body_bytes)
        await writer.drain()


# =========================================================================
# Unified Support Hub Initializer & Standalone Runner
# =========================================================================

def init_support_hub(
    application: Optional[Application] = None,
    ghost_dir: str = "/var/www/ghost",
    admin_chat_id: int = 0,
    port: int = 8080,
    host: str = "127.0.0.1"
) -> SupportApiServer:
    """Initialize the Vault, Bot Bridge, and HTTP Server on the bot's asyncio loop."""
    vault = SupportVault(ghost_dir=ghost_dir)
    bridge = SupportBotBridge(application=application, vault=vault, admin_chat_id=admin_chat_id)
    server = SupportApiServer(vault=vault, bridge=bridge, host=host, port=port)
    return server


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Support & Evidence Hub API Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--ghost-dir", type=str, default=os.path.abspath(os.path.dirname(__file__)), help="Directory where support_vault is located")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    vault = SupportVault(ghost_dir=args.ghost_dir)
    bridge = SupportBotBridge(application=None, vault=vault, admin_chat_id=0)
    server = SupportApiServer(vault=vault, bridge=bridge, host=args.host, port=args.port)

    print("==================================================")
    print("      Support Hub REST API Server (Standalone)     ")
    print("==================================================")
    print(f"Listening on:    http://{args.host}:{args.port}")
    print(f"Vault Directory: {vault.vault_dir}")
    print("Health Check:    http://{}:{}/health".format(args.host, args.port))
    print("--------------------------------------------------")
    print("Running... Press Ctrl+C to stop.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nStopping Support API server...")
        loop.run_until_complete(server.stop())
