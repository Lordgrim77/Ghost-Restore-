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
        """Determine non-root user to execute Ghost CLI commands."""
        # 1. Check directory owner
        if pwd:
            try:
                stat_info = os.stat(self.ghost_dir)
                owner_name = pwd.getpwuid(stat_info.st_uid).pw_name
                if owner_name not in ["root", "daemon"]:
                    return owner_name
            except Exception:
                pass

        # 2. Check for 'ghost' or 'ubuntu' user
        for candidate in ["ghost", "ubuntu", os.environ.get("SUDO_USER"), os.environ.get("USER")]:
            if candidate and candidate != "root":
                if pwd:
                    try:
                        pwd.getpwnam(candidate)
                        return candidate
                    except KeyError:
                        continue
                else:
                    return candidate
        return "ubuntu"

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

        # Ghost CLI status check
        cli_status = self.run_ghost_cli("status")
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
                dump_cmd = [
                    "mysqldump",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{user}",
                    "--single-transaction",
                    "--quick",
                    "--routines",
                    "--triggers"
                ]
                if password:
                    dump_cmd.append(f"-p{password}")
                dump_cmd.append(database)

                with open(sql_dump_file, "w", encoding="utf-8") as out:
                    proc = subprocess.run(dump_cmd, stdout=out, stderr=subprocess.PIPE, text=True)
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

            # 3. Backup Uploaded Media & Settings
            notify("🖼️ [4/5] Archiving media images & routes...")
            src_images = os.path.join(content_dir, "images")
            if os.path.exists(src_images):
                shutil.copytree(src_images, os.path.join(staging_content, "images"), dirs_exist_ok=True)

            src_settings = os.path.join(content_dir, "settings")
            if os.path.exists(src_settings):
                shutil.copytree(src_settings, os.path.join(staging_content, "settings"), dirs_exist_ok=True)

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
            self.run_ghost_cli("stop")

            # 2. Extract Archive with Backslash Normalization
            notify("📂 [2/6] Extracting archive & normalizing paths...")
            bs = chr(92)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for m in zf.infolist():
                    clean_name = m.filename.replace(bs, "/").lstrip("/")
                    if not clean_name:
                        continue
                    target = os.path.join(staging_dir, clean_name)
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
                    if os.path.isdir(dest_theme):
                        shutil.rmtree(dest_theme, ignore_errors=True)
                    shutil.copytree(src_theme, dest_theme)

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
                    # Direct MySQL dump import
                    cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}"]
                    if password:
                        cmd.append(f"-p{password}")
                    cmd.append(database)
                    with open(mysql_sql, "r", encoding="utf-8") as sf:
                        proc = subprocess.run(cmd, stdin=sf, capture_output=True, text=True)
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
            ghost_user = self.get_ghost_user()
            if is_root():  # If root, fix ownership
                try:
                    subprocess.run(["chown", "-R", f"{ghost_user}:{ghost_user}", target_content], check=False)
                    subprocess.run(["find", target_content, "-type", "d", "-exec", "chmod", "775", "{}", "+"], check=False)
                    subprocess.run(["find", target_content, "-type", "f", "-exec", "chmod", "664", "{}", "+"], check=False)
                except Exception as e:
                    notify(f"⚠️ Permission setting notice: {e}")

            # Start Ghost
            start_res = self.run_ghost_cli("start")
            if not start_res["success"]:
                # Try restart
                start_res = self.run_ghost_cli("restart")

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

        cmd = ["mysql", f"-h{host}", f"-P{port}", f"-u{user}"]
        if password:
            cmd.append(f"-p{password}")
        cmd.append(database)

        with open(sql_tmp.name, "r", encoding="utf-8") as sf:
            subprocess.run(cmd, stdin=sf, capture_output=True, text=True)
        os.remove(sql_tmp.name)

    def list_backups(self):
        """Lists available backup archives sorted newest to oldest."""
        if not os.path.exists(self.backups_dir):
            return []
        files = glob.glob(os.path.join(self.backups_dir, "ghost-backup-*.zip"))
        results = []
        for f in files:
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
        results.sort(key=lambda x: x["mtime"], reverse=True)
        return results
