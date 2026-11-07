import os
import sys
import json
import sqlite3
import shutil
import zipfile
import subprocess
import datetime
import tempfile
import glob
import re
import logging
from pathlib import Path

try:
    import pwd
except ImportError:
    pwd = None

def is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0

class GhostManager:
    def __init__(self, ghost_dir="/var/www/ghost", backups_dir=None):
        self.ghost_dir = os.path.abspath(ghost_dir)
        self.backups_dir = os.path.abspath(backups_dir) if backups_dir else os.path.join(self.ghost_dir, "backups")
        os.makedirs(self.backups_dir, exist_ok=True)

    def get_config_path(self):
        prod = os.path.join(self.ghost_dir, "config.production.json")
        dev = os.path.join(self.ghost_dir, "config.development.json")
        if os.path.exists(prod):
            return prod
        if os.path.exists(dev):
            return dev
        return None

    def read_config(self):
        cfg_path = self.get_config_path()
        if not cfg_path:
            return {}
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}

    def get_ghost_user(self):
        """Determine non-root user with sudo access to execute Ghost CLI commands."""
        # 1. Prefer regular sudo user like 'ubuntu', never the 'ghost' service account
        for candidate in ["ubuntu", os.environ.get("SUDO_USER"), os.environ.get("USER")]:
            if candidate and candidate not in ["root", "ghost", "daemon"]:
                if pwd:
                    try:
                        pwd.getpwnam(candidate)
                        return candidate
                    except KeyError:
                        continue
                else:
                    return candidate

        # 2. Check directory owner (if not root or ghost)
        if pwd:
            try:
                stat_info = os.stat(self.ghost_dir)
                owner_name = pwd.getpwuid(stat_info.st_uid).pw_name
                if owner_name not in ["root", "ghost", "daemon"]:
                    return owner_name
            except Exception:
                pass

        return "ubuntu"

    def get_systemd_service_name(self):
        """Find the exact systemd service name for this Ghost instance."""
        # 1. Check .ghost-cli.json
        cli_meta_path = os.path.join(self.ghost_dir, ".ghost-cli.json")
        if os.path.exists(cli_meta_path):
            try:
                with open(cli_meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    name = meta.get("name")
                    if name:
                        return f"ghost_{name}"
            except Exception:
                pass

        # 2. Check systemd unit directories for ghost_*.service (Ubuntu 24.04 compatible)
        for unit_dir in ["/etc/systemd/system", "/usr/lib/systemd/system", "/lib/systemd/system"]:
            if os.path.exists(unit_dir):
                services = glob.glob(os.path.join(unit_dir, "ghost_*.service"))
                if services:
                    return os.path.basename(services[0]).replace(".service", "")

        return None

    def control_service(self, action):
        """Controls Ghost using native systemctl if available, or falls back to ghost-cli."""
        svc_name = self.get_systemd_service_name()
        if svc_name:
            if action == "status":
                cmd = ["systemctl", "is-active", svc_name]
                res = subprocess.run(cmd, capture_output=True, text=True)
                is_active = res.returncode == 0
                return {"success": is_active, "stdout": "running" if is_active else "inactive", "stderr": ""}
            else:
                cmd = ["systemctl", action, svc_name]
                if not is_root():
                    cmd = ["sudo"] + cmd
                res = subprocess.run(cmd, capture_output=True, text=True)
                return {"success": res.returncode == 0, "stdout": res.stdout.strip(), "stderr": res.stderr.strip()}

        # Fallback to Ghost CLI
        return self.run_ghost_cli(action)

    def run_ghost_cli(self, command):
        """Run ghost cli as the proper non-root user."""
        ghost_user = self.get_ghost_user()

        if is_root():  # Running as root
            full_cmd = ["sudo", "-u", ghost_user, "bash", "-c", f"cd '{self.ghost_dir}' && ghost {command}"]
        else:
            full_cmd = ["bash", "-c", f"cd '{self.ghost_dir}' && ghost {command}"]

        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=90)
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Command timed out after 90 seconds"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}

    def get_database_info(self):
        cfg = self.read_config()
        db_cfg = cfg.get("database", {})
        client = db_cfg.get("client", "unknown")
        conn = db_cfg.get("connection", {})
        return {
            "client": client,
            "connection": conn,
            "url": cfg.get("url", "http://localhost:2368")
        }

    def get_status(self):
        """Fetch comprehensive status of the Ghost instance."""
        cfg = self.read_config()
        url = cfg.get("url", "N/A")
        db_info = self.get_database_info()
        ghost_user = self.get_ghost_user()

        # Systemd / Ghost status check
        cli_status = self.control_service("status")
        is_running = "running" in cli_status.get("stdout", "").lower()

        # Recent Backups Count
        backups = self.list_backups()
        total_backups = len(backups)
        latest_backup = backups[0]["name"] if backups else "None"

        # Content stats
        content_dir = os.path.join(self.ghost_dir, "content")
        themes_dir = os.path.join(content_dir, "themes")
        themes = []
        if os.path.exists(themes_dir):
            for t in os.listdir(themes_dir):
                if os.path.isdir(os.path.join(themes_dir, t)) or os.path.islink(os.path.join(themes_dir, t)):
                    themes.append(t)

        return {
            "url": url,
            "running": is_running,
            "raw_status": cli_status.get("stdout", ""),
            "db_client": db_info["client"],
            "ghost_user": ghost_user,
            "themes": themes,
            "total_backups": total_backups,
            "latest_backup": latest_backup,
            "ghost_dir": self.ghost_dir
        }

    def create_backup(self, progress_callback=None):
        """
        Creates a complete 1:1 backup archive of Ghost publication.
        Handles both MySQL and SQLite, normalizes POSIX paths, and skips symlinks.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_filename = f"ghost-backup-{timestamp}.zip"
        zip_path = os.path.join(self.backups_dir, zip_filename)
        staging_dir = tempfile.mkdtemp(prefix="ghost_backup_")

        def notify(msg):
            if progress_callback:
                progress_callback(msg)

        try:
            notify("🔍 [1/5] Inspecting Ghost configuration & database...")
            db_info = self.get_database_info()
            content_dir = os.path.join(self.ghost_dir, "content")
            staging_content = os.path.join(staging_dir, "content")
            os.makedirs(staging_content, exist_ok=True)

            # 1. Backup Database
            notify(f"💾 [2/5] Backing up database ({db_info['client']})...")
            staging_data = os.path.join(staging_content, "data")
            os.makedirs(staging_data, exist_ok=True)

            if db_info["client"] == "sqlite3":
                src_db = db_info["connection"].get("filename")
                if not src_db or not os.path.isabs(src_db):
                    src_db = os.path.join(self.ghost_dir, src_db or "content/data/ghost.db")
                if os.path.exists(src_db):
                    shutil.copy2(src_db, os.path.join(staging_data, os.path.basename(src_db)))
            elif db_info["client"] == "mysql":
                conn = db_info["connection"]
                host = conn.get("host", "localhost")
                port = str(conn.get("port", 3306))
                user = conn.get("user", "root")
                password = conn.get("password", "")
                database = conn.get("database", "ghost_production")

                sql_dump_file = os.path.join(staging_data, "mysql_database.sql")
                env = os.environ.copy()
                if password:
                    env["MYSQL_PWD"] = str(password)

                dump_cmd = [
                    "mysqldump",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{user}",
                    "--single-transaction",
                    "--quick",
                    "--routines",
                    "--triggers",
                    database
                ]

                with open(sql_dump_file, "w", encoding="utf-8") as out:
                    proc = subprocess.run(dump_cmd, stdout=out, stderr=subprocess.PIPE, text=True, env=env)
                    if proc.returncode != 0:
                        raise Exception(f"mysqldump failed: {proc.stderr}")

            # 2. Backup Themes (Skip core symlinks like casper/source)
            notify("🎨 [3/5] Archiving custom themes & layouts...")
            src_themes = os.path.join(content_dir, "themes")
            staging_themes = os.path.join(staging_content, "themes")
            os.makedirs(staging_themes, exist_ok=True)
            if os.path.exists(src_themes):
                for t in os.listdir(src_themes):
                    full_theme = os.path.join(src_themes, t)
                    # Skip symlinks to avoid cross-environment breakage
                    if os.path.islink(full_theme):
                        continue
                    if os.path.isdir(full_theme):
                        dest_theme = os.path.join(staging_themes, t)
                        shutil.copytree(full_theme, dest_theme, ignore=shutil.ignore_patterns(".git", "node_modules"))
                    elif os.path.isfile(full_theme):
                        shutil.copy2(full_theme, os.path.join(staging_themes, t))

            # 3. Backup Uploaded Media & Settings
            notify("🖼️ [4/5] Archiving media images & routes...")
            src_images = os.path.join(content_dir, "images")
            if os.path.exists(src_images):
                shutil.copytree(src_images, os.path.join(staging_content, "images"), dirs_exist_ok=True)

            src_settings = os.path.join(content_dir, "settings")
            if os.path.exists(src_settings):
                shutil.copytree(src_settings, os.path.join(staging_content, "settings"), dirs_exist_ok=True)

            # Backup Support Vault (Database & Evidence Artifacts)
            src_vault = os.path.join(self.ghost_dir, "support_vault")
            if os.path.exists(src_vault):
                shutil.copytree(src_vault, os.path.join(staging_dir, "support_vault"), dirs_exist_ok=True)

            # Copy config file
            cfg_path = self.get_config_path()
            if cfg_path and os.path.exists(cfg_path):
                shutil.copy2(cfg_path, os.path.join(staging_dir, os.path.basename(cfg_path)))

            # 4. Create Zip Archive with POSIX forward slashes
            notify("📦 [5/5] Compressing into cross-platform archive...")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(staging_dir):
                    for file in files:
                        abs_file = os.path.join(root, file)
                        rel_path = os.path.relpath(abs_file, staging_dir)
                        # Ensure POSIX forward slashes
                        clean_rel_path = rel_path.replace(os.sep, "/")
                        zf.write(abs_file, clean_rel_path)

            file_size_bytes = os.path.getsize(zip_path)
            file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
            notify(f"✅ Backup complete! Archive size: {file_size_mb} MB")

            return {
                "success": True,
                "file_path": zip_path,
                "file_name": zip_filename,
                "size_mb": file_size_mb,
                "size_bytes": file_size_bytes,
                "timestamp": timestamp
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)

    def restore_backup(self, zip_path, progress_callback=None):
        """
        Safely restores a Ghost backup archive:
        - Gracefully stops Ghost
        - Auto-normalizes Windows backslashes (chr(92))
        - Preserves Ghost core Casper/Source symlinks
        - Restores MySQL or SQLite
        - Enforces correct Linux permissions
        - Restarts Ghost as proper non-root user
        """
        def notify(msg):
            if progress_callback:
                progress_callback(msg)

        if not os.path.exists(zip_path):
            return {"success": False, "error": f"Backup file not found: {zip_path}"}

        staging_dir = tempfile.mkdtemp(prefix="ghost_restore_")

        try:
            # 1. Stop Ghost
            notify("⏸️ [1/6] Gracefully stopping Ghost...")
            self.control_service("stop")

            # 2. Extract Archive with Backslash Normalization & Zip Slip Defense
            notify("📂 [2/6] Extracting archive & normalizing paths...")
            bs = chr(92)
            staging_real = os.path.realpath(staging_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for m in zf.infolist():
                    clean_name = m.filename.replace(bs, "/").lstrip("/")
                    if not clean_name:
                        continue
                    target = os.path.realpath(os.path.join(staging_dir, clean_name))
                    # Prevent Zip Slip directory traversal
                    if not (target.startswith(staging_real + os.sep) or target == staging_real):
                        continue
                    if m.is_dir() or clean_name.endswith("/"):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(m) as src, open(target, "wb") as dst:
                            dst.write(src.read())

            target_content = os.path.join(self.ghost_dir, "content")
            staging_content = os.path.join(staging_dir, "content")
            os.makedirs(target_content, exist_ok=True)

            # 3. Restore Themes (Preserve Casper/Source symlinks)
            notify("🎨 [3/6] Restoring themes (preserving core symlinks)...")
            staging_themes = os.path.join(staging_content, "themes")
            target_themes = os.path.join(target_content, "themes")
            os.makedirs(target_themes, exist_ok=True)

            if os.path.exists(staging_themes):
                for t in os.listdir(staging_themes):
                    src_theme = os.path.join(staging_themes, t)
                    dest_theme = os.path.join(target_themes, t)
                    # Don't overwrite if destination is an active core symlink
                    if os.path.islink(dest_theme):
                        continue

                    if os.path.isdir(src_theme):
                        if os.path.exists(dest_theme):
                            if os.path.isdir(dest_theme):
                                shutil.rmtree(dest_theme, ignore_errors=True)
                            else:
                                os.remove(dest_theme)
                        shutil.copytree(src_theme, dest_theme)
                    elif os.path.isfile(src_theme):
                        if os.path.exists(dest_theme) and os.path.isdir(dest_theme):
                            shutil.rmtree(dest_theme, ignore_errors=True)
                        shutil.copy2(src_theme, dest_theme)

            # 4. Restore Media & Routes
            notify("🖼️ [4/6] Restoring uploaded images & route settings...")
            staging_images = os.path.join(staging_content, "images")
            if os.path.exists(staging_images):
                target_images = os.path.join(target_content, "images")
                os.makedirs(target_images, exist_ok=True)
                # Copy images merging with existing
                for root, dirs, files in os.walk(staging_images):
                    rel = os.path.relpath(root, staging_images)
                    dest_dir = os.path.join(target_images, rel)
                    os.makedirs(dest_dir, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))

            staging_settings = os.path.join(staging_content, "settings")
            if os.path.exists(staging_settings):
                shutil.copytree(staging_settings, os.path.join(target_content, "settings"), dirs_exist_ok=True)

            # Restore Support Vault (Database & Evidence Artifacts)
            staging_vault = os.path.join(staging_dir, "support_vault")
            if os.path.exists(staging_vault):
                target_vault = os.path.join(self.ghost_dir, "support_vault")
                os.makedirs(target_vault, exist_ok=True)
                for root, dirs, files in os.walk(staging_vault):
                    rel = os.path.relpath(root, staging_vault)
                    dest_dir = os.path.join(target_vault, rel)
                    os.makedirs(dest_dir, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))

            # 5. Restore Database
            notify("💾 [5/6] Restoring database content...")
            db_info = self.get_database_info()
            staging_data = os.path.join(staging_content, "data")

            if db_info["client"] == "mysql":
                # Check for mysql_database.sql or ghost-local.db SQLite fallback
                mysql_sql = os.path.join(staging_data, "mysql_database.sql")
                sqlite_file = None
                if os.path.exists(staging_data):
                    for f in os.listdir(staging_data):
                        if f.endswith(".db"):
                            sqlite_file = os.path.join(staging_data, f)
                            break

                conn = db_info["connection"]
                host = conn.get("host", "localhost")
                port = str(conn.get("port", 3306))
                user = conn.get("user", "root")
                password = conn.get("password", "")
                database = conn.get("database", "ghost_production")

                if os.path.exists(mysql_sql):
                    # Direct MySQL dump import with secure password handling via env
                    cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}", database]
                    env = os.environ.copy()
                    if password:
                        env["MYSQL_PWD"] = str(password)
                    with open(mysql_sql, "r", encoding="utf-8") as sf:
                        proc = subprocess.run(cmd, stdin=sf, capture_output=True, text=True, env=env)
                        if proc.returncode != 0:
                            notify(f"⚠️ MySQL import notice: {proc.stderr}")
                elif sqlite_file and os.path.exists(sqlite_file):
                    # Convert SQLite tables to MySQL REPLACE INTO statements
                    self._import_sqlite_to_mysql(sqlite_file, host, port, user, password, database)

            elif db_info["client"] == "sqlite3":
                target_db = db_info["connection"].get("filename")
                if not target_db or not os.path.isabs(target_db):
                    target_db = os.path.join(self.ghost_dir, target_db or "content/data/ghost.db")
                os.makedirs(os.path.dirname(target_db), exist_ok=True)

                if os.path.exists(staging_data):
                    for f in os.listdir(staging_data):
                        if f.endswith(".db"):
                            shutil.copy2(os.path.join(staging_data, f), target_db)
                            break

            # 6. Fix Permissions & Restart Ghost
            notify("🔑 [6/6] Fixing Linux ownership & starting Ghost...")
            cli_user = self.get_ghost_user()
            if is_root():  # If root, fix ownership
                try:
                    # Content folder owned by ghost runtime user
                    subprocess.run(["chown", "-R", "ghost:ghost", target_content], check=False)
                    subprocess.run(["find", target_content, "-type", "d", "-exec", "chmod", "775", "{}", "+"], check=False)
                    subprocess.run(["find", target_content, "-type", "f", "-exec", "chmod", "664", "{}", "+"], check=False)
                    # Base ghost directory owned by CLI user (ubuntu)
                    subprocess.run(["chown", f"{cli_user}:{cli_user}", self.ghost_dir], check=False)
                except Exception as e:
                    notify(f"⚠️ Permission setting notice: {e}")

            # Start Ghost
            start_res = self.control_service("start")
            if not start_res["success"]:
                start_res = self.control_service("restart")

            # Auto-heal systemd if missing or corrupted
            combined_err = (start_res.get("stderr", "") + " " + start_res.get("stdout", "")).lower()
            if not start_res["success"] and ("systemd" in combined_err or "corrupted" in combined_err):
                notify("🔧 Re-linking Ghost systemd service...")
                self.run_ghost_cli("setup linux-user systemd --no-prompt")
                start_res = self.run_ghost_cli("start")

            notify("🎉 [SUCCESS] Ghost publication restored & restarted!")
            return {"success": True, "details": start_res}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _import_sqlite_to_mysql(self, sqlite_path, host, port, user, password, database):
        """Pipes SQLite rows into MySQL with foreign key check bypass."""
        def esc(v):
            if v is None: return "NULL"
            if isinstance(v, (int, float)): return str(v)
            s = str(v).replace("\\", "\\\\").replace("'", "''").replace("\0", "")
            return f"'{s}'"

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        sql_lines = ["SET FOREIGN_KEY_CHECKS=0;"]
        tables = ["posts", "posts_authors", "tags", "posts_tags", "settings", "custom_theme_settings"]
        for t in tables:
            try:
                rows = c.execute(f"SELECT * FROM `{t}`").fetchall()
                if not rows: continue
                cols = list(rows[0].keys())
                col_names = ", ".join([f"`{col}`" for col in cols])
                for r in rows:
                    vals = ", ".join([esc(r[col]) for col in cols])
                    sql_lines.append(f"REPLACE INTO `{t}` ({col_names}) VALUES ({vals});")
            except Exception:
                continue

        sql_lines.append("SET FOREIGN_KEY_CHECKS=1;")
        conn.close()

        sql_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8")
        sql_tmp.write("\n".join(sql_lines))
        sql_tmp.close()

        cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}", database]
        env = os.environ.copy()
        if password:
            env["MYSQL_PWD"] = str(password)

        with open(sql_tmp.name, "r", encoding="utf-8") as sf:
            subprocess.run(cmd, stdin=sf, capture_output=True, text=True, env=env)
        os.remove(sql_tmp.name)

    def list_backups(self):
        """Lists available backup archives sorted newest to oldest."""
        files = []
        if os.path.exists(self.backups_dir):
            files.extend(glob.glob(os.path.join(self.backups_dir, "*.zip")))

        # Also discover any .zip archives in /tmp or /home/*
        for extra_dir in ["/tmp", "/home/ubuntu"]:
            if os.path.exists(extra_dir):
                files.extend(glob.glob(os.path.join(extra_dir, "*.zip")))

        # Deduplicate
        files = list(set(files))
        results = []
        for f in files:
            try:
                stat = os.stat(f)
                size_mb = round(stat.st_size / (1024 * 1024), 2)
                dt = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                results.append({
                    "path": f,
                    "name": os.path.basename(f),
                    "size_mb": size_mb,
                    "size_bytes": stat.st_size,
                    "date": dt,
                    "mtime": stat.st_mtime
                })
            except Exception:
                continue
        results.sort(key=lambda x: x["mtime"], reverse=True)
        return results

    # =========================================================================
    # GitHub Private Backup & Restore System (Unzipped, Clean Content Archive)
    # =========================================================================

    def _build_authenticated_git_url(self, repo_url: str, token: str = None) -> str:
        """
        Formats a clean, authenticated HTTPS URL for GitHub or other Git providers.
        Supports https://github.com/owner/repo.git, owner/repo, git@github.com:owner/repo.git.
        """
        if not repo_url:
            return ""
        clean = repo_url.strip()

        # Handle SSH format git@github.com:owner/repo.git
        if clean.startswith("git@"):
            clean = re.sub(r"^git@([^:]+):", r"https://\1/", clean)

        # Handle plain owner/repo format
        if not clean.startswith("http://") and not clean.startswith("https://"):
            clean = f"https://github.com/{clean}"

        # Ensure .git suffix
        if not clean.endswith(".git"):
            clean = f"{clean}.git"

        if token:
            token = token.strip()
            # Strip any existing credentials in URL
            clean_host_path = re.sub(r"^https?://[^@]+@", "", clean)
            if not clean_host_path.startswith("http"):
                clean_host_path = f"https://{clean_host_path}"

            # Format for GitHub Personal Access Tokens (x-access-token)
            clean = clean_host_path.replace("https://", f"https://x-access-token:{token}@")

        return clean

    def _sanitize_git_output(self, text: str, token: str = None) -> str:
        """Strips credentials, personal access tokens, and sensitive URLs from output."""
        if not text:
            return ""
        sanitized = str(text)
        if token and token in sanitized:
            sanitized = sanitized.replace(token, "[REDACTED_TOKEN]")
        # Strip https://...:token@ or https://token@ patterns
        sanitized = re.sub(r"https?://[^@\s]+@", "https://***@", sanitized)
        return sanitized

    def _run_git(self, cmd: list, cwd: str = None, token: str = None, timeout: int = 180) -> dict:
        """Runs a Git command safely with strict timeouts and sanitized output."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = ""
        env["LC_ALL"] = "C"

        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            return {
                "success": res.returncode == 0,
                "returncode": res.returncode,
                "stdout": self._sanitize_git_output(res.stdout.strip(), token),
                "stderr": self._sanitize_git_output(res.stderr.strip(), token)
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Git command timed out after {timeout} seconds."
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": self._sanitize_git_output(str(e), token)
            }

    def test_github_connection(self, repo_url: str = None, token: str = None) -> tuple:
        """Validates connection and repository permissions against GitHub."""
        repo_url = repo_url or os.getenv("GITHUB_BACKUP_REPO")
        token = token or os.getenv("GITHUB_TOKEN")

        if not shutil.which("git"):
            return False, "Git CLI is not installed on this server. Run 'sudo apt install -y git'."
        if not repo_url:
            return False, "GITHUB_BACKUP_REPO is not configured."
        if not token:
            return False, "GITHUB_TOKEN is not configured."

        auth_url = self._build_authenticated_git_url(repo_url, token)
        res = self._run_git(["git", "ls-remote", "--heads", auth_url], timeout=25, token=token)
        if res["success"]:
            return True, "Connection verified successfully."

        err = res["stderr"] or res["stdout"] or "Authentication failed or repository not found."
        return False, err

    def get_github_status(self) -> dict:
        """Returns the current configuration and sync status of the GitHub backup repository."""
        repo = os.getenv("GITHUB_BACKUP_REPO", "")
        token = os.getenv("GITHUB_TOKEN", "")
        branch = os.getenv("GITHUB_BRANCH", "main")

        is_configured = bool(repo and token)

        clean_repo = repo
        if "@" in clean_repo:
            clean_repo = re.sub(r"https?://[^@]+@", "https://", clean_repo)

        masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ("Configured" if token else "Not Set")

        sync_dir = os.path.join(self.backups_dir, "github_sync")
        last_commit = None
        if os.path.exists(os.path.join(sync_dir, ".git")):
            res = self._run_git(["git", "log", "-1", "--format=%h - %s (%cr)"], cwd=sync_dir, token=token)
            if res["success"] and res["stdout"]:
                last_commit = res["stdout"]

        return {
            "configured": is_configured,
            "repo": clean_repo or "Not Set",
            "token_status": masked_token,
            "branch": branch,
            "last_commit": last_commit or "No sync recorded yet",
            "sync_dir": sync_dir
        }

    def _dump_posts_and_pages_to_json(self, dest_dir: str) -> tuple:
        """
        Dumps Ghost posts and pages into individual, unzipped human-readable JSON files.
        Extracts tags, authors, status, HTML, lexical/mobiledoc, and metadata.
        Returns (post_count, page_count).
        """
        posts_dir = os.path.join(dest_dir, "posts")
        pages_dir = os.path.join(dest_dir, "pages")
        settings_dir = os.path.join(dest_dir, "settings")
        os.makedirs(posts_dir, exist_ok=True)
        os.makedirs(pages_dir, exist_ok=True)
        os.makedirs(settings_dir, exist_ok=True)

        db_info = self.get_database_info()
        client = db_info.get("client")

        post_count = 0
        page_count = 0

        # Case A: SQLite
        if client == "sqlite3":
            src_db = db_info["connection"].get("filename")
            if not src_db or not os.path.isabs(src_db):
                src_db = os.path.join(self.ghost_dir, src_db or "content/data/ghost.db")
            if not os.path.exists(src_db):
                return (0, 0)

            conn = sqlite3.connect(src_db)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            # Map tags
            post_tags = {}
            try:
                for r in c.execute("SELECT pt.post_id, t.name FROM tags t JOIN posts_tags pt ON t.id = pt.tag_id ORDER BY pt.sort_order ASC").fetchall():
                    post_tags.setdefault(r["post_id"], []).append(r["name"])
            except Exception:
                pass

            # Map authors
            post_authors = {}
            try:
                for r in c.execute("SELECT pa.post_id, u.name FROM users u JOIN posts_authors pa ON u.id = pa.author_id ORDER BY pa.sort_order ASC").fetchall():
                    post_authors.setdefault(r["post_id"], []).append(r["name"])
            except Exception:
                pass

            # Extract posts & pages
            try:
                for row in c.execute("SELECT * FROM posts").fetchall():
                    data = dict(row)
                    pid = data.get("id")
                    ptype = str(data.get("type") or "post").lower()
                    slug = data.get("slug") or f"item_{pid}"
                    safe_slug = re.sub(r"[^\w\-_\.]", "_", slug).strip("._") or f"item_{pid}"

                    data["tags"] = post_tags.get(pid, [])
                    data["authors"] = post_authors.get(pid, [])

                    target_dir = pages_dir if ptype == "page" else posts_dir
                    target_file = os.path.join(target_dir, f"{safe_slug}.json")
                    with open(target_file, "w", encoding="utf-8") as pf:
                        json.dump(data, pf, indent=2, ensure_ascii=False, default=str)

                    if ptype == "page":
                        page_count += 1
                    else:
                        post_count += 1
            except Exception:
                pass

            # Extract settings
            try:
                settings_rows = c.execute("SELECT `key`, `value` FROM settings").fetchall()
                settings_dict = {r["key"]: r["value"] for r in settings_rows}
                with open(os.path.join(settings_dir, "settings.json"), "w", encoding="utf-8") as sf:
                    json.dump(settings_dict, sf, indent=2, ensure_ascii=False)
            except Exception:
                pass

            conn.close()

        # Case B: MySQL
        elif client == "mysql":
            conn = db_info["connection"]
            host = conn.get("host", "localhost")
            port = str(conn.get("port", 3306))
            user = conn.get("user", "root")
            password = conn.get("password", "")
            database = conn.get("database", "ghost_production")

            def run_mysql_query(sql):
                cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}", "-D", database, "-B", "-e", sql]
                env = os.environ.copy()
                if password:
                    env["MYSQL_PWD"] = str(password)
                res = subprocess.run(cmd, capture_output=True, text=True, env=env)
                if res.returncode != 0:
                    return []
                lines = res.stdout.split("\n")
                if not lines or not lines[0]:
                    return []
                headers = lines[0].split("\t")
                results = []
                for line in lines[1:]:
                    if not line:
                        continue
                    vals = line.split("\t")
                    row = {}
                    for i, h in enumerate(headers):
                        val = vals[i] if i < len(vals) else ""
                        if val == "NULL":
                            val = None
                        else:
                            val = val.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\").replace("\\0", "\0")
                        row[h] = val
                    results.append(row)
                return results

            # Map tags
            post_tags = {}
            try:
                for r in run_mysql_query("SELECT pt.post_id, t.name FROM tags t JOIN posts_tags pt ON t.id = pt.tag_id ORDER BY pt.sort_order ASC"):
                    post_tags.setdefault(r["post_id"], []).append(r["name"])
            except Exception:
                pass

            # Map authors
            post_authors = {}
            try:
                for r in run_mysql_query("SELECT pa.post_id, u.name FROM users u JOIN posts_authors pa ON u.id = pa.author_id ORDER BY pa.sort_order ASC"):
                    post_authors.setdefault(r["post_id"], []).append(r["name"])
            except Exception:
                pass

            # Extract posts & pages
            try:
                for data in run_mysql_query("SELECT * FROM posts"):
                    pid = data.get("id")
                    ptype = str(data.get("type") or "post").lower()
                    slug = data.get("slug") or f"item_{pid}"
                    safe_slug = re.sub(r"[^\w\-_\.]", "_", slug).strip("._") or f"item_{pid}"

                    data["tags"] = post_tags.get(pid, [])
                    data["authors"] = post_authors.get(pid, [])

                    target_dir = pages_dir if ptype == "page" else posts_dir
                    target_file = os.path.join(target_dir, f"{safe_slug}.json")
                    with open(target_file, "w", encoding="utf-8") as pf:
                        json.dump(data, pf, indent=2, ensure_ascii=False, default=str)

                    if ptype == "page":
                        page_count += 1
                    else:
                        post_count += 1
            except Exception:
                pass

            # Extract settings
            try:
                settings_rows = run_mysql_query("SELECT `key`, `value` FROM settings")
                settings_dict = {r["key"]: r["value"] for r in settings_rows}
                with open(os.path.join(settings_dir, "settings.json"), "w", encoding="utf-8") as sf:
                    json.dump(settings_dict, sf, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return (post_count, page_count)

    def backup_to_github(self, repo_url: str = None, token: str = None, branch: str = None, progress_callback = None) -> dict:
        """
        Backs up Ghost publication into a private GitHub repository in an unzipped,
        human-readable layout (posts/*.json, pages/*.json, images/, database/, settings/, themes/).
        STRICT PRIVACY REQUIREMENT: Explicitly excludes support vault and all evidence files.
        """
        def notify(msg):
            if progress_callback:
                progress_callback(msg)

        if not shutil.which("git"):
            return {"success": False, "error": "Git is not installed on this server. Run 'sudo apt install -y git'."}

        repo_url = repo_url or os.getenv("GITHUB_BACKUP_REPO")
        token = token or os.getenv("GITHUB_TOKEN")
        branch = branch or os.getenv("GITHUB_BRANCH", "main")

        if not repo_url or not token:
            return {
                "success": False,
                "error": "GitHub backup repository or token is not configured. Use /github_setup <repo_url> <token>."
            }

        auth_url = self._build_authenticated_git_url(repo_url, token)
        sync_dir = os.path.join(self.backups_dir, "github_sync")
        os.makedirs(self.backups_dir, exist_ok=True)

        try:
            # 1. Sync / Clone Git Repository
            notify("🔍 [1/6] Connecting to private GitHub repository...")
            git_dir = os.path.join(sync_dir, ".git")

            if os.path.exists(git_dir):
                self._run_git(["git", "remote", "set-url", "origin", auth_url], cwd=sync_dir, token=token)
                self._run_git(["git", "fetch", "origin", branch], cwd=sync_dir, token=token)
                self._run_git(["git", "checkout", "-B", branch], cwd=sync_dir, token=token)
                self._run_git(["git", "pull", "origin", branch], cwd=sync_dir, token=token)
            else:
                if os.path.exists(sync_dir):
                    shutil.rmtree(sync_dir, ignore_errors=True)
                os.makedirs(sync_dir, exist_ok=True)

                clone_res = self._run_git(["git", "clone", "--branch", branch, auth_url, sync_dir], token=token)
                if not clone_res["success"]:
                    clone_all = self._run_git(["git", "clone", auth_url, sync_dir], token=token)
                    if not clone_all["success"]:
                        self._run_git(["git", "init", sync_dir], token=token)
                        self._run_git(["git", "remote", "add", "origin", auth_url], cwd=sync_dir, token=token)
                # Ensure we are on the target branch
                self._run_git(["git", "checkout", "-B", branch], cwd=sync_dir, token=token)

            # 2. Clean previous working tree content while preserving .git
            for item in os.listdir(sync_dir):
                if item == ".git":
                    continue
                item_path = os.path.join(sync_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    try:
                        os.remove(item_path)
                    except Exception:
                        pass

            # 3. Write .gitignore (Strict privacy exclusions)
            gitignore_path = os.path.join(sync_dir, ".gitignore")
            with open(gitignore_path, "w", encoding="utf-8") as gf:
                gf.write(
                    "# Privacy & Security Exclusions\n"
                    "# Strictly prevent support cases, evidence, or credentials from entering git\n"
                    "support_vault/\n"
                    "*support_vault*\n"
                    "evidence/\n"
                    "*evidence*\n"
                    "*.log\n"
                    "*.tmp\n"
                    ".env*\n"
                    "config.*.json\n"
                )

            # 4. Write natural README.md
            readme_path = os.path.join(sync_dir, "README.md")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(readme_path, "w", encoding="utf-8") as rf:
                rf.write(
                    f"# Publication Content Archive\n\n"
                    f"Automated unzipped backup of publication posts, pages, images, and relational database.\n\n"
                    f"- **Last Updated:** {timestamp}\n"
                    f"- **Sync Branch:** `{branch}`\n"
                )

            # 5. Archive Database
            notify("💾 [2/6] Exporting database snapshot...")
            db_dir = os.path.join(sync_dir, "database")
            os.makedirs(db_dir, exist_ok=True)
            db_info = self.get_database_info()

            if db_info["client"] == "sqlite3":
                src_db = db_info["connection"].get("filename")
                if not src_db or not os.path.isabs(src_db):
                    src_db = os.path.join(self.ghost_dir, src_db or "content/data/ghost.db")
                if os.path.exists(src_db):
                    shutil.copy2(src_db, os.path.join(db_dir, "ghost.db"))
            elif db_info["client"] == "mysql":
                conn = db_info["connection"]
                host = conn.get("host", "localhost")
                port = str(conn.get("port", 3306))
                user = conn.get("user", "root")
                password = conn.get("password", "")
                database = conn.get("database", "ghost_production")

                sql_dump_file = os.path.join(db_dir, "ghost_database.sql")
                env = os.environ.copy()
                if password:
                    env["MYSQL_PWD"] = str(password)

                dump_cmd = [
                    "mysqldump",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{user}",
                    "--single-transaction",
                    "--quick",
                    "--routines",
                    "--triggers",
                    database
                ]

                with open(sql_dump_file, "w", encoding="utf-8") as out:
                    proc = subprocess.run(dump_cmd, stdout=out, stderr=subprocess.PIPE, text=True, env=env)
                    if proc.returncode != 0:
                        raise Exception(f"mysqldump failed: {proc.stderr}")

            # 6. Export Posts & Pages into individual JSON files
            notify("📝 [3/6] Exporting readable posts and pages...")
            num_posts, num_pages = self._dump_posts_and_pages_to_json(sync_dir)

            # 7. Sync Media Images & Themes
            notify("🖼️ [4/6] Syncing media images & themes...")
            content_dir = os.path.join(self.ghost_dir, "content")

            # Images
            src_images = os.path.join(content_dir, "images")
            dest_images = os.path.join(sync_dir, "images")
            if os.path.exists(src_images):
                os.makedirs(dest_images, exist_ok=True)
                for root, dirs, files in os.walk(src_images):
                    # Strictly prune any evidence or support directories
                    dirs[:] = [d for d in dirs if "evidence" not in d.lower() and "support" not in d.lower()]
                    rel = os.path.relpath(root, src_images)
                    target_sub = os.path.join(dest_images, rel)
                    os.makedirs(target_sub, exist_ok=True)
                    for f in files:
                        if "evidence" not in f.lower():
                            shutil.copy2(os.path.join(root, f), os.path.join(target_sub, f))

            # Settings routes.yaml
            src_routes = os.path.join(content_dir, "settings", "routes.yaml")
            if os.path.exists(src_routes):
                settings_sync = os.path.join(sync_dir, "settings")
                os.makedirs(settings_sync, exist_ok=True)
                shutil.copy2(src_routes, os.path.join(settings_sync, "routes.yaml"))

            # Custom Themes (Skipping symlinks)
            src_themes = os.path.join(content_dir, "themes")
            dest_themes = os.path.join(sync_dir, "themes")
            if os.path.exists(src_themes):
                os.makedirs(dest_themes, exist_ok=True)
                for t in os.listdir(src_themes):
                    full_theme = os.path.join(src_themes, t)
                    if os.path.islink(full_theme):
                        continue
                    if os.path.isdir(full_theme):
                        shutil.copytree(full_theme, os.path.join(dest_themes, t), dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "node_modules"))

            # 8. Strict Privacy Audit
            notify("🔒 [5/6] Verifying privacy & evidence exclusions...")
            for root, dirs, files in os.walk(sync_dir):
                if ".git" in root:
                    continue
                for d in list(dirs):
                    if "evidence" in d.lower() or "support_vault" in d.lower():
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        dirs.remove(d)
                for f in files:
                    if "evidence" in f.lower() or f.startswith(".env"):
                        try:
                            os.remove(os.path.join(root, f))
                        except Exception:
                            pass

            # 9. Commit & Push
            notify("🚀 [6/6] Committing & pushing to private repository...")
            self._run_git(["git", "add", "-A"], cwd=sync_dir, token=token)
            status_res = self._run_git(["git", "status", "--porcelain"], cwd=sync_dir, token=token)

            if not status_res["stdout"]:
                notify("✅ Publication is already up-to-date on GitHub.")
                return {
                    "success": True,
                    "unchanged": True,
                    "message": "Repository is already up to date with latest content.",
                    "posts": num_posts,
                    "pages": num_pages,
                    "branch": branch
                }

            commit_msg = f"Archive sync: {timestamp} ({num_posts} posts, {num_pages} pages)"
            self._run_git([
                "git",
                "-c", "user.name=Ghost Backup Bot",
                "-c", "user.email=backup@ghost.local",
                "commit", "-m", commit_msg
            ], cwd=sync_dir, token=token)

            self._run_git(["git", "branch", "-M", branch], cwd=sync_dir, token=token)

            push_res = self._run_git(["git", "push", "-u", "origin", branch], cwd=sync_dir, timeout=300, token=token)
            if not push_res["success"]:
                return {
                    "success": False,
                    "error": f"Push to GitHub failed: {push_res['stderr'] or push_res['stdout']}"
                }

            rev_res = self._run_git(["git", "rev-parse", "--short", "HEAD"], cwd=sync_dir, token=token)
            commit_hash = rev_res["stdout"] if rev_res["success"] else "head"

            notify(f"🎉 Backup successfully synced to GitHub! (Commit {commit_hash})")
            return {
                "success": True,
                "commit": commit_hash,
                "posts": num_posts,
                "pages": num_pages,
                "branch": branch,
                "timestamp": timestamp,
                "repo": re.sub(r"https?://[^@]+@", "https://", repo_url)
            }

        except Exception as e:
            return {"success": False, "error": self._sanitize_git_output(str(e), token)}

    def restore_from_github(self, repo_url: str = None, token: str = None, branch: str = None, progress_callback = None) -> dict:
        """
        Restores Ghost publication from the private GitHub repository.
        Pulls latest commits, gracefully stops Ghost, restores database, images, routes,
        and custom themes, fixes permissions, and restarts Ghost.
        """
        def notify(msg):
            if progress_callback:
                progress_callback(msg)

        if not shutil.which("git"):
            return {"success": False, "error": "Git is not installed on this server. Run 'sudo apt install -y git'."}

        repo_url = repo_url or os.getenv("GITHUB_BACKUP_REPO")
        token = token or os.getenv("GITHUB_TOKEN")
        branch = branch or os.getenv("GITHUB_BRANCH", "main")

        if not repo_url or not token:
            return {
                "success": False,
                "error": "GitHub backup repository or token is not configured. Use /github_setup <repo_url> <token>."
            }

        auth_url = self._build_authenticated_git_url(repo_url, token)
        sync_dir = os.path.join(self.backups_dir, "github_sync")
        os.makedirs(self.backups_dir, exist_ok=True)

        try:
            # 1. Fetch Latest Commits
            notify("🔍 [1/6] Fetching latest publication content from GitHub...")
            git_dir = os.path.join(sync_dir, ".git")

            if os.path.exists(git_dir):
                self._run_git(["git", "remote", "set-url", "origin", auth_url], cwd=sync_dir, token=token)
                self._run_git(["git", "fetch", "origin", branch], cwd=sync_dir, token=token)
                self._run_git(["git", "checkout", branch], cwd=sync_dir, token=token)
                self._run_git(["git", "reset", "--hard", f"origin/{branch}"], cwd=sync_dir, token=token)
                self._run_git(["git", "clean", "-fd"], cwd=sync_dir, token=token)
            else:
                if os.path.exists(sync_dir):
                    shutil.rmtree(sync_dir, ignore_errors=True)
                os.makedirs(sync_dir, exist_ok=True)
                clone_res = self._run_git(["git", "clone", "--branch", branch, auth_url, sync_dir], token=token)
                if not clone_res["success"]:
                    return {"success": False, "error": f"Failed to clone repository: {clone_res['stderr'] or clone_res['stdout']}"}

            rev_res = self._run_git(["git", "rev-parse", "--short", "HEAD"], cwd=sync_dir, token=token)
            commit_hash = rev_res["stdout"] if rev_res["success"] else "head"

            # 2. Gracefully Stop Ghost
            notify("⏸️ [2/6] Gracefully stopping Ghost...")
            self.control_service("stop")

            # 3. Restore Database
            notify("💾 [3/6] Restoring database contents...")
            db_info = self.get_database_info()
            sync_db_dir = os.path.join(sync_dir, "database")

            if db_info["client"] == "mysql":
                sql_file = os.path.join(sync_db_dir, "ghost_database.sql")
                sqlite_file = os.path.join(sync_db_dir, "ghost.db")

                conn = db_info["connection"]
                host = conn.get("host", "localhost")
                port = str(conn.get("port", 3306))
                user = conn.get("user", "root")
                password = conn.get("password", "")
                database = conn.get("database", "ghost_production")

                if os.path.exists(sql_file):
                    cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}", database]
                    env = os.environ.copy()
                    if password:
                        env["MYSQL_PWD"] = str(password)
                    with open(sql_file, "r", encoding="utf-8") as sf:
                        proc = subprocess.run(cmd, stdin=sf, capture_output=True, text=True, env=env)
                        if proc.returncode != 0:
                            notify(f"⚠️ MySQL import notice: {proc.stderr}")
                elif os.path.exists(sqlite_file):
                    self._import_sqlite_to_mysql(sqlite_file, host, port, user, password, database)

            elif db_info["client"] == "sqlite3":
                sqlite_file = os.path.join(sync_db_dir, "ghost.db")
                target_db = db_info["connection"].get("filename")
                if not target_db or not os.path.isabs(target_db):
                    target_db = os.path.join(self.ghost_dir, target_db or "content/data/ghost.db")
                os.makedirs(os.path.dirname(target_db), exist_ok=True)
                if os.path.exists(sqlite_file):
                    shutil.copy2(sqlite_file, target_db)

            # 4. Restore Media Images
            notify("🖼️ [4/6] Restoring uploaded media images...")
            target_content = os.path.join(self.ghost_dir, "content")
            sync_images = os.path.join(sync_dir, "images")
            target_images = os.path.join(target_content, "images")

            if os.path.exists(sync_images):
                os.makedirs(target_images, exist_ok=True)
                for root, dirs, files in os.walk(sync_images):
                    rel = os.path.relpath(root, sync_images)
                    dest_dir = os.path.join(target_images, rel)
                    os.makedirs(dest_dir, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))

            # 5. Restore Settings routes.yaml
            sync_routes = os.path.join(sync_dir, "settings", "routes.yaml")
            if os.path.exists(sync_routes):
                target_settings = os.path.join(target_content, "settings")
                os.makedirs(target_settings, exist_ok=True)
                shutil.copy2(sync_routes, os.path.join(target_settings, "routes.yaml"))

            # 6. Restore Custom Themes (Preserving core symlinks)
            notify("🎨 [5/6] Restoring themes (preserving core symlinks)...")
            sync_themes = os.path.join(sync_dir, "themes")
            target_themes = os.path.join(target_content, "themes")
            os.makedirs(target_themes, exist_ok=True)

            if os.path.exists(sync_themes):
                for t in os.listdir(sync_themes):
                    src_theme = os.path.join(sync_themes, t)
                    dest_theme = os.path.join(target_themes, t)
                    if os.path.islink(dest_theme):
                        continue
                    if os.path.isdir(src_theme):
                        if os.path.exists(dest_theme):
                            if os.path.isdir(dest_theme):
                                shutil.rmtree(dest_theme, ignore_errors=True)
                            else:
                                os.remove(dest_theme)
                        shutil.copytree(src_theme, dest_theme)
                    elif os.path.isfile(src_theme):
                        shutil.copy2(src_theme, dest_theme)

            # 7. Fix Linux Ownership & Restart Ghost
            notify("🔑 [6/6] Securing Linux ownership & restarting Ghost...")
            cli_user = self.get_ghost_user()
            if is_root():
                try:
                    subprocess.run(["chown", "-R", "ghost:ghost", target_content], check=False)
                    subprocess.run(["find", target_content, "-type", "d", "-exec", "chmod", "775", "{}", "+"], check=False)
                    subprocess.run(["find", target_content, "-type", "f", "-exec", "chmod", "664", "{}", "+"], check=False)
                    subprocess.run(["chown", f"{cli_user}:{cli_user}", self.ghost_dir], check=False)
                except Exception as e:
                    notify(f"⚠️ Permission setting notice: {e}")

            # Restart Ghost
            start_res = self.control_service("start")
            if not start_res["success"]:
                start_res = self.control_service("restart")

            combined_err = (start_res.get("stderr", "") + " " + start_res.get("stdout", "")).lower()
            if not start_res["success"] and ("systemd" in combined_err or "corrupted" in combined_err):
                notify("🔧 Re-linking Ghost systemd service...")
                self.run_ghost_cli("setup linux-user systemd --no-prompt")
                start_res = self.run_ghost_cli("start")

            notify(f"🎉 [SUCCESS] Ghost restored from GitHub (commit {commit_hash})!")
            return {
                "success": True,
                "commit": commit_hash,
                "branch": branch,
                "details": start_res
            }

        except Exception as e:
            return {"success": False, "error": self._sanitize_git_output(str(e), token)}

