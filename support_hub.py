from __future__ import annotations
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
import urllib.request
import time
from typing import Optional, Dict, Any, List, Tuple, Set, Callable
from email import policy
from email.parser import BytesParser

try:
    from telegram import (
        Update,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        WebAppInfo,
        MenuButtonWebApp,
        MenuButtonDefault,
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
    HAS_TELEGRAM = True
except (ImportError, ModuleNotFoundError):
    HAS_TELEGRAM = False
    Update = Any  # type: ignore
    InlineKeyboardButton = Any  # type: ignore
    InlineKeyboardMarkup = Any  # type: ignore
    WebAppInfo = Any  # type: ignore
    MenuButtonWebApp = Any  # type: ignore
    MenuButtonDefault = Any  # type: ignore
    class ParseMode:  # type: ignore
        HTML = "HTML"
        MARKDOWN = "Markdown"
        MARKDOWN_V2 = "MarkdownV2"
    Application = Any  # type: ignore
    CallbackQueryHandler = Any  # type: ignore
    MessageHandler = Any  # type: ignore
    CommandHandler = Any  # type: ignore
    ContextTypes = Any  # type: ignore
    filters = Any  # type: ignore

logger = logging.getLogger("support-hub")


class EvidenceTooLargeError(Exception):
    """Raised when an evidence file exceeds Telegram Bot API getFile download limits."""
    pass

# =========================================================================
# OpSec & Metadata Scrubbing (Pure Python, Zero External C Dependencies)
# =========================================================================

def strip_jpeg_exif(data: bytes) -> bytes:
    """Strip EXIF/XMP/GPS (APP1), IPTC (APP13), non-essential APPn, and COM markers from JPEG bytes."""
    if not data.startswith(b'\xff\xd8'):
        return data
    out = [b'\xff\xd8']
    idx = 2
    length = len(data)
    # Preserve JFIF (0xFFE0) and ICC profile (0xFFE2); drop APP1, APP3..APP15, and COM (0xFFFE)
    drop_markers = {b'\xff\xe1', b'\xff\xfe'} | {bytes([0xff, m]) for m in range(0xe3, 0xf0)}
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
        if marker == b'\xff\xda':  # Start of Scan — remaining bytes are compressed image stream
            out.append(data[idx:])
            break
        if idx + 4 > length:
            out.append(data[idx:])
            break
        seg_len = int.from_bytes(data[idx+2:idx+4], 'big')
        if seg_len < 2 or idx + 2 + seg_len > length:
            out.append(data[idx:])
            break
        if marker not in drop_markers:
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


def strip_webp_metadata(data: bytes) -> bytes:
    """Strip EXIF and XMP RIFF chunks from WebP images."""
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return data
    chunks: List[bytes] = []
    idx = 12
    length = len(data)
    drop_fourcc = {b'EXIF', b'XMP '}
    while idx + 8 <= length:
        fourcc = data[idx:idx+4]
        chunk_size = struct.unpack('<I', data[idx+4:idx+8])[0]
        padded_size = chunk_size + (chunk_size & 1)
        end_idx = idx + 8 + padded_size
        if end_idx > length:
            chunks.append(data[idx:])
            break
        if fourcc not in drop_fourcc:
            if fourcc == b'VP8X' and chunk_size >= 10:
                payload = bytearray(data[idx+8:idx+8+chunk_size])
                payload[0] &= ~(0x08 | 0x04)
                pad = b'\x00' if (chunk_size & 1) else b''
                chunks.append(fourcc + struct.pack('<I', chunk_size) + bytes(payload) + pad)
            else:
                chunks.append(data[idx:end_idx])
        idx = end_idx
    body = b'WEBP' + b''.join(chunks)
    return b'RIFF' + struct.pack('<I', len(body)) + body


def sanitize_media(filename: str, data: bytes) -> bytes:
    """Sanitize file data according to its extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.jpg', '.jpeg') or data.startswith(b'\xff\xd8'):
        return strip_jpeg_exif(data)
    elif ext == '.png' or data.startswith(b'\x89PNG\r\n\x1a\n'):
        return strip_png_metadata(data)
    elif ext == '.webp' or (len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
        return strip_webp_metadata(data)
    return data


# =========================================================================
# Support Vault Database Manager
# =========================================================================

class SupportVault:
    ALLOWED_EVIDENCE_EXTS: Set[str] = {
        '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic', '.heif',
        '.pdf', '.txt', '.log', '.csv', '.json', '.eml',
        '.mp4', '.mov', '.webm', '.mp3', '.wav', '.ogg', '.m4a', '.zip'
    }

    def __init__(self, ghost_dir: str):
        self.ghost_dir = ghost_dir
        self.vault_dir = os.path.join(ghost_dir, "support_vault")
        self.evidence_dir = os.path.join(self.vault_dir, "evidence")
        self.db_path = os.path.join(self.vault_dir, "support_cases.db")
        os.makedirs(self.vault_dir, mode=0o700, exist_ok=True)
        os.makedirs(self.evidence_dir, mode=0o700, exist_ok=True)
        for dpath in (self.vault_dir, self.evidence_dir):
            try:
                os.chmod(dpath, 0o700)
            except Exception:
                pass
        self._init_db()
        for fpath in (self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"):
            if os.path.exists(fpath):
                try:
                    os.chmod(fpath, 0o600)
                except Exception:
                    pass

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
            conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_read_state (
                case_code TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                last_read_msg_id INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (case_code, admin_id)
            )
            """)
            # Auto-migrate existing DBs for member tracking, assignment, & Telegram metadata
            for col_sql in [
                "ALTER TABLE cases ADD COLUMN member_email TEXT",
                "ALTER TABLE cases ADD COLUMN member_uuid TEXT",
                "ALTER TABLE cases ADD COLUMN telegram_message_id INTEGER",
                "ALTER TABLE cases ADD COLUMN assigned_admin_id INTEGER",
                "ALTER TABLE cases ADD COLUMN assigned_admin_name TEXT",
                "ALTER TABLE evidence_files ADD COLUMN telegram_file_id TEXT",
                "ALTER TABLE evidence_files ADD COLUMN telegram_message_id INTEGER",
                "ALTER TABLE evidence_files ADD COLUMN telegram_chat_id INTEGER",
                "ALTER TABLE evidence_files ADD COLUMN telegram_file_unique_id TEXT",
            ]:
                try:
                    conn.execute(col_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_member_email ON cases(member_email)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_member_uuid ON cases(member_uuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_tg_msg ON cases(telegram_message_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence_files(case_code)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_case_id ON messages(case_code, id)")
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
                telegram_file_id TEXT,
                telegram_message_id INTEGER,
                telegram_chat_id INTEGER,
                telegram_file_unique_id TEXT,
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
        # Security: Mandate BOTH verified member_uuid and member_email; never expose access_key in bulk lists
        if not clean_uuid or not clean_email:
            return []

        seen_codes = set()
        member_cases = []
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT case_code, category, priority, status, subject,
                               description, reporter_alias, created_at, updated_at
                        FROM cases
                        WHERE member_uuid = ? AND LOWER(member_email) = ?
                        ORDER BY id DESC LIMIT ?
                        """,
                        (clean_uuid, clean_email, limit)
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
        default_dirs = {
            os.path.abspath("/var/www/ghost"),
            os.path.abspath("/opt/ghost-telegram-bot"),
            os.path.abspath(os.path.dirname(os.path.abspath(__file__))),
        }
        if os.path.abspath(self.ghost_dir) not in default_dirs:
            return [self.db_path]

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

    def save_evidence(
        self,
        case_code: str,
        filename: str,
        data: bytes,
        mime_type: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
        telegram_message_id: Optional[int] = None,
        telegram_chat_id: Optional[int] = None,
        telegram_file_unique_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_data = sanitize_media(filename, data)
        sha256 = hashlib.sha256(clean_data).hexdigest()
        raw_name = os.path.basename(filename or "evidence")
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_name)[:120]
        if not clean_name or clean_name.startswith('.'):
            clean_name = f"evidence_{clean_name}"

        # Enforce strict evidence extension allowlist (MED-05 / SEC-05)
        root_name, ext = os.path.splitext(clean_name)
        if not ext or ext.lower() not in self.ALLOWED_EVIDENCE_EXTS:
            ext_label = ext.lstrip('.') or 'bin'
            clean_name = f"{root_name[:96]}_{ext_label}.blocked"
            mime_type = "application/octet-stream"

        stored_name = f"{case_code}_{uuid.uuid4().hex[:8]}_{clean_name}"
        stored_path = ""

        # Only write to local VPS disk if NOT stored directly in Telegram Storage Group
        if not telegram_file_id:
            stored_path = os.path.join(self.evidence_dir, stored_name)
            with open(stored_path, "wb") as f:
                f.write(clean_data)
            try:
                os.chmod(stored_path, 0o600)
            except Exception:
                pass
        else:
            stored_path = f"telegram://{telegram_chat_id}/{telegram_message_id}"

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO evidence_files (
                    case_code, original_name, stored_filename, mime_type, file_size, sha256_hash, created_at,
                    telegram_file_id, telegram_message_id, telegram_chat_id, telegram_file_unique_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_code,
                    clean_name,
                    stored_name,
                    mime_type or "application/octet-stream",
                    len(clean_data),
                    sha256,
                    now,
                    telegram_file_id,
                    telegram_message_id,
                    telegram_chat_id,
                    telegram_file_unique_id
                )
            )
            audit_dest = (
                f"Telegram Storage Group [Chat: {telegram_chat_id}, Msg: {telegram_message_id}]"
                if telegram_file_id else "Local VPS Vault"
            )
            conn.execute(
                "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (case_code, "EVIDENCE_UPLOADED", "reporter", f"File: {clean_name} ({len(clean_data)} bytes, SHA: {sha256[:12]}) -> {audit_dest}", now)
            )
            conn.commit()

        return {
            "original_name": clean_name,
            "stored_filename": stored_name,
            "stored_path": stored_path,
            "file_size": len(clean_data),
            "sha256": sha256,
            "telegram_file_id": telegram_file_id,
            "telegram_message_id": telegram_message_id,
            "telegram_chat_id": telegram_chat_id,
            "telegram_file_unique_id": telegram_file_unique_id
        }

    def get_evidence_path(self, stored_filename: str) -> Optional[str]:
        # Guard against path traversal in stored_filename
        clean_stored = os.path.basename(stored_filename)
        candidates = [
            os.path.join(self.evidence_dir, clean_stored),
            os.path.join("/var/www/ghost/support_vault/evidence", clean_stored),
            os.path.join("/opt/ghost-telegram-bot/support_vault/evidence", clean_stored),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "support_vault", "evidence", clean_stored)
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                return c
        return None

    def get_case_by_telegram_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Resolve a case by its Telegram message ID across candidate DBs."""
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT case_code FROM cases WHERE telegram_message_id = ?", (message_id,)).fetchone()
                    if row:
                        return self.get_case(row["case_code"])
            except Exception:
                pass
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

    def get_messages(self, case_code: str) -> List[Dict[str, Any]]:
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM messages WHERE case_code = ? ORDER BY id ASC", (case_code,)).fetchall()
                    if rows:
                        return [dict(r) for r in rows]
            except Exception:
                pass
        return []

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

    def delete_case(self, case_code: str) -> Optional[Dict[str, Any]]:
        """Permanently delete a support case and its child records/files across vault DBs."""
        clean_code = (case_code or "").strip().lstrip("#").upper()
        if not clean_code or not re.fullmatch(r"[A-Z0-9-]+", clean_code):
            return None

        deleted = False
        ops_msg_ids: List[int] = []
        tg_evidence_msgs: List[Tuple[int, int]] = []
        local_filenames: List[str] = []

        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    case_row = conn.execute(
                        "SELECT case_code, telegram_message_id FROM cases WHERE case_code = ?",
                        (clean_code,)
                    ).fetchone()
                    if not case_row:
                        continue
                    deleted = True
                    if case_row["telegram_message_id"]:
                        ops_msg_ids.append(int(case_row["telegram_message_id"]))

                    ev_rows = conn.execute(
                        "SELECT stored_filename, telegram_chat_id, telegram_message_id FROM evidence_files WHERE case_code = ?",
                        (clean_code,)
                    ).fetchall()
                    for ev in ev_rows:
                        if ev["stored_filename"]:
                            local_filenames.append(str(ev["stored_filename"]))
                        if ev["telegram_chat_id"] and ev["telegram_message_id"]:
                            tg_evidence_msgs.append((int(ev["telegram_chat_id"]), int(ev["telegram_message_id"])))

                    conn.execute("DELETE FROM evidence_files WHERE case_code = ?", (clean_code,))
                    conn.execute("DELETE FROM messages WHERE case_code = ?", (clean_code,))
                    conn.execute("DELETE FROM audit_logs WHERE case_code = ?", (clean_code,))
                    conn.execute("DELETE FROM cases WHERE case_code = ?", (clean_code,))
                    conn.commit()
            except Exception as e:
                logger.error("Failed deleting case %s from %s: %s", clean_code, db, e)

        if not deleted:
            return None

        for fn in local_filenames:
            try:
                p = self.get_evidence_path(fn)
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

        return {
            "case_code": clean_code,
            "ops_telegram_message_ids": ops_msg_ids,
            "evidence_tg_messages": tg_evidence_msgs,
        }

    def list_cases_admin(
        self,
        status: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 80,
        viewer_admin_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List support cases across vault DBs with unread/message/evidence counts (no access_key/ip_hash)."""
        clean_status = (status or "").strip().upper()
        if clean_status == "ALL":
            clean_status = ""
        clean_q = (q or "").strip().lower()
        seen_codes: Set[str] = set()
        results: List[Dict[str, Any]] = []

        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    has_read_tbl = bool(
                        conn.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_read_state'"
                        ).fetchone()
                    )
                    cols = {r[1] for r in conn.execute("PRAGMA table_info(cases)").fetchall()}
                    has_assign = "assigned_admin_id" in cols and "assigned_admin_name" in cols
                    assign_sel = "c.assigned_admin_id, c.assigned_admin_name" if has_assign else "NULL AS assigned_admin_id, NULL AS assigned_admin_name"
                    read_join = (
                        "LEFT JOIN admin_read_state r ON r.case_code = c.case_code AND r.admin_id = ?"
                        if (has_read_tbl and viewer_admin_id)
                        else ""
                    )
                    read_sel = (
                        "COALESCE(r.last_read_msg_id, 0) AS last_read_msg_id"
                        if (has_read_tbl and viewer_admin_id)
                        else "0 AS last_read_msg_id"
                    )
                    sql = f"""
                        SELECT
                            c.case_code, c.category, c.priority, c.status, c.subject,
                            c.description, c.reporter_alias, c.reporter_contact,
                            c.member_email, c.resolution_note, c.created_at, c.updated_at,
                            {assign_sel},
                            {read_sel},
                            (SELECT COUNT(*) FROM evidence_files ef WHERE ef.case_code = c.case_code) AS file_count,
                            (SELECT COUNT(*) FROM messages m WHERE m.case_code = c.case_code) AS msg_count,
                            (SELECT COALESCE(MAX(m.id), 0) FROM messages m WHERE m.case_code = c.case_code) AS last_msg_id,
                            (SELECT m.sender_type FROM messages m WHERE m.case_code = c.case_code ORDER BY m.id DESC LIMIT 1) AS last_sender_type,
                            (SELECT m.message_text FROM messages m WHERE m.case_code = c.case_code ORDER BY m.id DESC LIMIT 1) AS last_message_text
                        FROM cases c
                        {read_join}
                        ORDER BY COALESCE(c.updated_at, c.created_at) DESC
                        LIMIT ?
                    """
                    args: Tuple[Any, ...] = (int(viewer_admin_id), limit * 2) if (has_read_tbl and viewer_admin_id) else (limit * 2,)
                    rows = conn.execute(sql, args).fetchall()
                    for r in rows:
                        d = dict(r)
                        cc = d.get("case_code")
                        if not cc or cc in seen_codes:
                            continue
                        if clean_status and str(d.get("status") or "").upper() != clean_status:
                            continue
                        if clean_q:
                            hay = " ".join([
                                str(cc),
                                str(d.get("subject") or ""),
                                str(d.get("category") or ""),
                                str(d.get("reporter_alias") or ""),
                                str(d.get("member_email") or ""),
                                str(d.get("description") or "")[:300],
                            ]).lower()
                            if clean_q not in hay:
                                continue
                        seen_codes.add(cc)
                        last_msg_id = int(d.get("last_msg_id") or 0)
                        last_read_id = int(d.get("last_read_msg_id") or 0)
                        last_sender = str(d.get("last_sender_type") or "")
                        is_unread = (
                            (last_msg_id > last_read_id and last_sender == "reporter")
                            or (str(d.get("status") or "").upper() == "SUBMITTED" and last_read_id == 0 and last_msg_id == 0)
                        )
                        results.append({
                            "case_code": cc,
                            "category": d.get("category") or "Support",
                            "priority": d.get("priority") or "STANDARD",
                            "status": d.get("status") or "SUBMITTED",
                            "subject": d.get("subject") or "No Subject",
                            "description_preview": str(d.get("description") or "")[:180],
                            "reporter_alias": d.get("reporter_alias") or "Anonymous",
                            "has_member": bool(d.get("member_email")),
                            "assigned_admin_id": d.get("assigned_admin_id"),
                            "assigned_admin_name": d.get("assigned_admin_name"),
                            "file_count": int(d.get("file_count") or 0),
                            "msg_count": int(d.get("msg_count") or 0),
                            "last_msg_id": last_msg_id,
                            "last_sender_type": last_sender,
                            "last_message_preview": str(d.get("last_message_text") or "")[:120],
                            "unread": bool(is_unread),
                            "created_at": d.get("created_at"),
                            "updated_at": d.get("updated_at"),
                        })
            except Exception as e:
                logger.warning("list_cases_admin query warning on %s: %s", db, e)
        results.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
        return results[:limit]

    def mark_case_read(self, case_code: str, admin_id: int, last_read_msg_id: int):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target_msg_id = max(1, int(last_read_msg_id or 0))
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.execute(
                        """
                        INSERT INTO admin_read_state (case_code, admin_id, last_read_msg_id, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(case_code, admin_id) DO UPDATE SET
                            last_read_msg_id = MAX(admin_read_state.last_read_msg_id, excluded.last_read_msg_id),
                            updated_at = excluded.updated_at
                        """,
                        (case_code, int(admin_id), target_msg_id, now)
                    )
                    conn.commit()
            except Exception:
                pass

    def assign_case(self, case_code: str, admin_id: Optional[int], admin_name: Optional[str], actor: str) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated = False
        action = "CASE_CLAIMED" if admin_id else "CASE_RELEASED"
        details = f"Assigned to {admin_name} (ID {admin_id})" if admin_id else "Case unassigned"
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    row = conn.execute("SELECT 1 FROM cases WHERE case_code = ?", (case_code,)).fetchone()
                    if row:
                        conn.execute(
                            "UPDATE cases SET assigned_admin_id = ?, assigned_admin_name = ?, updated_at = ? WHERE case_code = ?",
                            (admin_id, admin_name, now, case_code)
                        )
                        conn.execute(
                            "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                            (case_code, action, actor, details, now)
                        )
                        conn.commit()
                        updated = True
            except Exception:
                pass
        return updated

    def get_evidence_item(self, case_code: str, evidence_id: int) -> Optional[Dict[str, Any]]:
        """Fetch an evidence record strictly scoped by BOTH id and case_code (IDOR-safe)."""
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM evidence_files WHERE id = ? AND case_code = ?",
                        (int(evidence_id), case_code)
                    ).fetchone()
                    if row:
                        return dict(row)
            except Exception:
                pass
        return None

    def record_admin_audit(self, case_code: str, action: str, actor: str, details: str = ""):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for db in self._candidate_dbs():
            try:
                with sqlite3.connect(db) as conn:
                    conn.execute(
                        "INSERT INTO audit_logs (case_code, action, actor, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (case_code or "__SYSTEM__", action[:64], actor[:120], details[:500], now)
                    )
                    conn.commit()
                    break
            except Exception:
                pass


# =========================================================================
# Support Telegram Bot Integration (Inline Keyboards & Two-Way Chat)
# =========================================================================

class SupportBotBridge:
    def __init__(
        self,
        application: Optional[Application],
        vault: SupportVault,
        admin_chat_id: int,
        allowed_user_ids: Optional[Set[int]] = None,
        auth_callback: Optional[Callable[[int], bool]] = None,
        super_admin_callback: Optional[Callable[[int], bool]] = None,
        ops_group_chat_id: Optional[int] = None,
        storage_chat_id: Optional[int] = None,
        webapp_url: Optional[str] = None,
        bot_username: Optional[str] = None,
        webapp_shortname: Optional[str] = None,
    ):
        self.app = application
        self.vault = vault
        self.admin_chat_id = admin_chat_id
        # Group 1: Collaborative Operations Group
        self.ops_group_chat_id = ops_group_chat_id or admin_chat_id
        # Group 2: Dedicated Evidence Storage Group / Channel
        self.storage_chat_id = storage_chat_id
        self.auth_callback = auth_callback
        self.super_admin_callback = super_admin_callback
        self.webapp_url = (webapp_url or os.getenv("SUPPORT_WEBAPP_URL") or "").strip().rstrip("/") or self._discover_default_webapp_url()
        self.bot_username = (bot_username or os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
        self.webapp_shortname = (webapp_shortname or os.getenv("TELEGRAM_WEBAPP_SHORTNAME") or "").strip().strip("/")
        self.main_mini_app = os.getenv("TELEGRAM_MAIN_MINI_APP", "0").strip() == "1"
        self.legacy_chat_reply = os.getenv("LEGACY_TG_CHAT_REPLY", "0").strip() == "1"
        if allowed_user_ids is not None:
            self.allowed_user_ids: Set[int] = set(allowed_user_ids)
        elif admin_chat_id and admin_chat_id > 0:
            # Positive Telegram chat IDs correspond to individual user accounts; negative IDs are group/channel chats
            self.allowed_user_ids = {int(admin_chat_id)}
        else:
            self.allowed_user_ids = set()
        # In-memory mapping of active admin reply sessions: admin_id -> case_code
        self.active_reply_sessions: Dict[int, str] = {}
        # In-memory mapping of telegram message_id -> case_code
        self.msg_to_case: Dict[int, str] = {}
        if self.app and HAS_TELEGRAM:
            self._register_handlers()

    def _discover_default_webapp_url(self) -> str:
        """Infer HTTPS /tg-admin URL from Ghost configuration if SUPPORT_WEBAPP_URL is unset."""
        for cfg_name in ("config.production.json", "config.development.json"):
            for base_dir in (self.vault.ghost_dir, "/var/www/ghost"):
                cfg_path = os.path.join(base_dir, cfg_name)
                if os.path.isfile(cfg_path):
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                        raw_url = str(cfg.get("url") or "").strip().rstrip("/")
                        if raw_url:
                            return f"{raw_url}/tg-admin"
                    except Exception:
                        pass
        return ""

    def build_case_webapp_url(self, case_code: Optional[str] = None) -> str:
        base = (self.webapp_url or "").strip().rstrip("/")
        if not base:
            return ""
        if case_code:
            return f"{base}/?case={urllib.parse.quote(str(case_code))}"
        return f"{base}/"

    def build_ops_deeplink_url(self, case_code: Optional[str] = None) -> Optional[str]:
        """Build a Group-safe Telegram Mini App / bot deep link (Telegram forbids web_app buttons in groups)."""
        uname = (self.bot_username or "").strip().lstrip("@")
        if not uname:
            return None
        clean_code = str(case_code or "").strip().lstrip("#").upper()
        if self.webapp_shortname:
            param = f"case_{clean_code}" if clean_code else "inbox"
            return f"https://t.me/{uname}/{self.webapp_shortname}?startapp={urllib.parse.quote(param)}"
        if self.main_mini_app:
            param = f"case_{clean_code}" if clean_code else "inbox"
            return f"https://t.me/{uname}?startapp={urllib.parse.quote(param)}"
        open_param = f"open_{clean_code}" if clean_code else "open_inbox"
        return f"https://t.me/{uname}?start={urllib.parse.quote(open_param)}"

    def make_open_webapp_button(self, label: str, target_chat_id: Optional[int], case_code: Optional[str] = None) -> Optional[Any]:
        """Return an InlineKeyboardButton safe for the target chat type (WebAppInfo in DM, Direct/Start URL in Group)."""
        if not HAS_TELEGRAM:
            return None
        w_url = self.build_case_webapp_url(case_code)
        is_private_dm = target_chat_id is not None and int(target_chat_id) > 0
        if is_private_dm and w_url.startswith("https://"):
            return InlineKeyboardButton(label, web_app=WebAppInfo(url=w_url))
        dl_url = self.build_ops_deeplink_url(case_code)
        if dl_url:
            return InlineKeyboardButton(label, url=dl_url)
        return InlineKeyboardButton(label, callback_data=f"case_open:{case_code or 'INBOX'}")

    async def fetch_evidence_bytes(self, evidence_row: Dict[str, Any]) -> Tuple[bytes, str]:
        """Retrieve evidence bytes from local vault or server-side via Telegram Storage Bot API (never exposes BOT_TOKEN)."""
        mime = str(evidence_row.get("mime_type") or "application/octet-stream")
        stored_name = str(evidence_row.get("stored_filename") or "")
        if stored_name:
            local_path = self.vault.get_evidence_path(stored_name)
            if local_path and os.path.isfile(local_path):
                with open(local_path, "rb") as fp:
                    return fp.read(), mime

        tg_fid = evidence_row.get("telegram_file_id")
        reported_size = int(evidence_row.get("file_size") or 0)
        if reported_size > 20 * 1024 * 1024:
            raise EvidenceTooLargeError("File exceeds Telegram Bot API 20 MB download limit; send to Bot DM instead.")

        if tg_fid and self.app and HAS_TELEGRAM:
            try:
                tg_file = await self.app.bot.get_file(tg_fid)
                raw = await tg_file.download_as_bytearray()
                return bytes(raw), mime
            except Exception as exc:
                if "too big" in str(exc).lower():
                    raise EvidenceTooLargeError("File exceeds Telegram Bot API 20 MB download limit; send to Bot DM instead.") from exc
                raise FileNotFoundError(f"Could not fetch Telegram evidence: {exc}") from exc

        raise FileNotFoundError("Evidence file is unavailable on local disk and Telegram Bot is offline.")

    async def send_evidence_to_admin_dm(self, admin_user_id: int, case_code: str, evidence_row: Dict[str, Any]) -> bool:
        """Send an evidence file directly to the authenticated admin's Private DM (supports files up to 50 MB via file_id)."""
        if not self.app or not HAS_TELEGRAM or int(admin_user_id) <= 0:
            return False
        clean_fname = str(evidence_row.get("original_name") or "evidence.bin")
        sha_short = str(evidence_row.get("sha256_hash") or "")[:16]
        size_kb = int(evidence_row.get("file_size") or 0) // 1024
        caption = (
            f"📁 <b>{html.escape(clean_fname)}</b> (#{html.escape(case_code)})\n"
            f"Size: {size_kb} KB · SHA-256: <code>{html.escape(sha_short)}</code>"
        )
        tg_fid = evidence_row.get("telegram_file_id")
        if tg_fid:
            await self.app.bot.send_document(
                chat_id=int(admin_user_id),
                document=tg_fid,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            return True
        stored_name = str(evidence_row.get("stored_filename") or "")
        local_path = self.vault.get_evidence_path(stored_name) if stored_name else None
        if local_path and os.path.isfile(local_path):
            with open(local_path, "rb") as fp:
                await self.app.bot.send_document(
                    chat_id=int(admin_user_id),
                    document=fp,
                    filename=clean_fname,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            return True
        return False

    async def delete_telegram_messages(self, tg_msgs: List[Tuple[int, int]]):
        """Best-effort cleanup of Telegram storage/notification messages on case deletion."""
        if not self.app or not HAS_TELEGRAM:
            return
        for tg_cid, tg_mid in tg_msgs:
            try:
                await self.app.bot.delete_message(chat_id=tg_cid, message_id=tg_mid)
            except Exception:
                pass

    async def sync_ops_card_status(self, case_code: str):
        """Best-effort refresh of the Telegram notification card when case status changes in WebApp."""
        target_chat = self.ops_group_chat_id or self.admin_chat_id
        if not self.app or not target_chat or not HAS_TELEGRAM:
            return
        case_data = self.vault.get_case(case_code)
        if not case_data or not case_data.get("telegram_message_id"):
            return
        msg_id = int(case_data["telegram_message_id"])
        text = self.format_case_card(case_data)
        kb = self.make_case_keyboard(
            case_data["case_code"],
            case_data.get("status", "SUBMITTED"),
            has_files=bool(case_data.get("files")),
            msg_count=len(case_data.get("messages") or []),
            can_delete=self._is_super_admin(target_chat),
            target_chat_id=target_chat,
        )
        try:
            await self.app.bot.edit_message_text(
                chat_id=target_chat,
                message_id=msg_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception:
            pass

    async def store_evidence(
        self,
        case_code: str,
        filename: str,
        data: bytes,
        mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload evidence directly to the dedicated Telegram Storage Group (Group 2) with zero VPS disk retention."""
        clean_data = sanitize_media(filename, data)
        raw_name = os.path.basename(filename or "evidence")
        clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_name)[:120]
        if not clean_name or clean_name.startswith('.'):
            clean_name = f"evidence_{clean_name}"

        root_name, ext = os.path.splitext(clean_name)
        if not ext or ext.lower() not in self.vault.ALLOWED_EVIDENCE_EXTS:
            ext_label = ext.lstrip('.') or 'bin'
            clean_name = f"{root_name[:96]}_{ext_label}.blocked"
            mime_type = "application/octet-stream"

        sha256 = hashlib.sha256(clean_data).hexdigest()
        tg_file_id = None
        tg_msg_id = None
        tg_chat_id = None
        tg_unique_id = None

        if self.app and self.storage_chat_id and HAS_TELEGRAM:
            try:
                import io
                bio = io.BytesIO(clean_data)
                bio.name = clean_name
                now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                caption = (
                    f"📦 <b>Case #{html.escape(case_code)}</b>\n"
                    f"File: <code>{html.escape(clean_name)}</code> ({len(clean_data):,} bytes)\n"
                    f"SHA-256: <code>{sha256}</code>\n"
                    f"Time: {now_str}"
                )
                sent_msg = await self.app.bot.send_document(
                    chat_id=self.storage_chat_id,
                    document=bio,
                    filename=clean_name,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                if sent_msg and sent_msg.document:
                    tg_file_id = sent_msg.document.file_id
                    tg_unique_id = sent_msg.document.file_unique_id
                    tg_msg_id = sent_msg.message_id
                    tg_chat_id = sent_msg.chat.id
                    logger.info("Uploaded evidence %s for case %s to Telegram Storage Group %s (msg: %s)", clean_name, case_code, tg_chat_id, tg_msg_id)
            except Exception as e:
                logger.error("Failed to upload evidence to Telegram Storage Group: %s. Falling back to local storage.", e)

        # Record in vault (if tg_file_id is set, save_evidence skips writing bytes to VPS disk)
        saved = self.vault.save_evidence(
            case_code=case_code,
            filename=clean_name,
            data=clean_data,
            mime_type=mime_type,
            telegram_file_id=tg_file_id,
            telegram_message_id=tg_msg_id,
            telegram_chat_id=tg_chat_id,
            telegram_file_unique_id=tg_unique_id
        )
        return saved

    def _is_authorized_user(self, user_id: Optional[int]) -> bool:
        """Fail-closed authorization check on all SupportBotBridge handlers (CRIT-01)."""
        if user_id is None:
            return False
        if self.auth_callback is not None:
            try:
                return bool(self.auth_callback(user_id))
            except Exception:
                return False
        if not self.allowed_user_ids:
            return False
        return user_id in self.allowed_user_ids

    def _is_super_admin(self, user_id: Optional[int]) -> bool:
        """Fail-closed Super Admin privilege check for destructive case operations."""
        if user_id is None or self.super_admin_callback is None:
            return False
        try:
            return bool(self.super_admin_callback(user_id))
        except Exception:
            return False

    def _register_handlers(self):
        if not HAS_TELEGRAM or not self.app:
            return
        try:
            self.app.add_handler(CallbackQueryHandler(self.handle_callback, pattern=r"^case_"))
            self.app.add_handler(CommandHandler("cases", self.cases_command))
            self.app.add_handler(CommandHandler("cancel", self.cancel_command))
            # Handle admin text messages (both native replies and interactive conversation)
            self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_admin_message))
        except Exception as e:
            logger.warning("Could not register handlers on bot app (may already be registered in main): %s", e)

    def make_case_keyboard(
        self,
        case_code: str,
        status: str,
        has_files: bool = False,
        msg_count: int = 0,
        can_delete: bool = False,
        target_chat_id: Optional[int] = None,
    ) -> Any:
        if not HAS_TELEGRAM:
            return None
        resolved_chat = target_chat_id if target_chat_id is not None else (self.ops_group_chat_id or self.admin_chat_id)
        webapp_btn = self.make_open_webapp_button("🖥️ Open in Case Console", resolved_chat, case_code=case_code)

        if not self.legacy_chat_reply:
            rows = []
            if webapp_btn:
                rows.append([webapp_btn])
            if resolved_chat and int(resolved_chat) > 0:
                if can_delete:
                    rows.append([
                        InlineKeyboardButton("🗑️ Delete Case", callback_data=f"case_delete_ask:{case_code}"),
                        InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list"),
                    ])
                else:
                    rows.append([InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list")])
            return InlineKeyboardMarkup(rows) if rows else None

        # Legacy inline chat controls (only if LEGACY_TG_CHAT_REPLY=1)
        rows = []
        if webapp_btn:
            rows.append([webapp_btn])
        row1 = [
            InlineKeyboardButton(f"💬 Chat & History ({msg_count})", callback_data=f"case_thread:{case_code}")
        ]
        if has_files:
            row1.append(InlineKeyboardButton("📎 Evidence", callback_data=f"case_evidence:{case_code}"))
        rows.append(row1)

        row2 = [
            InlineKeyboardButton("⚙️ Change Status", callback_data=f"case_status_menu:{case_code}")
        ]
        if can_delete:
            row2.append(InlineKeyboardButton("🗑️ Delete Case", callback_data=f"case_delete_ask:{case_code}"))
            rows.append(row2)
            rows.append([InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list")])
        else:
            row2.append(InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list"))
            rows.append(row2)
        return InlineKeyboardMarkup(rows)

    def make_status_menu_keyboard(self, case_code: str, can_delete: bool = False) -> Any:
        if not HAS_TELEGRAM:
            return None
        rows = [
            [
                InlineKeyboardButton("🟡 Set: In Progress", callback_data=f"case_set_status:{case_code}:IN_REVIEW"),
                InlineKeyboardButton("🟢 Set: Resolved", callback_data=f"case_set_status:{case_code}:CLOSED")
            ],
            [
                InlineKeyboardButton("⚪ Set: Closed / Dismissed", callback_data=f"case_set_status:{case_code}:REJECTED")
            ],
        ]
        if can_delete:
            rows.append([InlineKeyboardButton("🗑️ Delete Case", callback_data=f"case_delete_ask:{case_code}")])
        rows.append([InlineKeyboardButton("⬅️ Cancel / Back", callback_data=f"case_view:{case_code}")])
        return InlineKeyboardMarkup(rows)

    def format_case_card(self, case_data: Dict[str, Any]) -> str:
        priority_emojis = {
            "CRITICAL": "🔴 Critical",
            "URGENT": "🟠 Urgent",
            "STANDARD": "🟡 Standard",
            "LOW": "⚪ Low"
        }
        status_emojis = {
            "SUBMITTED": "🟡 New",
            "IN_REVIEW": "🟠 In Progress",
            "CLOSED": "🟢 Resolved",
            "REJECTED": "⚪ Closed"
        }

        raw_priority = str(case_data.get('priority') or 'STANDARD').upper()
        raw_status = str(case_data.get('status') or 'SUBMITTED').upper()
        p_display = priority_emojis.get(raw_priority, raw_priority)
        s_display = status_emojis.get(raw_status, raw_status)

        import html
        category = html.escape(str(case_data.get('category') or 'Support'))
        subject = html.escape(str(case_data.get('subject') or 'No Subject'))
        desc = html.escape(str(case_data.get('description') or ''))[:600]
        reporter = html.escape(str(case_data.get('reporter_alias') or 'Anonymous'))
        created_at = str(case_data.get('created_at') or '')[:16].replace('T', ' ')

        member_info = ""
        if case_data.get("member_email"):
            m_esc = html.escape(str(case_data["member_email"]))
            member_info = f" (<code>{m_esc}</code>)"

        files = case_data.get("files", [])
        if files:
            files_snippet = []
            for f in files[:2]:
                fn = html.escape(str(f.get('original_name') or 'file'))
                sz = (f.get('file_size') or 0) // 1024
                files_snippet.append(f"{fn} ({sz} KB)")
            files_line = f"📎 <b>Attachments:</b> {len(files)} file(s) [{', '.join(files_snippet)}]\n"
        else:
            files_line = "📎 <b>Attachments:</b> None\n"

        msgs = self.vault.get_messages(case_data.get("case_code", ""))
        msg_count = len(msgs)
        if msg_count > 0:
            latest = msgs[-1]
            last_sender = "You" if latest.get("sender_type") == "admin" else "Reporter"
            last_time = str(latest.get("created_at") or "")[11:16]
            msg_line = f"💬 <b>Conversation:</b> {msg_count} message(s) (Latest from {last_sender} at {last_time} UTC)\n"
        else:
            msg_line = "💬 <b>Conversation:</b> No messages exchanged yet\n"

        note_text = ""
        if case_data.get("resolution_note"):
            clean_note = html.escape(str(case_data['resolution_note']))
            note_text = f"📋 <b>Resolution Note:</b> {clean_note}\n"

        return (
            f"🛡️ <b>Support Case #{case_data['case_code']}</b>\n"
            f"Status: <b>{s_display}</b>  |  Priority: <b>{p_display}</b>\n"
            f"Category: {category}  ·  Reporter: {reporter}{member_info}\n"
            f"Submitted: {created_at} UTC\n\n"
            f"📝 <b>{subject}</b>\n"
            f"<blockquote>{desc}</blockquote>\n"
            f"{files_line}"
            f"{msg_line}"
            f"{note_text}"
        )

    def format_thread_view(self, case_code: str, case_data: Dict[str, Any], msgs: List[Dict[str, Any]]) -> Tuple[str, InlineKeyboardMarkup]:
        import html
        subject = html.escape(str(case_data.get('subject') or 'No Subject'))
        raw_status = str(case_data.get('status') or 'SUBMITTED').upper()
        status_tag = "🟡 New" if raw_status == "SUBMITTED" else ("🟠 In Progress" if raw_status == "IN_REVIEW" else "🟢 Resolved")

        lines = [
            f"💬 <b>Case #{case_code} Thread</b>",
            f"<b>{subject}</b> · {status_tag}",
            ""
        ]

        if not msgs:
            lines.append("<i>No messages yet. Tap Send Reply below to start.</i>")
        else:
            for m in msgs[-10:]:
                is_admin = m.get("sender_type") == "admin"
                sender_label = "🛡️ Support" if is_admin else f"👤 {html.escape(m.get('sender_name') or 'Reporter')}"
                time_str = str(m.get("created_at") or "")[11:16]
                m_text = html.escape(m.get("message_text") or "")
                lines.append(f"<b>{sender_label}</b> · <i>{time_str} UTC</i>\n<blockquote>{m_text}</blockquote>")

        lines.append(f"\n<i>{len(msgs)} message(s)</i>")
        text = "\n".join(lines)

        buttons = [
            [
                InlineKeyboardButton("💬 Send Reply", callback_data=f"case_reply:{case_code}"),
                InlineKeyboardButton("🔄 Refresh Thread", callback_data=f"case_thread:{case_code}")
            ],
            [
                InlineKeyboardButton("⚙️ Change Status", callback_data=f"case_status_menu:{case_code}"),
                InlineKeyboardButton("⬅️ Back to Case", callback_data=f"case_view:{case_code}")
            ]
        ]
        kb = InlineKeyboardMarkup(buttons) if HAS_TELEGRAM else None
        return text, kb

    async def notify_new_case(self, case_data: Dict[str, Any]):
        """Send streamlined notification alert with WebApp launch button to the ops chat."""
        target_chat = self.ops_group_chat_id or self.admin_chat_id
        if not self.app or not target_chat:
            logger.info("Standalone/No-admin mode: skipping Telegram case alert for %s", case_data.get("case_code"))
            return

        text = self.format_case_card(case_data)
        has_files = bool(case_data.get("files"))
        kb = self.make_case_keyboard(
            case_data["case_code"],
            case_data["status"],
            has_files=has_files,
            msg_count=0,
            can_delete=self._is_super_admin(target_chat),
            target_chat_id=target_chat,
        )
        try:
            msg = await self.app.bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            self.vault.set_telegram_message_id(case_data["case_code"], msg.message_id)
            self.msg_to_case[msg.message_id] = case_data["case_code"]
        except Exception as e:
            logger.error("Failed to dispatch Telegram case notification to %s: %s", target_chat, e)

    async def notify_reporter_reply(self, case_code: str, message_text: str):
        """Notify ops chat with a WebApp launch link when reporter sends a message on the web portal."""
        target_chat = self.ops_group_chat_id or self.admin_chat_id
        if not self.app or not target_chat:
            logger.info("Standalone/No-admin mode: skipping Telegram reporter reply alert for %s", case_code)
            return

        snippet = str(message_text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:397] + "..."
        text = (
            f"💬 <b>New Reporter Message on #{html.escape(case_code)}</b>\n\n"
            f"<blockquote>{html.escape(snippet)}</blockquote>\n"
            f"<i>Open in Case Console to review &amp; reply:</i>"
        )
        open_btn = self.make_open_webapp_button("🖥️ Open Case Console", target_chat, case_code=case_code)
        rows = [[open_btn]] if open_btn else []
        if self.legacy_chat_reply:
            rows.append([
                InlineKeyboardButton("💬 Legacy Reply", callback_data=f"case_reply:{case_code}"),
                InlineKeyboardButton("🔍 View Case", callback_data=f"case_view:{case_code}"),
            ])
        kb = InlineKeyboardMarkup(rows) if (HAS_TELEGRAM and rows) else None
        try:
            msg = await self.app.bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            self.msg_to_case[msg.message_id] = case_code
        except Exception as e:
            logger.error("Failed to forward reporter reply: %s", e)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        caller_id = query.from_user.id if (query and query.from_user) else (update.effective_user.id if update.effective_user else None)
        if not self._is_authorized_user(caller_id):
            if query:
                try:
                    await query.answer("⛔ Access Denied.", show_alert=True)
                except Exception:
                    pass
            return
        data = query.data or ""
        parts = data.split(":")
        action = parts[0] if parts else ""
        case_code = parts[1] if len(parts) > 1 else ""
        extra_param = parts[2] if len(parts) > 2 else ""
        is_super = self._is_super_admin(caller_id)

        if action in ("case_delete_ask", "case_delete_do") and not is_super:
            try:
                await query.answer("⛔ Permission denied.", show_alert=True)
            except Exception:
                pass
            return

        if action not in ("case_delete_ask", "case_delete_do", "case_evidence", "case_reply", "case_set_status"):
            try:
                await query.answer()
            except Exception:
                pass

        try:
            case_data = self.vault.get_case(case_code)
            if not case_data:
                try:
                    await query.answer(f"❌ Case #{case_code} not found.", show_alert=True)
                except Exception:
                    pass
                try:
                    await query.edit_message_text(f"❌ Case #{case_code} not found.")
                except Exception:
                    pass
                return

            admin_user = query.from_user.username or query.from_user.first_name or "Administrator"

            chat_id_for_kb = query.message.chat.id if (query and query.message and query.message.chat) else caller_id

            if action == "case_open":
                dm_btn = self.make_open_webapp_button("🖥️ Open Case Console", caller_id, case_code=None if case_code == "INBOX" else case_code)
                if query.message and query.message.chat and int(query.message.chat.id) < 0:
                    try:
                        await query.answer("Open the Case Console via my Private DM.", show_alert=True)
                    except Exception:
                        pass
                else:
                    await query.message.reply_text(
                        f"🖥️ <b>Support Case Console</b>" + (f" (<b>#{html.escape(case_code)}</b>)" if case_code and case_code != "INBOX" else ""),
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[dm_btn]]) if dm_btn else None,
                    )

            elif action == "case_view":
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(
                    case_code,
                    case_data.get("status", "SUBMITTED"),
                    has_files=has_files,
                    msg_count=len(msgs),
                    can_delete=is_super,
                    target_chat_id=chat_id_for_kb,
                )
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action in ("case_thread", "case_history"):
                if not self.legacy_chat_reply:
                    dm_btn = self.make_open_webapp_button("🖥️ Open in Case Console", chat_id_for_kb, case_code=case_code)
                    await query.message.reply_text(
                        f"🖥️ <b>Case #{html.escape(case_code)} chat &amp; history are managed in the WebApp Case Console.</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[dm_btn]]) if dm_btn else None,
                    )
                    return
                msgs = self.vault.get_messages(case_code)
                text, kb = self.format_thread_view(case_code, case_data, msgs)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action == "case_status_menu":
                raw_st = str(case_data.get("status") or "SUBMITTED").upper()
                st_name = "🟡 New" if raw_st == "SUBMITTED" else ("🟠 In Progress" if raw_st == "IN_REVIEW" else "🟢 Resolved")
                text = (
                    f"⚙️ <b>Change Status: #{html.escape(case_code)}</b>\n"
                    f"Current Status: <b>{st_name}</b>\n\n"
                    f"Choose an updated status for this case:"
                )
                kb = self.make_status_menu_keyboard(case_code, can_delete=is_super)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action == "case_set_status":
                # Format: case_set_status:<case_code>:<new_status>
                parts = data.split(":")
                new_st = parts[2] if len(parts) > 2 else "IN_REVIEW"
                self.vault.update_status(case_code, new_st, actor=admin_user, note=f"Status set to {new_st} via Telegram.")
                case_data = self.vault.get_case(case_code) or case_data
                case_data["status"] = new_st
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                try:
                    await query.answer(f"✓ Case #{case_code} set to {new_st}")
                except Exception:
                    pass
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, new_st, has_files=has_files, msg_count=len(msgs), can_delete=is_super)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass

            elif action == "case_review":
                self.vault.update_status(case_code, "IN_REVIEW", actor=admin_user)
                case_data["status"] = "IN_REVIEW"
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "IN_REVIEW", has_files=has_files, msg_count=len(msgs), can_delete=is_super)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass

            elif action == "case_close":
                self.vault.update_status(case_code, "CLOSED", actor=admin_user, note="Resolved by support team.")
                case_data["status"] = "CLOSED"
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "CLOSED", has_files=has_files, msg_count=len(msgs), can_delete=is_super)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass

            elif action == "case_reject":
                self.vault.update_status(case_code, "REJECTED", actor=admin_user, note="Dismissed or closed.")
                case_data["status"] = "REJECTED"
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(case_code, "REJECTED", has_files=has_files, msg_count=len(msgs), can_delete=is_super)
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass

            elif action == "case_delete_ask":
                if not is_super:
                    try:
                        await query.answer("⛔ Permission denied.", show_alert=True)
                    except Exception:
                        pass
                    return
                try:
                    await query.answer()
                except Exception:
                    pass
                subj = html.escape(str(case_data.get("subject") or "No Subject"))
                confirm_text = (
                    f"⚠️ <b>Delete #{html.escape(case_code)}?</b>\n\n"
                    f"<b>Subject:</b> {subj}\n\n"
                    f"This permanently removes the case, messages, and evidence records."
                )
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Yes, Delete", callback_data=f"case_delete_do:{case_code}"),
                        InlineKeyboardButton("❌ Cancel", callback_data=f"case_view:{case_code}"),
                    ]
                ])
                try:
                    await query.edit_message_text(text=confirm_text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action == "case_delete_do":
                if not is_super:
                    try:
                        await query.answer("⛔ Permission denied.", show_alert=True)
                    except Exception:
                        pass
                    return
                del_info = self.vault.delete_case(case_code)
                if not del_info:
                    try:
                        await query.answer(f"❌ Case #{case_code} not found.", show_alert=True)
                    except Exception:
                        pass
                    return

                for uid_key in [u for u, cc in self.active_reply_sessions.items() if cc == case_code]:
                    self.active_reply_sessions.pop(uid_key, None)
                for mid_key in [m for m, cc in self.msg_to_case.items() if cc == case_code]:
                    self.msg_to_case.pop(mid_key, None)

                bot_client = getattr(context, "bot", None) or (self.app.bot if self.app else None)
                if bot_client:
                    tg_cleanup = list(del_info.get("evidence_tg_messages", []))
                    target_chat = self.ops_group_chat_id or self.admin_chat_id
                    if target_chat:
                        for ops_mid in del_info.get("ops_telegram_message_ids") or []:
                            tg_cleanup.append((int(target_chat), int(ops_mid)))
                    for tg_cid, tg_mid in tg_cleanup:
                        try:
                            await bot_client.delete_message(chat_id=tg_cid, message_id=tg_mid)
                        except Exception:
                            pass

                try:
                    await query.answer(f"Deleted #{case_code}")
                except Exception:
                    pass
                try:
                    await query.edit_message_text(
                        text=f"🗑️ Case <b>#{html.escape(case_code)}</b> deleted.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list")]])
                    )
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action == "case_evidence":
                if not self.legacy_chat_reply:
                    try:
                        await query.answer("Inspect evidence inside the Case Console WebApp.", show_alert=True)
                    except Exception:
                        pass
                    dm_btn = self.make_open_webapp_button("🖥️ Open Evidence in Case Console", chat_id_for_kb, case_code=case_code)
                    if dm_btn and query and query.message:
                        await query.message.reply_text(
                            f"📎 <b>Evidence for #{html.escape(case_code)}</b> is viewed securely inside the Case Console WebApp.",
                            parse_mode=ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup([[dm_btn]]),
                        )
                    return
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
                    clean_fname = html.escape(str(f.get("original_name") or "evidence.bin"))
                    sha = html.escape(str(f.get("sha256_hash") or "")[:16])
                    size_kb = (f.get("file_size") or 0) // 1024
                    caption = (
                        f"📁 <b>{clean_fname}</b>\n"
                        f"Size: {size_kb} KB\n"
                        f"SHA-256: <code>{sha}</code>"
                    )

                    # 1. First priority: Direct instant delivery from Telegram Storage Vault
                    tg_fid = f.get("telegram_file_id")
                    if tg_fid:
                        try:
                            await query.message.reply_document(
                                document=tg_fid,
                                caption=caption,
                                parse_mode=ParseMode.HTML
                            )
                            sent_count += 1
                            continue
                        except Exception as e:
                            logger.warning("Could not forward evidence via telegram_file_id %s: %s", tg_fid, e)

                    # 2. Second priority: Fallback to local disk file if present
                    stored_name = f.get("stored_filename", "")
                    stored_path = self.vault.get_evidence_path(stored_name)
                    if stored_path and os.path.exists(stored_path):
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
                            f"⚠️ Evidence file <code>{missing_name}</code> could not be retrieved.",
                            parse_mode=ParseMode.HTML
                        )

                if sent_count > 0:
                    await query.message.reply_text(
                        f"✅ Sent <b>{sent_count}</b> file(s) for <b>#{html.escape(case_code)}</b>.",
                        parse_mode=ParseMode.HTML
                    )

            elif action == "case_reply":
                if not self.legacy_chat_reply:
                    try:
                        await query.answer("Replies have moved to the Case Console WebApp.", show_alert=True)
                    except Exception:
                        pass
                    dm_btn = self.make_open_webapp_button("🖥️ Open Case Console", chat_id_for_kb, case_code=case_code)
                    if dm_btn and query and query.message:
                        await query.message.reply_text(
                            f"💬 <b>Replying to #{html.escape(case_code)}</b> now happens inside the WebApp Case Console.",
                            parse_mode=ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup([[dm_btn]]),
                        )
                    return
                self.active_reply_sessions[query.from_user.id] = case_code
                try:
                    await query.answer("💬 Reply Mode Active")
                except Exception:
                    pass
                await query.message.reply_text(
                    f"💬 <b>Replying to #{html.escape(case_code)}</b>\n"
                    f"Type your message below. Send /cancel to stop.",
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
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self._is_authorized_user(user_id):
            return
        if not self.legacy_chat_reply:
            self.active_reply_sessions.pop(user_id, None)
            if update.message.chat and int(update.message.chat.id) > 0:
                open_btn = self.make_open_webapp_button("🖥️ Open Case Console", update.message.chat.id)
                await update.message.reply_text(
                    "🖥️ <b>Support replies &amp; evidence review now happen inside the Case Console WebApp.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[open_btn]]) if open_btn else None,
                )
            return
        reply_to = update.message.reply_to_message
        case_code = None

        # Check 1: Is user in an active reply session?
        if user_id in self.active_reply_sessions:
            case_code = self.active_reply_sessions.get(user_id)

        # Check 2: Did user reply directly to a bot message representing a case (group chat support)?
        elif reply_to and reply_to.message_id:
            case_code = self.msg_to_case.get(reply_to.message_id)
            if not case_code:
                case_row = self.vault.get_case_by_telegram_message_id(reply_to.message_id)
                if case_row:
                    case_code = case_row["case_code"]
                    self.msg_to_case[reply_to.message_id] = case_code

        if not case_code:
            return  # Not a support reply message, pass through to other bot handlers

        # Handle cancel command
        if update.message.text and update.message.text.strip().lower() == "/cancel":
            self.active_reply_sessions.pop(user_id, None)
            await update.message.reply_text("❌ Reply session ended.", parse_mode=ParseMode.HTML)
            return

        admin_name = update.effective_user.first_name or "Investigator"
        delivered_parts = []

        # Download and store photo if present (directly to Telegram Storage Group)
        if update.message.photo:
            try:
                photo = update.message.photo[-1]
                p_file = await photo.get_file()
                p_bytes = await p_file.download_as_bytearray()
                p_name = f"admin_photo_{int(time.time())}.jpg"
                await self.store_evidence(case_code, p_name, bytes(p_bytes), "image/jpeg")
                delivered_parts.append(f"📁 [{p_name}]")
            except Exception as e:
                logger.error("Failed to store admin photo: %s", e)

        # Download and store document if present (directly to Telegram Storage Group)
        if update.message.document:
            try:
                doc = update.message.document
                d_file = await doc.get_file()
                d_bytes = await d_file.download_as_bytearray()
                d_name = doc.file_name or f"admin_file_{int(time.time())}"
                await self.store_evidence(case_code, d_name, bytes(d_bytes), doc.mime_type or "application/octet-stream")
                delivered_parts.append(f"📁 [{d_name}]")
            except Exception as e:
                logger.error("Failed to store admin document: %s", e)

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
            f"✓ <b>Sent to #{html.escape(case_code)}</b> ({html.escape(admin_name)})\n"
            f"<blockquote>{html.escape(final_text)}</blockquote>\n"
            f"<i>Reply mode active · /cancel to stop</i>",
            parse_mode=ParseMode.HTML
        )

    async def cases_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List active cases with one-tap Case Console WebApp buttons."""
        caller_id = update.effective_user.id if update.effective_user else None
        if not self._is_authorized_user(caller_id):
            if update.message:
                await update.message.reply_text("⛔ Access Denied.")
            return
        chat_id = update.effective_chat.id if update.effective_chat else caller_id
        inbox_btn = self.make_open_webapp_button("🖥️ Open Support Case Console", chat_id)
        cases = self.vault.list_recent_cases(limit=8)
        if not cases:
            kb = InlineKeyboardMarkup([[inbox_btn]]) if (HAS_TELEGRAM and inbox_btn) else None
            await update.message.reply_text("ℹ️ No support cases currently on record.", reply_markup=kb)
            return

        lines = ["📋 <b>Recent Cases</b>\n"]
        buttons = []
        if inbox_btn:
            buttons.append([inbox_btn])
        for c in cases:
            cc_raw = str(c.get('case_code') or 'UNKNOWN')
            cs_raw = str(c.get('status') or 'SUBMITTED').upper()
            st_icon = "🟡" if cs_raw == "SUBMITTED" else ("🟠" if cs_raw == "IN_REVIEW" else "🟢")
            cc = html.escape(cc_raw)
            cp = html.escape(str(c.get('priority') or 'STANDARD'))
            cg = html.escape(str(c.get('category') or 'General'))
            cs = html.escape(cs_raw)
            sub_raw = str(c.get('subject') or 'No Subject')
            sub = html.escape(sub_raw[:30])
            lines.append(
                f"• <b>#{cc}</b> [{cp}] · {cg}\n"
                f"  <b>{cs}</b> — {sub}\n"
            )
            btn = self.make_open_webapp_button(f"{st_icon} #{cc_raw} - {sub_raw[:22]}", chat_id, case_code=cc_raw)
            if btn:
                buttons.append([btn])
        lines.append("<i>Tap below to open a case in the Mini App:</i>")
        kb = InlineKeyboardMarkup(buttons) if HAS_TELEGRAM and buttons else None
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        caller_id = update.effective_user.id if update.effective_user else None
        if not self._is_authorized_user(caller_id):
            if update.message:
                await update.message.reply_text("⛔ Access Denied.")
            return
        user_id = caller_id
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
    2. Vector-path visual math challenge (zero <text> / ASCII digits in SVG DOM, shuffled glyph order).
    3. Client-side SHA-256 Proof-of-Work (PoW) difficulty requiring computational work
       before requests are admitted, neutralizing DDoS/flood scripts.
    4. Anti-replay token tracking with memory-capped sliding expiration.
    """
    GLYPH_STROKES: Dict[str, List[Tuple[float, float, float, float]]] = {
        '0': [(0, 0, 10, 0), (10, 0, 10, 16), (10, 16, 0, 16), (0, 16, 0, 0)],
        '1': [(2, 3, 5, 0), (5, 0, 5, 16), (1, 16, 9, 16)],
        '2': [(0, 0, 10, 0), (10, 0, 10, 8), (10, 8, 0, 8), (0, 8, 0, 16), (0, 16, 10, 16)],
        '3': [(0, 0, 10, 0), (10, 0, 10, 16), (0, 8, 10, 8), (0, 16, 10, 16)],
        '4': [(0, 0, 0, 8), (0, 8, 10, 8), (10, 0, 10, 16)],
        '5': [(10, 0, 0, 0), (0, 0, 0, 8), (0, 8, 10, 8), (10, 8, 10, 16), (10, 16, 0, 16)],
        '6': [(10, 0, 0, 0), (0, 0, 0, 16), (0, 16, 10, 16), (10, 16, 10, 8), (10, 8, 0, 8)],
        '7': [(0, 0, 10, 0), (10, 0, 3, 16)],
        '8': [(0, 0, 10, 0), (10, 0, 10, 16), (10, 16, 0, 16), (0, 16, 0, 0), (0, 8, 10, 8)],
        '9': [(10, 8, 0, 8), (0, 8, 0, 0), (0, 0, 10, 0), (10, 0, 10, 16), (10, 16, 0, 16)],
        '+': [(5, 3, 5, 13), (0, 8, 10, 8)],
        '-': [(1, 8, 9, 8)],
        '=': [(1, 5, 9, 5), (1, 11, 9, 11)],
        '?': [(0, 3, 0, 0), (0, 0, 10, 0), (10, 0, 10, 7), (10, 7, 5, 9), (5, 9, 5, 12), (5, 15, 5, 16.5)],
    }

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or secrets.token_hex(32)
        # Store spent challenges: challenge_id -> expiry_timestamp
        self.spent_tokens: Dict[str, float] = {}
        self.max_spent_tokens = 10000
        self.difficulty = 4  # Requires hash beginning with '0000' (~0.1s-0.4s client-side)

    def _cleanup_expired(self):
        now = time.time()
        expired = [cid for cid, exp in self.spent_tokens.items() if exp < now]
        for cid in expired:
            self.spent_tokens.pop(cid, None)
        if len(self.spent_tokens) > self.max_spent_tokens:
            # Evict oldest expiry entries if memory cap is exceeded
            oldest = sorted(self.spent_tokens.items(), key=lambda kv: kv[1])[: len(self.spent_tokens) - self.max_spent_tokens]
            for cid, _ in oldest:
                self.spent_tokens.pop(cid, None)

    @staticmethod
    def _jitter() -> float:
        return (secrets.randbelow(121) - 60) / 100.0  # [-0.60, +0.60]

    def _render_vector_svg(self, expr: str) -> str:
        svg_w, svg_h = 176, 44
        chars = [ch for ch in expr]
        # Compute x positions for non-space glyphs
        positioned: List[Tuple[float, str]] = []
        cursor_x = 14.0
        for ch in chars:
            if ch == ' ':
                cursor_x += 7.0
                continue
            positioned.append((cursor_x, ch))
            cursor_x += 15.5

        # Center horizontally
        total_span = max(cursor_x - 14.0, 1.0)
        offset_x = max((svg_w - total_span) / 2.0, 8.0)

        # Shuffle DOM emission order so glyph sequence cannot be inferred from element index
        indices = list(range(len(positioned)))
        for i in range(len(indices) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            indices[i], indices[j] = indices[j], indices[i]

        glyph_elems: List[str] = []
        for idx in indices:
            gx, ch = positioned[idx]
            strokes = self.GLYPH_STROKES.get(ch, [])
            if not strokes:
                continue
            px = offset_x + (gx - 14.0) + self._jitter()
            py = 14.0 + self._jitter() * 1.5
            rot = (secrets.randbelow(13) - 6)  # [-6, +6] deg
            d_parts: List[str] = []
            # Shuffle individual strokes within each glyph as well
            s_order = list(strokes)
            for si in range(len(s_order) - 1, 0, -1):
                sj = secrets.randbelow(si + 1)
                s_order[si], s_order[sj] = s_order[sj], s_order[si]
            for (x1, y1, x2, y2) in s_order:
                jx1 = round(x1 + self._jitter() * 0.65, 2)
                jy1 = round(y1 + self._jitter() * 0.65, 2)
                jx2 = round(x2 + self._jitter() * 0.65, 2)
                jy2 = round(y2 + self._jitter() * 0.65, 2)
                d_parts.append(f"M {jx1} {jy1} L {jx2} {jy2}")
            d_str = " ".join(d_parts)
            glyph_elems.append(
                f'<g transform="translate({px:.1f},{py:.1f}) rotate({rot},5,8)">'
                f'<path d="{d_str}" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                f'</g>'
            )

        # Decoy interference curves
        decoys: List[str] = []
        for _ in range(5):
            x0, y0 = secrets.randbelow(30) + 4, secrets.randbelow(36) + 4
            cx, cy = secrets.randbelow(100) + 35, secrets.randbelow(40) + 2
            x1, y1 = secrets.randbelow(40) + 132, secrets.randbelow(36) + 4
            decoys.append(
                f'<path d="M {x0} {y0} Q {cx} {cy}, {x1} {y1}" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="1.3"/>'
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" style="user-select:none;border-radius:8px;">'
            f'<rect width="100%" height="100%" fill="rgba(15,23,42,0.95)" rx="8" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>'
            + "".join(decoys)
            + "".join(glyph_elems)
            + '</svg>'
        )

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
            question = f"{num1} + {num2} = ?"
        else:
            if num1 < num2:
                num1, num2 = num2, num1
            ans = str(num1 - num2)
            question = f"{num1} - {num2} = ?"

        # Sign the challenge parameters: challenge_id, timestamp, ans, difficulty
        sig_payload = f"{challenge_id}:{timestamp}:{ans}:{self.difficulty}"
        signature = hmac.new(self.secret_key.encode('utf-8'), sig_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        svg_markup = self._render_vector_svg(question)

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
    MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB overall HTTP payload cap
    MAX_EVIDENCE_BYTES = 20 * 1024 * 1024  # 20 MB per-file cap (Telegram Bot API getFile download limit)
    MAX_EVIDENCE_CACHE_BYTES = 48 * 1024 * 1024  # Bounded in-memory LRU for streamed evidence previews
    EVIDENCE_CACHE_TTL_SEC = 300.0
    ADMIN_IDLE_TTL_SEC = 900.0  # 15 min idle session timeout
    ADMIN_MAX_TTL_SEC = 7200.0  # 2 hr hard session timeout
    ADMIN_INITDATA_MAX_AGE_SEC = int(os.getenv("ADMIN_INITDATA_MAX_AGE_SEC", "300") or "300")
    LARGE_UPLOAD_THRESHOLD = 2 * 1024 * 1024  # 2 MB concurrency gate
    MAX_HEADER_COUNT = 64
    MAX_HEADER_LINE_BYTES = 8192
    MAX_FILES_PER_CASE = 15

    SAFE_PREVIEW_EXTS: Dict[str, str] = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".csv": "text/plain; charset=utf-8",
        ".json": "text/plain; charset=utf-8",
        ".eml": "text/plain; charset=utf-8",
    }

    def __init__(self, vault: SupportVault, bridge: SupportBotBridge, host: str = "127.0.0.1", port: int = 8080):
        self.vault = vault
        self.bridge = bridge
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.captcha = CaptchaEngine()
        self._conn_sem = asyncio.Semaphore(32)
        self._upload_sem = asyncio.Semaphore(2)
        self._evidence_dl_sem = asyncio.Semaphore(4)
        # Bounded sliding-window rate-limit buckets: bucket_name -> {key -> [timestamps]}
        self._rate_buckets: Dict[str, Dict[str, List[float]]] = {}
        # Bounded ephemeral admin Mini App sessions: token -> session dict
        self._admin_sessions: Dict[str, Dict[str, Any]] = {}
        # Single-use 30s evidence download tickets: ticket -> ticket dict
        self._dl_tickets: Dict[str, Dict[str, Any]] = {}
        # Bounded evidence byte cache: cache_key -> (timestamp, bytes)
        self._evidence_cache: Dict[str, Tuple[float, bytes]] = {}
        self._evidence_cache_bytes = 0
        self._ghost_port, self._ghost_origin, self._ghost_host, self._ghost_proto = self._load_ghost_upstream_config()

    def _resolve_bot_token(self) -> str:
        """Resolve Telegram Bot Token from active bot application or environment (never exposed to clients)."""
        if self.bridge and self.bridge.app and getattr(self.bridge.app, "bot", None):
            tok = str(getattr(self.bridge.app.bot, "token", "") or "").strip()
            if tok:
                return tok
        return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip().strip("'\"")

    def _verify_telegram_init_data(self, raw_init_data: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Cryptographically verify Telegram WebApp initData (HMAC-SHA-256 with 'WebAppData' key).
        Returns (status_code_str, parsed_info) where status_code_str is one of:
          'ok', 'unconfigured', 'invalid', 'expired', 'forbidden'
        """
        bot_token = self._resolve_bot_token()
        if not bot_token or bot_token == "your_bot_token_here":
            return "unconfigured", None

        raw = str(raw_init_data or "").strip()
        if not raw or len(raw) > 8192:
            return "invalid", None

        try:
            pairs = urllib.parse.parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        except Exception:
            return "invalid", None

        vals: Dict[str, str] = {}
        received_hash = ""
        for k, v in pairs:
            if k == "hash":
                received_hash = v
            else:
                vals[k] = v

        if not received_hash or not re.fullmatch(r"[0-9a-fA-F]{64}", received_hash):
            return "invalid", None

        data_check_string = "\n".join(f"{k}={vals[k]}" for k in sorted(vals.keys()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed_hash.lower(), received_hash.lower()):
            return "invalid", None

        try:
            auth_date = int(vals.get("auth_date") or "0")
        except (ValueError, TypeError):
            return "invalid", None

        now_ts = int(time.time())
        if auth_date <= 0 or auth_date > now_ts + 60 or (now_ts - auth_date) > max(60, self.ADMIN_INITDATA_MAX_AGE_SEC):
            return "expired", None

        try:
            user_obj = json.loads(vals.get("user") or "{}")
            user_id = int(user_obj.get("id") or 0)
        except Exception:
            return "invalid", None

        if user_id <= 0:
            return "invalid", None

        info = {
            "user_id": user_id,
            "username": str(user_obj.get("username") or "").strip()[:64],
            "first_name": str(user_obj.get("first_name") or "").strip()[:64],
            "last_name": str(user_obj.get("last_name") or "").strip()[:64],
            "start_param": str(vals.get("start_param") or "").strip()[:128],
            "chat_type": str(vals.get("chat_type") or "").strip()[:32],
            "auth_date": auth_date,
        }

        if not self.bridge._is_authorized_user(user_id):
            return "forbidden", info

        return "ok", info

    def _evict_expired_admin_sessions(self):
        now = time.time()
        dead = [
            tok for tok, s in self._admin_sessions.items()
            if (now - s["last_seen"] > self.ADMIN_IDLE_TTL_SEC) or (now > s["hard_expires"])
        ]
        for tok in dead:
            self._admin_sessions.pop(tok, None)
        if len(self._admin_sessions) > 500:
            oldest = sorted(self._admin_sessions.keys(), key=lambda t: self._admin_sessions[t]["last_seen"])[: len(self._admin_sessions) - 400]
            for tok in oldest:
                self._admin_sessions.pop(tok, None)

        dead_tickets = [tk for tk, tv in self._dl_tickets.items() if now > tv["expires_at"]]
        for tk in dead_tickets:
            self._dl_tickets.pop(tk, None)
        if len(self._dl_tickets) > 200:
            oldest_tk = sorted(self._dl_tickets.keys(), key=lambda t: self._dl_tickets[t]["expires_at"])[: len(self._dl_tickets) - 150]
            for tk in oldest_tk:
                self._dl_tickets.pop(tk, None)

    def _create_admin_session(self, info: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        self._evict_expired_admin_sessions()
        now = time.time()
        token = secrets.token_urlsafe(32)
        ua_hash = hashlib.sha256((headers.get("user-agent") or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
        uid = int(info["user_id"])
        sess = {
            "token": token,
            "user_id": uid,
            "username": info.get("username") or "",
            "first_name": info.get("first_name") or "Admin",
            "ua_hash": ua_hash,
            "created_at": now,
            "last_seen": now,
            "hard_expires": now + self.ADMIN_MAX_TTL_SEC,
        }
        self._admin_sessions[token] = sess
        is_super = self.bridge._is_super_admin(uid)
        display_name = sess["first_name"] or (f"@{sess['username']}" if sess["username"] else f"Admin #{uid}")
        return {
            "token": token,
            "expires_in": int(self.ADMIN_IDLE_TTL_SEC),
            "admin": {
                "user_id": uid,
                "username": sess["username"],
                "first_name": sess["first_name"],
                "display_name": display_name,
                "role": "super_admin" if is_super else "support_admin",
                "is_super_admin": is_super,
            },
        }

    def _require_admin_session(self, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Validate Bearer session token AND live Telegram admin allowlist membership on every call."""
        self._evict_expired_admin_sessions()
        auth_hdr = str(headers.get("authorization") or "").strip()
        if not auth_hdr.lower().startswith("bearer "):
            return None
        token = auth_hdr[7:].strip()
        if not token or token not in self._admin_sessions:
            return None
        sess = self._admin_sessions[token]
        now = time.time()
        if (now - sess["last_seen"] > self.ADMIN_IDLE_TTL_SEC) or (now > sess["hard_expires"]):
            self._admin_sessions.pop(token, None)
            return None
        ua_hash = hashlib.sha256((headers.get("user-agent") or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
        if sess.get("ua_hash") and not hmac.compare_digest(sess["ua_hash"], ua_hash):
            return None
        uid = int(sess["user_id"])
        if not self.bridge._is_authorized_user(uid):
            self._admin_sessions.pop(token, None)
            return None
        sess["last_seen"] = now
        is_super = self.bridge._is_super_admin(uid)
        actor_label = (
            f"@{sess['username']} (TG#{uid})"
            if sess.get("username")
            else f"{sess.get('first_name') or 'Admin'} (TG#{uid})"
        )
        return {
            "token": token,
            "user_id": uid,
            "username": sess.get("username") or "",
            "first_name": sess.get("first_name") or "Admin",
            "is_super_admin": is_super,
            "role": "super_admin" if is_super else "support_admin",
            "actor_label": actor_label,
        }

    def _evict_evidence_cache_if_needed(self):
        now = time.time()
        expired = [k for k, (ts, _) in self._evidence_cache.items() if (now - ts) > self.EVIDENCE_CACHE_TTL_SEC]
        for k in expired:
            _, data = self._evidence_cache.pop(k, (0.0, b""))
            self._evidence_cache_bytes = max(0, self._evidence_cache_bytes - len(data))
        while self._evidence_cache_bytes > self.MAX_EVIDENCE_CACHE_BYTES and self._evidence_cache:
            oldest_k = min(self._evidence_cache.keys(), key=lambda x: self._evidence_cache[x][0])
            _, data = self._evidence_cache.pop(oldest_k, (0.0, b""))
            self._evidence_cache_bytes = max(0, self._evidence_cache_bytes - len(data))

    async def _get_or_fetch_evidence_bytes(self, case_code: str, ev_item: Dict[str, Any]) -> Tuple[bytes, str]:
        self._evict_evidence_cache_if_needed()
        ev_id = int(ev_item["id"])
        sha_part = str(ev_item.get("sha256_hash") or "")[:16]
        cache_key = f"{case_code}:{ev_id}:{sha_part}"
        cached = self._evidence_cache.get(cache_key)
        mime = str(ev_item.get("mime_type") or "application/octet-stream")
        if cached is not None:
            return cached[1], mime
        async with self._evidence_dl_sem:
            cached = self._evidence_cache.get(cache_key)
            if cached is not None:
                return cached[1], mime
            data, resolved_mime = await self.bridge.fetch_evidence_bytes(ev_item)
            if len(data) <= 20 * 1024 * 1024:
                self._evidence_cache[cache_key] = (time.time(), data)
                self._evidence_cache_bytes += len(data)
                self._evict_evidence_cache_if_needed()
            return data, resolved_mime

    def _resolve_static_tg_admin_file(self, filename: str) -> Optional[Tuple[bytes, str]]:
        """Serve tg-admin/{index.html, app.css, app.js} strictly from allowlisted files."""
        allowed = {
            "index.html": "text/html; charset=utf-8",
            "app.css": "text/css; charset=utf-8",
            "app.js": "application/javascript; charset=utf-8",
        }
        clean_name = os.path.basename(filename or "")
        if clean_name not in allowed:
            return None
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tg-admin", clean_name),
            os.path.join(self.vault.ghost_dir, "tg-admin", clean_name),
            os.path.join("/var/www/ghost/tg-admin", clean_name),
            os.path.join("/opt/ghost-telegram-bot/tg-admin", clean_name),
        ]
        for p in candidates:
            if os.path.isfile(p):
                with open(p, "rb") as fp:
                    return fp.read(), allowed[clean_name]
        return None

    def _load_ghost_upstream_config(self) -> Tuple[int, str, str, str]:
        """Discover local Ghost port and configured public URL origin from config.*.json."""
        candidates = [
            os.path.join(self.vault.ghost_dir, "config.production.json"),
            os.path.join(self.vault.ghost_dir, "config.development.json"),
            "/var/www/ghost/config.production.json",
        ]
        for cfg_path in candidates:
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    port = int(cfg.get("server", {}).get("port", 2368) or 2368)
                    raw_url = str(cfg.get("url", "") or "").strip().rstrip("/")
                    if raw_url:
                        parsed = urllib.parse.urlparse(raw_url)
                        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
                        host_hdr = parsed.netloc or "localhost"
                        proto_hdr = parsed.scheme or "https"
                        return port, origin, host_hdr, proto_hdr
                except Exception:
                    pass
        return 2368, "", "localhost", "https"

    def _check_rate_limit(self, bucket: str, key: str, max_hits: int, window_sec: float) -> bool:
        """Return True if key is rate-limited in bucket; enforces memory bounds (HIGH-02 / MED-08)."""
        now = time.time()
        store = self._rate_buckets.setdefault(bucket, {})
        timestamps = [t for t in store.get(key, []) if now - t < window_sec]
        if not timestamps:
            store.pop(key, None)
        if len(timestamps) >= max_hits:
            store[key] = timestamps
            return True
        timestamps.append(now)
        store[key] = timestamps

        # Periodic eviction to bound dictionary size
        if len(store) > 5000:
            stale_keys = [k for k, ts_list in store.items() if not ts_list or (now - ts_list[-1] >= window_sec)]
            for k in stale_keys:
                store.pop(k, None)
            if len(store) > 5000:
                oldest_keys = sorted(store.keys(), key=lambda k: store[k][-1])[: len(store) - 4000]
                for k in oldest_keys:
                    store.pop(k, None)
        return False

    def _is_rate_limited(self, ip: str) -> bool:
        return self._check_rate_limit("create_case", ip, max_hits=6, window_sec=3600)

    def _extract_client_ip(self, writer: asyncio.StreamWriter, headers: Dict[str, str]) -> str:
        """Extract client IP safely without trusting spoofed leftmost X-Forwarded-For values (MED-08)."""
        peer = writer.get_extra_info("peername")
        peer_ip = str(peer[0]) if isinstance(peer, tuple) and peer else "127.0.0.1"
        is_loopback_peer = peer_ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
        if not is_loopback_peer:
            return peer_ip
        real_ip = headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
        xff = headers.get("x-forwarded-for", "").strip()
        if xff:
            # Rightmost entry is appended by local trusted reverse proxy ($proxy_add_x_forwarded_for)
            return xff.split(",")[-1].strip() or peer_ip
        return peer_ip

    async def _verify_ghost_member_cookie(self, cookie_header: str) -> Optional[Dict[str, str]]:
        """Verify Ghost member SSR session cookie against local Ghost /members/api/member/ (HIGH-01)."""
        if not cookie_header or "ghost-members-ssr" not in cookie_header:
            return None

        def _query_ghost() -> Optional[Dict[str, str]]:
            url = f"http://127.0.0.1:{self._ghost_port}/members/api/member/"
            req = urllib.request.Request(
                url,
                headers={
                    "Cookie": cookie_header,
                    "Host": self._ghost_host,
                    "X-Forwarded-Proto": self._ghost_proto,
                    "Accept": "application/json",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status != 200:
                        return None
                    raw = resp.read(65536)
                    if not raw:
                        return None
                    data = json.loads(raw.decode("utf-8", errors="replace"))
                    m_uuid = str(data.get("uuid") or "").strip()
                    m_email = str(data.get("email") or "").strip().lower()
                    m_name = str(data.get("name") or "").strip()
                    if m_uuid and m_email:
                        return {"uuid": m_uuid, "email": m_email, "name": m_name}
            except Exception:
                return None
            return None

        return await asyncio.to_thread(_query_ghost)

    async def _is_case_authorized(self, case_data: Dict[str, Any], provided_key: str, cookie_header: str) -> bool:
        """Constant-time access_key check with verified Ghost member session fallback (HIGH-01 / MED-06)."""
        stored_key = str(case_data.get("access_key") or "")
        if provided_key and stored_key and hmac.compare_digest(stored_key.encode("utf-8"), provided_key.encode("utf-8")):
            return True
        # Allow authenticated Ghost member to access their own linked case without exposing access_key in bulk lists
        case_uuid = str(case_data.get("member_uuid") or "").strip()
        case_email = str(case_data.get("member_email") or "").strip().lower()
        if case_uuid and case_email and cookie_header:
            verified = await self._verify_ghost_member_cookie(cookie_header)
            if verified:
                uuid_ok = hmac.compare_digest(case_uuid.encode("utf-8"), verified["uuid"].encode("utf-8"))
                email_ok = hmac.compare_digest(case_email.encode("utf-8"), verified["email"].encode("utf-8"))
                if uuid_ok and email_ok:
                    return True
        return False

    def _resolve_cors_origin(self, request_origin: str) -> Optional[str]:
        if not request_origin:
            return None
        clean_origin = request_origin.strip().rstrip("/")
        allowed = set()
        if self._ghost_origin:
            allowed.add(self._ghost_origin)
        allowed.update({
            f"http://localhost:{self._ghost_port}",
            f"http://127.0.0.1:{self._ghost_port}",
            f"http://localhost:{self.port}",
            f"http://127.0.0.1:{self.port}",
        })
        return clean_origin if clean_origin in allowed else None

    async def start(self):
        try:
            self.server = await asyncio.start_server(self.handle_client, self.host, self.port, limit=16384)
            logger.info("Support REST API server active on http://%s:%d", self.host, self.port)
        except OSError as e:
            if getattr(e, 'errno', None) in (98, 10048) or "address already in use" in str(e).lower():
                logger.warning("Port %d on %s is already in use by an active daemon. HTTP listener skipped (daemon online).", self.port, self.host)
                self.server = None
            else:
                raise

    async def stop(self):
        if self.server:
            try:
                self.server.close()
                await self.server.wait_closed()
                logger.info("Support REST API server stopped.")
            except Exception as e:
                logger.error("Error stopping Support REST API server: %s", e)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        async with self._conn_sem:
            await self._handle_client_inner(reader, writer)

    async def _handle_client_inner(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        req_origin = ""
        try:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=15.0)
            except (asyncio.TimeoutError, asyncio.LimitOverrunError, ValueError):
                return
            if not line or len(line) > self.MAX_HEADER_LINE_BYTES:
                return
            parts = line.decode('utf-8', errors='ignore').strip().split()
            if len(parts) < 2:
                return
            method, path = parts[0].upper(), parts[1]

            headers: Dict[str, str] = {}
            header_count = 0
            while True:
                try:
                    hline = await asyncio.wait_for(reader.readline(), timeout=10.0)
                except (asyncio.TimeoutError, asyncio.LimitOverrunError, ValueError):
                    await self._send_response(writer, 400, {"error": "Malformed or slow request headers."})
                    return
                if hline in (b'\r\n', b'\n', b''):
                    break
                header_count += 1
                if header_count > self.MAX_HEADER_COUNT or len(hline) > self.MAX_HEADER_LINE_BYTES:
                    await self._send_response(writer, 400, {"error": "Request headers exceed security limits."})
                    return
                hstr = hline.decode('utf-8', errors='ignore')
                hparts = hstr.split(':', 1)
                if len(hparts) == 2:
                    headers[hparts[0].strip().lower()] = hparts[1].strip()

            req_origin = headers.get("origin", "")

            try:
                content_len = int(headers.get('content-length', '0') or '0')
            except ValueError:
                await self._send_response(writer, 400, {"error": "Invalid Content-Length header."}, req_origin=req_origin)
                return

            if content_len < 0:
                await self._send_response(writer, 400, {"error": "Negative Content-Length is not permitted."}, req_origin=req_origin)
                return
            if content_len > self.MAX_BODY_BYTES:
                await self._send_response(writer, 413, {"error": "Payload exceeds 50MB limit"}, req_origin=req_origin)
                return

            body = b''
            if content_len > 0:
                try:
                    if content_len >= self.LARGE_UPLOAD_THRESHOLD:
                        async with self._upload_sem:
                            body = await asyncio.wait_for(reader.readexactly(content_len), timeout=60.0)
                    else:
                        body = await asyncio.wait_for(reader.readexactly(content_len), timeout=30.0)
                except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                    await self._send_response(writer, 400, {"error": "Request body read timed out or truncated."}, req_origin=req_origin)
                    return

            client_ip = self._extract_client_ip(writer, headers)
            ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

            # Route handling
            if method == "OPTIONS":
                cors_origin = self._resolve_cors_origin(req_origin)
                header_lines = [
                    "HTTP/1.1 204 No Content",
                    "Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Case-Key, X-Preview",
                    "Access-Control-Max-Age: 86400",
                    "X-Content-Type-Options: nosniff",
                    "Cross-Origin-Opener-Policy: same-origin",
                    "Cross-Origin-Resource-Policy: same-origin",
                    "X-Permitted-Cross-Domain-Policies: none",
                    "Content-Length: 0",
                    "Connection: close",
                ]
                if cors_origin:
                    header_lines.insert(1, f"Access-Control-Allow-Origin: {cors_origin}")
                    header_lines.insert(2, "Vary: Origin")
                header_lines.extend(["", ""])
                writer.write("\r\n".join(header_lines).encode('utf-8'))
                await writer.drain()
                return

            clean_path = path.split('?')[0].rstrip('/')
            route_path = clean_path
            if route_path.startswith("/api/support"):
                route_path = route_path[len("/api/support"):]
            if not route_path.startswith("/"):
                route_path = "/" + route_path

            query: Dict[str, str] = {}
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
                    "version": "1.1.0",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /captcha (Obtain Cryptographic Security Challenge)
            # -------------------------------------------------------------
            elif method == "GET" and route_path == "/captcha":
                if self._check_rate_limit("captcha", client_ip, max_hits=30, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Too many challenge requests. Please wait briefly."}, req_origin=req_origin)
                    return
                challenge = self.captcha.generate_challenge()
                await self._send_response(writer, 200, challenge, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # POST /csp-report (CSP Violation Telemetry Ingestion)
            # -------------------------------------------------------------
            elif method == "POST" and route_path in ("/csp-report", "/csp-reports", "/report"):
                if self._check_rate_limit("csp_report", client_ip, max_hits=60, window_sec=60):
                    await self._send_response(writer, 429, {"error": "Too many reports."}, req_origin=req_origin)
                    return
                if len(body) > 65536:
                    await self._send_response(writer, 413, {"error": "Report payload too large."}, req_origin=req_origin)
                    return
                try:
                    raw_payload = json.loads(body.decode("utf-8", errors="ignore") or "{}")
                    reports: List[Dict[str, Any]] = []
                    if isinstance(raw_payload, list):
                        for item in raw_payload[:20]:
                            if isinstance(item, dict):
                                inner = item.get("body") if isinstance(item.get("body"), dict) else item
                                reports.append({
                                    "format": "reports+json",
                                    "type": str(item.get("type", ""))[:64],
                                    "url": str(item.get("url", ""))[:512],
                                    "document_uri": str(inner.get("documentURL") or inner.get("document-uri") or "")[:512],
                                    "blocked_uri": str(inner.get("blockedURL") or inner.get("blocked-uri") or "")[:512],
                                    "directive": str(inner.get("effectiveDirective") or inner.get("violated-directive") or "")[:128],
                                    "disposition": str(inner.get("disposition", ""))[:32],
                                    "source_file": str(inner.get("sourceFile") or inner.get("source-file") or "")[:512],
                                    "line": inner.get("lineNumber") or inner.get("line-number"),
                                })
                    elif isinstance(raw_payload, dict):
                        inner = raw_payload.get("csp-report") if isinstance(raw_payload.get("csp-report"), dict) else raw_payload
                        reports.append({
                            "format": "csp-report" if "csp-report" in raw_payload else "json",
                            "document_uri": str(inner.get("document-uri") or inner.get("documentURL") or "")[:512],
                            "blocked_uri": str(inner.get("blocked-uri") or inner.get("blockedURL") or "")[:512],
                            "directive": str(inner.get("effective-directive") or inner.get("violated-directive") or inner.get("effectiveDirective") or "")[:128],
                            "disposition": str(inner.get("disposition", ""))[:32],
                            "source_file": str(inner.get("source-file") or inner.get("sourceFile") or "")[:512],
                            "line": inner.get("line-number") or inner.get("lineNumber"),
                        })
                    if reports:
                        violations_log = os.path.join(self.vault.vault_dir, "csp_violations.log")
                        ts_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        with open(violations_log, "a", encoding="utf-8") as vf:
                            for rep in reports:
                                vf.write(json.dumps({
                                    "ts": ts_now,
                                    "ip_hash": ip_hash,
                                    "report": rep
                                }) + "\n")
                        try:
                            os.chmod(violations_log, 0o600)
                        except OSError:
                            pass
                except Exception as err:
                    logger.debug("CSP report parsing error: %s", err)
                await self._send_response(writer, 204, None, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # POST /cases (Case Submission - JSON or Multipart)
            # -------------------------------------------------------------
            elif method == "POST" and route_path == "/cases":
                if self._is_rate_limited(client_ip):
                    await self._send_response(writer, 429, {"error": "Submission rate limit exceeded. Please wait a while before submitting again."}, req_origin=req_origin)
                    return

                ctype = headers.get('content-type', '')
                params: Dict[str, Any] = {}
                evidence_files: List[Dict[str, Any]] = []

                if "application/json" in ctype:
                    try:
                        params = json.loads(body.decode('utf-8'))
                        body = b''
                    except Exception as e:
                        logger.warning("JSON parse error: %s", e)
                        await self._send_response(writer, 400, {"error": "Invalid JSON payload."}, req_origin=req_origin)
                        return
                elif "multipart/form-data" in ctype:
                    try:
                        msg_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode('utf-8') + body
                        body = b''
                        msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
                        del msg_bytes
                        for part in msg.iter_parts():
                            name = part.get_param('name', header='content-disposition')
                            filename = part.get_filename()
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue
                            if filename:
                                if len(payload) > self.MAX_EVIDENCE_BYTES:
                                    await self._send_response(writer, 413, {"error": f"Attachment '{os.path.basename(filename)}' exceeds the 20 MB per-file limit."}, req_origin=req_origin)
                                    return
                                if len(evidence_files) < 10:
                                    evidence_files.append({"filename": filename, "data": payload, "mime": part.get_content_type()})
                            elif name:
                                params[name] = payload.decode('utf-8', errors='replace').strip()
                        del msg
                    except Exception as e:
                        logger.warning("Multipart parse error: %s", e)
                        await self._send_response(writer, 400, {"error": "Failed to parse multipart upload."}, req_origin=req_origin)
                        return
                else:
                    try:
                        params = json.loads(body.decode('utf-8'))
                        body = b''
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Unsupported Content-Type. Please use application/json or multipart/form-data."}, req_origin=req_origin)
                        return

                # Verify Security Challenge / Anti-Flooding Captcha + PoW
                c_id = str(params.get("captcha_id", "") or "").strip()
                try:
                    c_ts = int(params.get("captcha_timestamp", 0) or 0)
                except (ValueError, TypeError):
                    c_ts = 0
                c_sig = str(params.get("captcha_signature", "") or "").strip()
                c_sol = str(params.get("captcha_solution", "") or "").strip()
                c_nonce = str(params.get("captcha_nonce", "") or "").strip()

                if not c_id or not c_sig or not c_sol or not c_nonce:
                    await self._send_response(writer, 400, {"error": "Please solve the calculation puzzle to verify your submission."}, req_origin=req_origin)
                    return

                if not self.captcha.verify_challenge(c_id, c_ts, c_sig, c_sol, c_nonce):
                    await self._send_response(writer, 403, {"error": "Security verification failed or expired. Please solve the updated puzzle."}, req_origin=req_origin)
                    return

                subject = str(params.get("subject", "") or "").strip()[:300]
                description = str(params.get("description", "") or "").strip()[:20000]
                category = str(params.get("category", "Incident Report") or "Incident Report").strip()[:100]
                priority = str(params.get("priority", "STANDARD") or "STANDARD").strip().upper()[:32]
                alias = (str(params.get("reporter_alias", "Anonymous") or "").strip() or "Anonymous")[:120]
                contact = str(params.get("reporter_contact", "") or "").strip()[:200]
                req_member_email = str(params.get("member_email", "") or "").strip().lower()
                req_member_uuid = str(params.get("member_uuid", "") or "").strip()

                if not subject or not description:
                    await self._send_response(writer, 400, {"error": "Subject and Detailed Description are required fields."}, req_origin=req_origin)
                    return

                # Only bind member identity if verified against Ghost's signed session cookie (HIGH-01)
                verified_email: Optional[str] = None
                verified_uuid: Optional[str] = None
                if req_member_email or req_member_uuid:
                    verified_member = await self._verify_ghost_member_cookie(headers.get("cookie", ""))
                    if verified_member:
                        verified_email = verified_member["email"]
                        verified_uuid = verified_member["uuid"]

                # Create case in DB
                case_res = self.vault.create_case(
                    category=category,
                    priority=priority,
                    subject=subject,
                    description=description,
                    reporter_alias=alias,
                    reporter_contact=contact,
                    ip_hash=ip_hash,
                    member_email=verified_email,
                    member_uuid=verified_uuid
                )
                case_code = case_res["case_code"]

                # Save sanitized evidence files (uploaded directly to Telegram Storage Group with zero VPS disk retention)
                saved_files = []
                for ef in evidence_files:
                    saved = await self.bridge.store_evidence(case_code, ef["filename"], ef["data"], ef.get("mime"))
                    ef["data"] = b""
                    saved_files.append(saved)
                evidence_files.clear()

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
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /member/cases or /cases/member (List Member's Past Cases)
            # -------------------------------------------------------------
            elif method == "GET" and route_path in ("/member/cases", "/cases/member"):
                if self._check_rate_limit("member_cases", client_ip, max_hits=30, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Rate limit exceeded."}, req_origin=req_origin)
                    return

                verified_member = await self._verify_ghost_member_cookie(headers.get("cookie", ""))
                if not verified_member:
                    await self._send_response(writer, 401, {"error": "Authentication required: Valid Ghost member session cookie is missing or expired."}, req_origin=req_origin)
                    return

                cases = self.vault.list_member_cases(
                    member_email=verified_member["email"],
                    member_uuid=verified_member["uuid"]
                )
                await self._send_response(writer, 200, {
                    "success": True,
                    "cases": cases
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /cases/<case_code>/evidence/<file_id> (Stream Evidence File - RESTRICTED TO BOT)
            # -------------------------------------------------------------
            elif method == "GET" and "/evidence/" in route_path and route_path.startswith("/cases/"):
                await self._send_response(writer, 403, {
                    "error": "Direct web access to uploaded evidence is disabled for operational security. "
                             "Evidence files are sequestered in an isolated vault and accessible exclusively "
                             "by duty investigators via the verified operational Telegram Bot.",
                    "vault_status": "SECURED"
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /cases/<case_code> (Fetch Case Status & Chat)
            # -------------------------------------------------------------
            elif method == "GET" and route_path.startswith("/cases/") and not route_path.endswith("/messages"):
                if self._check_rate_limit("case_lookup", client_ip, max_hits=120, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Too many lookup requests. Please slow down."}, req_origin=req_origin)
                    return

                parts = [p for p in route_path.split("/") if p]
                if len(parts) < 2:
                    await self._send_response(writer, 400, {"error": "Invalid case endpoint format."}, req_origin=req_origin)
                    return
                case_code = parts[1]
                access_key = (headers.get("x-case-key", "") or query.get("key", "")).strip()
                case_data = self.vault.get_case(case_code)
                if not case_data:
                    await self._send_response(writer, 404, {"error": "Case not found."}, req_origin=req_origin)
                    return

                if not await self._is_case_authorized(case_data, access_key, headers.get("cookie", "")):
                    await self._send_response(writer, 403, {"error": "Invalid or missing Case Access Key."}, req_origin=req_origin)
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
                        "vault_status": "SECURED"
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
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # POST /cases/<case_code>/messages (Reporter Chat)
            # -------------------------------------------------------------
            elif method == "POST" and route_path.startswith("/cases/") and route_path.endswith("/messages"):
                if self._check_rate_limit("case_msg_ip", client_ip, max_hits=25, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Message rate limit exceeded. Please wait briefly before sending more messages."}, req_origin=req_origin)
                    return

                parts = [p for p in route_path.split("/") if p]
                if len(parts) < 3:
                    await self._send_response(writer, 400, {"error": "Invalid message endpoint format."}, req_origin=req_origin)
                    return
                case_code = parts[1]
                if self._check_rate_limit("case_msg_code", case_code, max_hits=20, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Too many messages posted to this case recently."}, req_origin=req_origin)
                    return

                case_data = self.vault.get_case(case_code)
                if not case_data:
                    await self._send_response(writer, 404, {"error": "Case not found."}, req_origin=req_origin)
                    return

                ctype = headers.get('content-type', '')
                text = ""
                key = headers.get("x-case-key", "").strip()
                attached_file = None
                if "application/json" in ctype:
                    try:
                        p = json.loads(body.decode('utf-8'))
                        body = b''
                        text = str(p.get("message", "") or "").strip()[:10000]
                        key = str(p.get("key", "") or key).strip()
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Invalid JSON"}, req_origin=req_origin)
                        return
                elif "multipart/form-data" in ctype:
                    try:
                        msg_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode('utf-8') + body
                        body = b''
                        msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
                        del msg_bytes
                        for part in msg.iter_parts():
                            name = part.get_param('name', header='content-disposition')
                            filename = part.get_filename()
                            payload = part.get_payload(decode=True)
                            if filename and payload and attached_file is None:
                                attached_file = {"filename": filename, "data": payload, "mime": part.get_content_type()}
                            elif name == "message" and payload:
                                text = payload.decode('utf-8', errors='replace').strip()[:10000]
                            elif name == "key" and payload:
                                key = payload.decode('utf-8', errors='replace').strip()
                        del msg
                    except Exception:
                        pass
                else:
                    try:
                        p = json.loads(body.decode('utf-8'))
                        body = b''
                        text = str(p.get("message", "") or "").strip()[:10000]
                        key = str(p.get("key", "") or key).strip()
                    except Exception:
                        pass

                if not await self._is_case_authorized(case_data, key, headers.get("cookie", "")):
                    await self._send_response(writer, 403, {"error": "Invalid or missing Case Access Key."}, req_origin=req_origin)
                    return

                if not text and not attached_file:
                    await self._send_response(writer, 400, {"error": "Message text or attachment is required."}, req_origin=req_origin)
                    return

                if attached_file:
                    if len(attached_file["data"]) > self.MAX_EVIDENCE_BYTES:
                        attached_file["data"] = b""
                        await self._send_response(writer, 413, {"error": "Attachment exceeds the 20 MB per-file limit."}, req_origin=req_origin)
                        return
                    existing_files = case_data.get("files") or []
                    if len(existing_files) >= self.MAX_FILES_PER_CASE:
                        await self._send_response(writer, 429, {"error": f"Maximum attachment limit ({self.MAX_FILES_PER_CASE} files) reached for this case."}, req_origin=req_origin)
                        return
                    saved_ev = await self.bridge.store_evidence(case_code, attached_file["filename"], attached_file["data"], attached_file.get("mime"))
                    attached_file["data"] = b""
                    safe_disp_name = saved_ev.get("original_name") or "attachment"
                    text = f"📁 [{safe_disp_name}]\n{text}" if text else f"📁 [{safe_disp_name}]"

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
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # Static Mini App Shell Fallback (/webapp/* or /tg-admin/* for standalone local dev)
            # -------------------------------------------------------------
            elif method == "GET" and (route_path in ("/webapp", "/tg-admin") or route_path.startswith("/webapp/") or route_path.startswith("/tg-admin/")):
                rel = "index.html"
                if route_path.endswith("/app.css"):
                    rel = "app.css"
                elif route_path.endswith("/app.js"):
                    rel = "app.js"
                elif route_path not in ("/webapp", "/tg-admin"):
                    await self._send_response(writer, 404, {"error": "Mini App asset not found."}, req_origin=req_origin)
                    return
                loaded = self._resolve_static_tg_admin_file(rel)
                if not loaded:
                    await self._send_response(writer, 404, {"error": "Mini App assets not installed on server."}, req_origin=req_origin)
                    return
                raw_bytes, mime = loaded
                webapp_csp = (
                    "default-src 'none'; base-uri 'self'; form-action 'none'; "
                    "frame-ancestors 'self' https://web.telegram.org; "
                    "script-src 'self' https://telegram.org; "
                    "style-src 'self' https://fonts.googleapis.com; "
                    "font-src 'self' data: https://fonts.gstatic.com; "
                    "img-src 'self' data: blob:; media-src 'self' blob:; "
                    "connect-src 'self'; frame-src 'self' blob:"
                )
                extra_headers = [
                    f"Content-Security-Policy: {webapp_csp}",
                    "Cross-Origin-Opener-Policy: same-origin-allow-popups",
                    "Cross-Origin-Resource-Policy: cross-origin",
                    "X-Content-Type-Options: nosniff",
                    "X-Permitted-Cross-Domain-Policies: none",
                    "Referrer-Policy: no-referrer",
                    "Cache-Control: no-store",
                ]
                await self._send_bytes_response(writer, 200, "OK", raw_bytes, mime, extra_headers=extra_headers)
                return

            # -------------------------------------------------------------
            # POST /admin/auth (Exchange Telegram Mini App initData for Bearer Session)
            # -------------------------------------------------------------
            elif method == "POST" and route_path == "/admin/auth":
                if self._check_rate_limit("admin_auth", client_ip, max_hits=15, window_sec=300):
                    await self._send_response(writer, 429, {"error": "Too many authentication attempts. Please wait briefly."}, req_origin=req_origin)
                    return
                try:
                    p = json.loads(body.decode("utf-8"))
                    body = b""
                except Exception:
                    await self._send_response(writer, 400, {"error": "Invalid JSON body."}, req_origin=req_origin)
                    return

                raw_init_data = str(p.get("init_data", "") or "")
                status_tag, info = self._verify_telegram_init_data(raw_init_data)
                if status_tag == "unconfigured":
                    await self._send_response(writer, 503, {"error": "Telegram bot token is not configured on this server."}, req_origin=req_origin)
                    return
                if status_tag == "expired":
                    await self._send_response(writer, 401, {"error": "Telegram session expired. Re-open the Case Console from Telegram."}, req_origin=req_origin)
                    return
                if status_tag == "invalid" or not info:
                    await self._send_response(writer, 401, {"error": "Invalid Telegram Mini App signature."}, req_origin=req_origin)
                    return
                if status_tag == "forbidden":
                    denied_uid = info.get("user_id")
                    self.vault.record_admin_audit("__SYSTEM__", "ADMIN_WEBAPP_DENIED", f"TG#{denied_uid}", f"ip={ip_hash}")
                    await self._send_response(writer, 403, {"error": "Access Denied: Your Telegram account is not an authorized support admin."}, req_origin=req_origin)
                    return

                sess_payload = self._create_admin_session(info, headers)
                actor_name = sess_payload["admin"]["display_name"]
                self.vault.record_admin_audit("__SYSTEM__", "ADMIN_WEBAPP_LOGIN", f"{actor_name} (TG#{info['user_id']})", f"ip={ip_hash}")
                await self._send_response(writer, 200, {
                    "success": True,
                    **sess_payload,
                    "start_param": info.get("start_param") or "",
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # POST /admin/logout
            # -------------------------------------------------------------
            elif method == "POST" and route_path == "/admin/logout":
                sess = self._require_admin_session(headers)
                if sess:
                    self._admin_sessions.pop(sess["token"], None)
                await self._send_response(writer, 200, {"success": True}, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /admin/cases (Admin Case Inbox List)
            # -------------------------------------------------------------
            elif method == "GET" and route_path == "/admin/cases":
                sess = self._require_admin_session(headers)
                if not sess:
                    await self._send_response(writer, 401, {"error": "Unauthorized or expired Telegram admin session."}, req_origin=req_origin)
                    return
                if self._check_rate_limit("admin_api", str(sess["user_id"]), max_hits=240, window_sec=60):
                    await self._send_response(writer, 429, {"error": "Rate limit exceeded."}, req_origin=req_origin)
                    return

                filter_status = (query.get("status") or "").strip().upper()
                search_q = (query.get("q") or "").strip()
                all_for_counts = self.vault.list_cases_admin(status=None, q=None, limit=200, viewer_admin_id=sess["user_id"])
                counts = {"ALL": len(all_for_counts), "SUBMITTED": 0, "IN_REVIEW": 0, "CLOSED": 0, "REJECTED": 0, "UNREAD": 0}
                for item in all_for_counts:
                    st = str(item.get("status") or "SUBMITTED").upper()
                    if st in counts:
                        counts[st] += 1
                    if item.get("unread"):
                        counts["UNREAD"] += 1

                if not filter_status and not search_q:
                    cases = all_for_counts[:80]
                else:
                    cases = self.vault.list_cases_admin(
                        status=filter_status or None,
                        q=search_q or None,
                        limit=80,
                        viewer_admin_id=sess["user_id"],
                    )
                await self._send_response(writer, 200, {
                    "success": True,
                    "cases": cases,
                    "counts": counts,
                    "admin": {
                        "user_id": sess["user_id"],
                        "role": sess["role"],
                        "is_super_admin": sess["is_super_admin"],
                    },
                }, req_origin=req_origin)
                return

            # -------------------------------------------------------------
            # GET /admin/dl/<ticket> (Single-Use Ticket Download for Native Client)
            # -------------------------------------------------------------
            elif method == "GET" and route_path.startswith("/admin/dl/"):
                parts = [p for p in route_path.split("/") if p]
                ticket = parts[2] if len(parts) == 3 else ""
                tinfo = self._dl_tickets.pop(ticket, None)
                if not tinfo or time.time() > tinfo.get("expires_at", 0):
                    await self._send_response(writer, 403, {"error": "Download link is invalid or has expired."}, req_origin=req_origin)
                    return
                if not self.bridge._is_authorized_user(tinfo.get("admin_id")):
                    await self._send_response(writer, 403, {"error": "Admin authorization revoked."}, req_origin=req_origin)
                    return
                ev_item = self.vault.get_evidence_item(tinfo["case_code"], tinfo["ev_id"])
                if not ev_item:
                    await self._send_response(writer, 404, {"error": "Evidence file not found."}, req_origin=req_origin)
                    return
                try:
                    ev_bytes, _ = await self._get_or_fetch_evidence_bytes(tinfo["case_code"], ev_item)
                except EvidenceTooLargeError as exc:
                    await self._send_response(writer, 413, {"error": str(exc), "too_large_for_webapp": True}, req_origin=req_origin)
                    return
                except FileNotFoundError:
                    await self._send_response(writer, 404, {"error": "Evidence bytes are no longer available."}, req_origin=req_origin)
                    return

                dl_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(ev_item.get("original_name") or "evidence.bin"))[:120]
                extra_headers = [
                    "Content-Security-Policy: default-src 'none'; sandbox; frame-ancestors 'none'",
                    "X-Content-Type-Options: nosniff",
                    "X-Frame-Options: DENY",
                    "Cross-Origin-Opener-Policy: same-origin",
                    "Cross-Origin-Resource-Policy: same-origin",
                    "X-Permitted-Cross-Domain-Policies: none",
                    "Cache-Control: no-store",
                    f'Content-Disposition: attachment; filename="{dl_name}"',
                ]
                await self._send_bytes_response(writer, 200, "OK", ev_bytes, "application/octet-stream", extra_headers=extra_headers)
                return

            # -------------------------------------------------------------
            # Admin Case-Scoped Endpoints (/admin/cases/<case_code>/...)
            # -------------------------------------------------------------
            elif route_path.startswith("/admin/cases/"):
                sess = self._require_admin_session(headers)
                if not sess:
                    await self._send_response(writer, 401, {"error": "Unauthorized or expired Telegram admin session."}, req_origin=req_origin)
                    return
                if self._check_rate_limit("admin_api", str(sess["user_id"]), max_hits=240, window_sec=60):
                    await self._send_response(writer, 429, {"error": "Rate limit exceeded."}, req_origin=req_origin)
                    return

                parts = [p for p in route_path.split("/") if p]
                # parts: ['admin', 'cases', '<case_code>', ...]
                if len(parts) < 3 or not re.fullmatch(r"[A-Za-z0-9-]+", parts[2]):
                    await self._send_response(writer, 400, {"error": "Invalid case identifier."}, req_origin=req_origin)
                    return
                case_code = parts[2].upper()
                case_data = self.vault.get_case(case_code)
                if not case_data:
                    await self._send_response(writer, 404, {"error": f"Case #{case_code} not found."}, req_origin=req_origin)
                    return

                # GET /admin/cases/<code>
                if method == "GET" and len(parts) == 3:
                    msgs = case_data.get("messages") or []
                    if msgs:
                        self.vault.mark_case_read(case_code, sess["user_id"], int(msgs[-1].get("id") or 0))
                    else:
                        self.vault.mark_case_read(case_code, sess["user_id"], 1)

                    safe_files = []
                    for f in case_data.get("files", []):
                        orig_name = str(f.get("original_name") or "evidence.bin")
                        ext = os.path.splitext(orig_name)[1].lower()
                        f_size = int(f.get("file_size") or 0)
                        safe_files.append({
                            "id": f["id"],
                            "name": orig_name,
                            "size": f_size,
                            "mime": f.get("mime_type") or "application/octet-stream",
                            "sha256": f.get("sha256_hash") or "",
                            "created_at": f.get("created_at"),
                            "storage": "telegram" if f.get("telegram_file_id") else "local",
                            "previewable": ext in self.SAFE_PREVIEW_EXTS and f_size <= self.MAX_EVIDENCE_BYTES,
                            "can_direct_dl": f_size <= self.MAX_EVIDENCE_BYTES,
                        })

                    await self._send_response(writer, 200, {
                        "success": True,
                        "case": {
                            "case_code": case_data["case_code"],
                            "category": case_data["category"],
                            "priority": case_data["priority"],
                            "status": case_data["status"],
                            "subject": case_data["subject"],
                            "description": case_data["description"],
                            "reporter_alias": case_data.get("reporter_alias") or "Anonymous",
                            "reporter_contact": case_data.get("reporter_contact") or "",
                            "member_email": case_data.get("member_email") or "",
                            "assigned_admin_id": case_data.get("assigned_admin_id"),
                            "assigned_admin_name": case_data.get("assigned_admin_name"),
                            "resolution_note": case_data.get("resolution_note") or "",
                            "created_at": case_data["created_at"],
                            "updated_at": case_data["updated_at"],
                            "files": safe_files,
                            "messages": msgs,
                            "audit_logs": case_data.get("audit_logs", []),
                        },
                    }, req_origin=req_origin)
                    return

                # POST /admin/cases/<code>/claim
                elif method == "POST" and len(parts) == 4 and parts[3] == "claim":
                    try:
                        p = json.loads(body.decode("utf-8")) if body else {}
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Invalid JSON body."}, req_origin=req_origin)
                        return
                    action = str(p.get("action") or "claim").strip().lower()
                    if action == "release":
                        cur_owner = case_data.get("assigned_admin_id")
                        if cur_owner and int(cur_owner) != sess["user_id"] and not sess["is_super_admin"]:
                            await self._send_response(writer, 403, {"error": "Only the assigned admin or a Super Admin can release this claim."}, req_origin=req_origin)
                            return
                        self.vault.assign_case(case_code, None, None, actor=sess["actor_label"])
                        await self._send_response(writer, 200, {"success": True, "assigned_admin_id": None, "assigned_admin_name": None}, req_origin=req_origin)
                        return
                    assignee_name = sess["first_name"] or (f"@{sess['username']}" if sess["username"] else f"Admin #{sess['user_id']}")
                    self.vault.assign_case(case_code, sess["user_id"], assignee_name, actor=sess["actor_label"])
                    await self._send_response(writer, 200, {"success": True, "assigned_admin_id": sess["user_id"], "assigned_admin_name": assignee_name}, req_origin=req_origin)
                    return

                # POST /admin/cases/<code>/status
                elif method == "POST" and len(parts) == 4 and parts[3] == "status":
                    try:
                        p = json.loads(body.decode("utf-8")) if body else {}
                    except Exception:
                        await self._send_response(writer, 400, {"error": "Invalid JSON body."}, req_origin=req_origin)
                        return
                    new_status = str(p.get("status") or "").strip().upper()
                    if new_status not in ("SUBMITTED", "IN_REVIEW", "CLOSED", "REJECTED"):
                        await self._send_response(writer, 400, {"error": "Invalid status value."}, req_origin=req_origin)
                        return
                    note = str(p.get("resolution_note") or "").strip()[:1000] or None
                    self.vault.update_status(case_code, new_status, actor=sess["actor_label"], note=note)
                    asyncio.create_task(self.bridge.sync_ops_card_status(case_code))
                    await self._send_response(writer, 200, {"success": True, "status": new_status, "resolution_note": note or ""}, req_origin=req_origin)
                    return

                # POST /admin/cases/<code>/messages (Admin WebApp Chat Reply + Optional Evidence)
                elif method == "POST" and len(parts) == 4 and parts[3] == "messages":
                    ctype = headers.get("content-type", "")
                    text = ""
                    attached_file = None
                    if "multipart/form-data" in ctype:
                        try:
                            msg_bytes = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
                            body = b""
                            msg = BytesParser(policy=policy.default).parsebytes(msg_bytes)
                            del msg_bytes
                            for part in msg.iter_parts():
                                name = part.get_param("name", header="content-disposition")
                                filename = part.get_filename()
                                payload = part.get_payload(decode=True)
                                if filename and payload and attached_file is None:
                                    attached_file = {"filename": filename, "data": payload, "mime": part.get_content_type()}
                                elif name == "message" and payload:
                                    text = payload.decode("utf-8", errors="replace").strip()[:10000]
                            del msg
                        except Exception:
                            await self._send_response(writer, 400, {"error": "Failed to parse multipart message payload."}, req_origin=req_origin)
                            return
                    else:
                        try:
                            p = json.loads(body.decode("utf-8")) if body else {}
                            body = b""
                            text = str(p.get("message", "") or "").strip()[:10000]
                        except Exception:
                            await self._send_response(writer, 400, {"error": "Invalid JSON body."}, req_origin=req_origin)
                            return

                    if not text and not attached_file:
                        await self._send_response(writer, 400, {"error": "Reply text or attachment is required."}, req_origin=req_origin)
                        return

                    if attached_file:
                        if len(attached_file["data"]) > self.MAX_EVIDENCE_BYTES:
                            attached_file["data"] = b""
                            await self._send_response(writer, 413, {"error": "Attachment exceeds the 20 MB per-file limit."}, req_origin=req_origin)
                            return
                        existing_files = case_data.get("files") or []
                        if len(existing_files) >= self.MAX_FILES_PER_CASE:
                            await self._send_response(writer, 429, {"error": f"Maximum attachment limit ({self.MAX_FILES_PER_CASE} files) reached for this case."}, req_origin=req_origin)
                            return
                        saved_ev = await self.bridge.store_evidence(case_code, attached_file["filename"], attached_file["data"], attached_file.get("mime"))
                        attached_file["data"] = b""
                        safe_disp_name = saved_ev.get("original_name") or "attachment"
                        text = f"📁 [{safe_disp_name}]\n{text}" if text else f"📁 [{safe_disp_name}]"

                    sender_disp = f"Investigator {sess['first_name']}" if sess.get("first_name") else "Investigator"
                    new_msg = self.vault.add_message(
                        case_code=case_code,
                        sender_type="admin",
                        sender_name=sender_disp,
                        text=text,
                    )
                    self.vault.mark_case_read(case_code, sess["user_id"], int(new_msg.get("id") or 0))
                    self.vault.record_admin_audit(case_code, "ADMIN_REPLY", sess["actor_label"], f"Msg #{new_msg.get('id')}")
                    await self._send_response(writer, 201, {"success": True, "message": new_msg}, req_origin=req_origin)
                    return

                # GET /admin/cases/<code>/evidence/<ev_id>
                elif method == "GET" and len(parts) == 5 and parts[3] == "evidence":
                    if not parts[4].isdigit():
                        await self._send_response(writer, 400, {"error": "Invalid evidence ID."}, req_origin=req_origin)
                        return
                    ev_id = int(parts[4])
                    ev_item = self.vault.get_evidence_item(case_code, ev_id)
                    if not ev_item:
                        await self._send_response(writer, 404, {"error": "Evidence item not found."}, req_origin=req_origin)
                        return
                    try:
                        ev_bytes, _ = await self._get_or_fetch_evidence_bytes(case_code, ev_item)
                    except EvidenceTooLargeError as exc:
                        await self._send_response(writer, 413, {"error": str(exc), "too_large_for_webapp": True}, req_origin=req_origin)
                        return
                    except FileNotFoundError:
                        await self._send_response(writer, 404, {"error": "Evidence bytes are no longer available."}, req_origin=req_origin)
                        return

                    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(ev_item.get("original_name") or "evidence.bin"))[:120]
                    ext = os.path.splitext(clean_name)[1].lower()
                    is_preview = (query.get("preview") == "1" or headers.get("x-preview") == "1")
                    if is_preview and ext in self.SAFE_PREVIEW_EXTS:
                        resp_mime = self.SAFE_PREVIEW_EXTS[ext]
                        disp = f'inline; filename="{clean_name}"'
                    else:
                        resp_mime = "application/octet-stream"
                        disp = f'attachment; filename="{clean_name}"'

                    extra_headers = [
                        "Content-Security-Policy: default-src 'none'; sandbox; frame-ancestors 'none'",
                        "X-Content-Type-Options: nosniff",
                        "X-Frame-Options: DENY",
                        "Cross-Origin-Opener-Policy: same-origin",
                        "Cross-Origin-Resource-Policy: same-origin",
                        "X-Permitted-Cross-Domain-Policies: none",
                        "Cache-Control: no-store",
                        f"Content-Disposition: {disp}",
                    ]
                    await self._send_bytes_response(writer, 200, "OK", ev_bytes, resp_mime, extra_headers=extra_headers)
                    return

                # POST /admin/cases/<code>/evidence/<ev_id>/ticket
                elif method == "POST" and len(parts) == 6 and parts[3] == "evidence" and parts[5] == "ticket":
                    if not parts[4].isdigit():
                        await self._send_response(writer, 400, {"error": "Invalid evidence ID."}, req_origin=req_origin)
                        return
                    ev_id = int(parts[4])
                    ev_item = self.vault.get_evidence_item(case_code, ev_id)
                    if not ev_item:
                        await self._send_response(writer, 404, {"error": "Evidence item not found."}, req_origin=req_origin)
                        return
                    if int(ev_item.get("file_size") or 0) > self.MAX_EVIDENCE_BYTES and not ev_item.get("stored_filename"):
                        await self._send_response(writer, 413, {"error": "File exceeds 20 MB; use 'Send to Bot DM'.", "too_large_for_webapp": True}, req_origin=req_origin)
                        return
                    self._evict_expired_admin_sessions()
                    ticket = secrets.token_urlsafe(24)
                    self._dl_tickets[ticket] = {
                        "case_code": case_code,
                        "ev_id": ev_id,
                        "admin_id": sess["user_id"],
                        "expires_at": time.time() + 30.0,
                    }
                    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(ev_item.get("original_name") or "evidence.bin"))[:120]
                    await self._send_response(writer, 200, {
                        "success": True,
                        "ticket": ticket,
                        "url_path": f"/api/support/admin/dl/{ticket}",
                        "filename": clean_name,
                        "expires_in": 30,
                    }, req_origin=req_origin)
                    return

                # POST /admin/cases/<code>/evidence/<ev_id>/send-dm
                elif method == "POST" and len(parts) == 6 and parts[3] == "evidence" and parts[5] == "send-dm":
                    if not parts[4].isdigit():
                        await self._send_response(writer, 400, {"error": "Invalid evidence ID."}, req_origin=req_origin)
                        return
                    ev_id = int(parts[4])
                    ev_item = self.vault.get_evidence_item(case_code, ev_id)
                    if not ev_item:
                        await self._send_response(writer, 404, {"error": "Evidence item not found."}, req_origin=req_origin)
                        return
                    try:
                        sent_ok = await self.bridge.send_evidence_to_admin_dm(sess["user_id"], case_code, ev_item)
                    except Exception as exc:
                        await self._send_response(writer, 502, {"error": f"Failed to send evidence to DM: {exc}"}, req_origin=req_origin)
                        return
                    if not sent_ok:
                        await self._send_response(writer, 503, {"error": "Telegram Bot DM delivery is currently unavailable."}, req_origin=req_origin)
                        return
                    self.vault.record_admin_audit(case_code, "EVIDENCE_SENT_DM", sess["actor_label"], f"Evidence #{ev_id}")
                    await self._send_response(writer, 200, {"success": True}, req_origin=req_origin)
                    return

                # DELETE /admin/cases/<code> (or POST /admin/cases/<code>/delete) — SUPER ADMIN ONLY
                elif (method == "DELETE" and len(parts) == 3) or (method == "POST" and len(parts) == 4 and parts[3] == "delete"):
                    if not sess["is_super_admin"]:
                        await self._send_response(writer, 403, {"error": "Permission Denied: Case deletion requires Super Admin privileges."}, req_origin=req_origin)
                        return
                    del_info = self.vault.delete_case(case_code)
                    if not del_info:
                        await self._send_response(writer, 404, {"error": f"Case #{case_code} not found."}, req_origin=req_origin)
                        return
                    for uid_key in [u for u, cc in self.bridge.active_reply_sessions.items() if cc == case_code]:
                        self.bridge.active_reply_sessions.pop(uid_key, None)
                    for mid_key in [m for m, cc in self.bridge.msg_to_case.items() if cc == case_code]:
                        self.bridge.msg_to_case.pop(mid_key, None)
                    stale_cache_keys = [k for k in self._evidence_cache if k.startswith(f"{case_code}:")]
                    for ck in stale_cache_keys:
                        _, cbytes = self._evidence_cache.pop(ck, (0.0, b""))
                        self._evidence_cache_bytes = max(0, self._evidence_cache_bytes - len(cbytes))
                    tg_cleanup: List[Tuple[int, int]] = list(del_info.get("evidence_tg_messages") or [])
                    target_chat = self.bridge.ops_group_chat_id or self.bridge.admin_chat_id
                    if target_chat:
                        for ops_mid in del_info.get("ops_telegram_message_ids") or []:
                            tg_cleanup.append((int(target_chat), int(ops_mid)))
                    if tg_cleanup:
                        asyncio.create_task(self.bridge.delete_telegram_messages(tg_cleanup))
                    await self._send_response(writer, 200, {"success": True, "deleted_case": case_code}, req_origin=req_origin)
                    return

                else:
                    await self._send_response(writer, 404, {"error": f"Endpoint '{clean_path}' not found."}, req_origin=req_origin)
                    return

            else:
                await self._send_response(writer, 404, {"error": f"Endpoint '{clean_path}' not found."}, req_origin=req_origin)

        except Exception as e:
            logger.error("HTTP request error: %s", e)
            try:
                await self._send_response(writer, 500, {"error": "Internal server error"}, req_origin=req_origin)
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        data: Optional[Dict[str, Any]],
        req_origin: str = "",
    ):
        status_texts = {
            200: "OK",
            201: "Created",
            204: "No Content",
            400: "Bad Request",
            401: "Unauthorized",
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
            "Cache-Control: no-cache, no-store, must-revalidate",
            "Pragma: no-cache",
            "Expires: 0",
            "X-Content-Type-Options: nosniff",
            "X-Frame-Options: DENY",
            "Content-Security-Policy: default-src 'none'; frame-ancestors 'none'",
            "Cross-Origin-Opener-Policy: same-origin",
            "Cross-Origin-Resource-Policy: same-origin",
            "X-Permitted-Cross-Domain-Policies: none",
            "Permissions-Policy: camera=(), microphone=(), geolocation=()",
            "Referrer-Policy: no-referrer",
            "Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Case-Key, X-Preview",
        ]
        cors_origin = self._resolve_cors_origin(req_origin)
        if cors_origin:
            header_lines.append(f"Access-Control-Allow-Origin: {cors_origin}")
            header_lines.append("Vary: Origin")
        header_lines.extend([
            f"Content-Length: {len(body_bytes)}",
            "Connection: close",
            "",
            ""
        ])
        headers_raw = "\r\n".join(header_lines).encode('utf-8')
        writer.write(headers_raw + body_bytes)
        await writer.drain()

    async def _send_bytes_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        status_msg: str,
        body_bytes: bytes,
        content_type: str,
        extra_headers: Optional[List[str]] = None,
    ):
        header_lines = [
            f"HTTP/1.1 {status_code} {status_msg}",
            f"Content-Type: {content_type}",
        ]
        if extra_headers:
            header_lines.extend(extra_headers)
        header_lines.extend([
            f"Content-Length: {len(body_bytes)}",
            "Connection: close",
            "",
            "",
        ])
        writer.write("\r\n".join(header_lines).encode("utf-8") + body_bytes)
        await writer.drain()


# =========================================================================
# Unified Support Hub Initializer & Standalone Runner
# =========================================================================

def init_support_hub(
    application: Optional[Application] = None,
    ghost_dir: str = "/var/www/ghost",
    admin_chat_id: int = 0,
    port: int = 8080,
    host: str = "127.0.0.1",
    allowed_user_ids: Optional[Set[int]] = None,
    auth_callback: Optional[Callable[[int], bool]] = None,
    super_admin_callback: Optional[Callable[[int], bool]] = None,
    ops_group_chat_id: Optional[int] = None,
    storage_chat_id: Optional[int] = None,
    webapp_url: Optional[str] = None,
    bot_username: Optional[str] = None,
    webapp_shortname: Optional[str] = None,
) -> SupportApiServer:
    """Initialize the Vault, Bot Bridge, and HTTP Server on the bot's asyncio loop."""
    vault = SupportVault(ghost_dir=ghost_dir)
    bridge = SupportBotBridge(
        application=application,
        vault=vault,
        admin_chat_id=admin_chat_id,
        allowed_user_ids=allowed_user_ids,
        auth_callback=auth_callback,
        super_admin_callback=super_admin_callback,
        ops_group_chat_id=ops_group_chat_id,
        storage_chat_id=storage_chat_id,
        webapp_url=webapp_url,
        bot_username=bot_username,
        webapp_shortname=webapp_shortname,
    )
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
