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
            # Auto-migrate existing DBs for member tracking & Telegram metadata
            for col_sql in [
                "ALTER TABLE cases ADD COLUMN member_email TEXT",
                "ALTER TABLE cases ADD COLUMN member_uuid TEXT",
                "ALTER TABLE cases ADD COLUMN telegram_message_id INTEGER",
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

    def make_case_keyboard(self, case_code: str, status: str, has_files: bool = False, msg_count: int = 0, can_delete: bool = False) -> Any:
        if not HAS_TELEGRAM:
            return None
        # Row 1: Chat & History, and Evidence (if files exist)
        row1 = [
            InlineKeyboardButton(f"💬 Chat & History ({msg_count})", callback_data=f"case_thread:{case_code}")
        ]
        if has_files:
            row1.append(InlineKeyboardButton("📎 Evidence", callback_data=f"case_evidence:{case_code}"))

        # Row 2: Status Menu and (if Super Admin) Delete Case
        row2 = [
            InlineKeyboardButton("⚙️ Change Status", callback_data=f"case_status_menu:{case_code}")
        ]
        if can_delete:
            row2.append(InlineKeyboardButton("🗑️ Delete Case", callback_data=f"case_delete_ask:{case_code}"))
            row3 = [InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list")]
            return InlineKeyboardMarkup([row1, row2, row3])

        row2.append(InlineKeyboardButton("⬅️ Back to Cases", callback_data="menu_cases_list"))
        return InlineKeyboardMarkup([row1, row2])

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
        """Send streamlined alert to the collaborative operations group (Group 1)."""
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
        """Notify collaborative operations group when reporter sends a message on the web portal."""
        target_chat = self.ops_group_chat_id or self.admin_chat_id
        if not self.app or not target_chat:
            logger.info("Standalone/No-admin mode: skipping Telegram reporter reply alert for %s", case_code)
            return

        import html
        text = (
            f"💬 <b>New Reply on #{case_code}</b>\n\n"
            f"<blockquote>{html.escape(message_text)}</blockquote>\n"
            f"<i>Reply to this message or tap below:</i>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 Send Reply", callback_data=f"case_reply:{case_code}"),
                InlineKeyboardButton("📜 View Thread", callback_data=f"case_thread:{case_code}")
            ],
            [
                InlineKeyboardButton("🔍 View Case", callback_data=f"case_view:{case_code}")
            ]
        ])
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

            if action == "case_view":
                msgs = self.vault.get_messages(case_code)
                has_files = bool(case_data.get("files"))
                text = self.format_case_card(case_data)
                kb = self.make_case_keyboard(
                    case_code,
                    case_data.get("status", "SUBMITTED"),
                    has_files=has_files,
                    msg_count=len(msgs),
                    can_delete=is_super,
                )
                try:
                    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        raise

            elif action in ("case_thread", "case_history"):
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
                    for tg_cid, tg_mid in del_info.get("evidence_tg_messages", []):
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
        """List active cases."""
        caller_id = update.effective_user.id if update.effective_user else None
        if not self._is_authorized_user(caller_id):
            if update.message:
                await update.message.reply_text("⛔ Access Denied.")
            return
        cases = self.vault.list_recent_cases(limit=10)
        if not cases:
            await update.message.reply_text("ℹ️ No support cases currently on record.")
            return

        lines = ["📋 <b>Recent Cases</b>\n"]
        buttons = []
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
            buttons.append([InlineKeyboardButton(f"{st_icon} #{cc_raw} - {sub_raw[:22]}", callback_data=f"case_view:{cc_raw}")])
        lines.append("<i>Select a case below:</i>")
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
    MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB hard payload cap
    LARGE_UPLOAD_THRESHOLD = 2 * 1024 * 1024  # 2 MB concurrency gate
    MAX_HEADER_COUNT = 64
    MAX_HEADER_LINE_BYTES = 8192
    MAX_FILES_PER_CASE = 15

    def __init__(self, vault: SupportVault, bridge: SupportBotBridge, host: str = "127.0.0.1", port: int = 8080):
        self.vault = vault
        self.bridge = bridge
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.captcha = CaptchaEngine()
        self._conn_sem = asyncio.Semaphore(32)
        self._upload_sem = asyncio.Semaphore(2)
        # Bounded sliding-window rate-limit buckets: bucket_name -> {key -> [timestamps]}
        self._rate_buckets: Dict[str, Dict[str, List[float]]] = {}
        self._ghost_port, self._ghost_origin, self._ghost_host, self._ghost_proto = self._load_ghost_upstream_config()

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
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Case-Key",
                    "Access-Control-Max-Age: 86400",
                    "X-Content-Type-Options: nosniff",
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
                try:
                    report_obj = json.loads(body.decode("utf-8", errors="ignore") or "{}")
                    violations_log = os.path.join(self.vault.vault_dir, "csp_violations.log")
                    log_entry = {
                        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "ip_hash": ip_hash,
                        "report": report_obj
                    }
                    with open(violations_log, "a", encoding="utf-8") as vf:
                        vf.write(json.dumps(log_entry) + "\n")
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
            "Permissions-Policy: camera=(), microphone=(), geolocation=()",
            "Referrer-Policy: no-referrer",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, X-Case-Key",
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
