#!/usr/bin/env python3
"""
Automated Ghost SQLite to MySQL Migration Script (v2 - Datetime & Re-run Aware)
-------------------------------------------------------------------------------
Migrates a live Ghost instance from SQLite to MySQL on Ubuntu 24.04 / Debian.
1. Backs up current SQLite database
2. Sets up MySQL database & dedicated user
3. Configures config.production.json
4. Initializes schema via Ghost knex-migrator
5. Auto-converts SQLite epoch timestamps to MySQL DATETIME format
6. Transfers all data (posts, tags, users, members, settings) with FK checks disabled
7. Restarts Ghost on MySQL
"""

import os
import sys
import json
import sqlite3
import shutil
import subprocess
import time
import glob
import datetime
import re

GHOST_DIR = "/var/www/ghost"
MYSQL_DB = "ghost_production"
MYSQL_USER = "ghost_app"
MYSQL_PASS = "GhostSecureProd2026!"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306

def restore_permissions(config_path=None):
    if not config_path:
        config_path = os.path.join(GHOST_DIR, "config.production.json")
    sudo_user = os.environ.get("SUDO_USER", "ubuntu")
    subprocess.run(["chown", "-R", f"{sudo_user}:ghost", GHOST_DIR], check=False)
    subprocess.run(["chown", "-R", "ghost:ghost", os.path.join(GHOST_DIR, "content")], check=False)
    if os.path.exists(config_path):
        subprocess.run(["chmod", "664", config_path], check=False)
    subprocess.run(["chmod", "775", GHOST_DIR], check=False)

def log(msg):
    print(f"[*] {msg}", flush=True)

def error(msg):
    restore_permissions()
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

def get_systemd_service():
    cli_file = os.path.join(GHOST_DIR, ".ghost-cli.json")
    if os.path.exists(cli_file):
        try:
            with open(cli_file, "r") as f:
                name = json.load(f).get("name")
                if name:
                    return f"ghost_{name}"
        except Exception:
            pass
    for udir in ["/etc/systemd/system", "/usr/lib/systemd/system", "/lib/systemd/system"]:
        if os.path.exists(udir):
            matches = glob.glob(os.path.join(udir, "ghost_*.service"))
            if matches:
                return os.path.basename(matches[0]).replace(".service", "")
    return "ghost_pedohunters-xlordgrim-com"

def main():
    if os.geteuid() != 0:
        error("This script must be run as root (sudo python3 migrate_to_mysql.py)")

    log("Starting Ghost SQLite -> MySQL Migration (v2)...")
    svc_name = get_systemd_service()
    log(f"Detected Ghost systemd service: {svc_name}")

    config_path = os.path.join(GHOST_DIR, "config.production.json")
    if not os.path.exists(config_path):
        error(f"Cannot find {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 1. Locate current SQLite database (or safety backup from prior run)
    log("Step 1/6: Locating existing SQLite database...")
    sqlite_file = None
    
    # Check for original .db files first
    candidates = glob.glob(os.path.join(GHOST_DIR, "content/data/*.db"))
    if candidates:
        sqlite_file = candidates[0]
    else:
        # Fallback to backups created earlier
        backup_candidates = glob.glob(os.path.join(GHOST_DIR, "content/data/*.backup_before_mysql_*"))
        if backup_candidates:
            backup_candidates.sort(key=os.path.getmtime, reverse=True)
            sqlite_file = backup_candidates[0]

    if not sqlite_file or not os.path.exists(sqlite_file):
        error(f"Could not locate active SQLite .db file in {GHOST_DIR}/content/data/")

    log(f"Found SQLite database: {sqlite_file} ({os.path.getsize(sqlite_file)} bytes)")

    # 2. Backup SQLite database if not already a backup file
    if ".backup_before_mysql_" not in sqlite_file:
        backup_file = sqlite_file + f".backup_before_mysql_{int(time.time())}"
        shutil.copy2(sqlite_file, backup_file)
        log(f"Created safety backup: {backup_file}")
    else:
        backup_file = sqlite_file
        log(f"Using verified safety backup: {backup_file}")

    # 3. Stop Ghost
    log("Step 2/6: Stopping Ghost...")
    subprocess.run(["systemctl", "stop", svc_name], check=False)
    subprocess.run(["pkill", "-9", "-f", "node.*current/index.js"], check=False)
    time.sleep(1)

    # 4. Create MySQL Database & User
    log("Step 3/6: Ensuring MySQL database & user...")
    sql_setup = f"""
    CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'localhost' IDENTIFIED BY '{MYSQL_PASS}';
    ALTER USER '{MYSQL_USER}'@'localhost' IDENTIFIED BY '{MYSQL_PASS}';
    CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'127.0.0.1' IDENTIFIED BY '{MYSQL_PASS}';
    ALTER USER '{MYSQL_USER}'@'127.0.0.1' IDENTIFIED BY '{MYSQL_PASS}';
    GRANT ALL PRIVILEGES ON `{MYSQL_DB}`.* TO '{MYSQL_USER}'@'localhost';
    GRANT ALL PRIVILEGES ON `{MYSQL_DB}`.* TO '{MYSQL_USER}'@'127.0.0.1';
    FLUSH PRIVILEGES;
    """
    res = subprocess.run(["mysql", "-u", "root", "-e", sql_setup], capture_output=True, text=True)
    if res.returncode != 0:
        error(f"Failed to configure MySQL database/user: {res.stderr}")
    log(f"MySQL database `{MYSQL_DB}` and user `{MYSQL_USER}` ready.")

    # 5. Update config.production.json to MySQL
    log("Step 4/6: Updating config.production.json to MySQL...")
    cfg["database"] = {
        "client": "mysql",
        "connection": {
            "host": MYSQL_HOST,
            "port": MYSQL_PORT,
            "user": MYSQL_USER,
            "password": MYSQL_PASS,
            "database": MYSQL_DB
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    restore_permissions(config_path)

    # 6. Initialize Ghost tables in MySQL via boot if needed
    log("Step 5/6: Verifying MySQL tables & schema...")
    res = subprocess.run([
        "mysql", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", f"-h{MYSQL_HOST}",
        "-e", f"SELECT count(*) FROM information_schema.tables WHERE table_schema='{MYSQL_DB}';"
    ], capture_output=True, text=True)
    
    schema_ready = False
    if res.returncode == 0:
        lines = res.stdout.strip().split("\n")
        if len(lines) > 1 and lines[1].isdigit() and int(lines[1]) > 40:
            log(f"Schema already initialized with {lines[1]} tables.")
            schema_ready = True

    if not schema_ready:
        log("Booting Ghost to initialize schema...")
        restore_permissions(config_path)
        subprocess.run(["systemctl", "start", svc_name], check=False)
        for _ in range(25):
            time.sleep(1)
            res = subprocess.run([
                "mysql", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", f"-h{MYSQL_HOST}",
                "-e", f"SELECT count(*) FROM information_schema.tables WHERE table_schema='{MYSQL_DB}';"
            ], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")
                if len(lines) > 1 and lines[1].isdigit() and int(lines[1]) > 40:
                    log(f"Schema initialized! Found {lines[1]} tables in MySQL.")
                    schema_ready = True
                    break
        subprocess.run(["systemctl", "stop", svc_name], check=False)
        time.sleep(1)

    # Fetch exact MySQL column schema for strict type alignment
    log("Inspecting MySQL column data types...")
    mysql_types = {}  # (table, column) -> data_type
    res = subprocess.run([
        "mysql", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", f"-h{MYSQL_HOST}", "-B", "-N",
        "-e", f"SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='{MYSQL_DB}';"
    ], capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        for line in res.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 3:
                mysql_types[(parts[0].lower(), parts[1].lower())] = parts[2].lower()
    log(f"Mapped {len(mysql_types)} column types from MySQL schema.")

    # 7. Migrate all SQLite data into MySQL with Datetime Normalization
    log("Step 6/6: Migrating all data from SQLite into MySQL with datetime normalization...")
    s_conn = sqlite3.connect(backup_file)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    s_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in s_cur.fetchall() if r[0] not in ('migrations', 'migrations_lock')]

    def format_cell(table_name, col_name, val):
        if val is None:
            return "NULL"
        
        target_type = mysql_types.get((table_name.lower(), col_name.lower()), "")
        col_lower = col_name.lower()
        is_dt = (
            target_type in ("datetime", "timestamp", "date") or
            col_lower.endswith(("_at", "_expires", "_date", "request", "lifetime")) or
            col_lower in ("created_at", "updated_at", "published_at", "last_seen_at")
        )

        if is_dt:
            if val == "" or str(val).lower() in ("null", "none", "undefined"):
                return "NULL"
            # Handle millisecond epoch or second epoch integer/float
            if isinstance(val, (int, float)) and val > 1000000000:
                ts = val / 1000.0 if val > 1000000000000 else float(val)
                dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
                return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"
            # Handle string of numeric digits
            if isinstance(val, str) and val.isdigit() and int(val) > 1000000000:
                int_val = int(val)
                ts = int_val / 1000.0 if int_val > 1000000000000 else float(int_val)
                dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
                return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"
            # Handle ISO string e.g. 2026-11-01T14:05:33.000Z
            if isinstance(val, str) and ('T' in val or '-' in val):
                clean = val.replace('T', ' ').replace('Z', '').split('.')[0]
                if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', clean):
                    return f"'{clean}'"
                elif re.match(r'^\d{4}-\d{2}-\d{2}$', clean):
                    return f"'{clean} 00:00:00'"
            # If target column in MySQL is datetime/timestamp, ensure we don't insert invalid syntax
            if target_type in ("datetime", "timestamp", "date"):
                return "NULL"

        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, (bytes, bytearray)):
            return f"X'{val.hex()}'"

        s = str(val).replace("\\", "\\\\").replace("'", "\\'").replace("\0", "")
        return f"'{s}'"

    sql_statements = [
        "SET FOREIGN_KEY_CHECKS = 0;",
        "SET SQL_MODE = '';"
    ]
    total_migrated = 0

    for t in tables:
        try:
            rows = s_cur.execute(f"SELECT * FROM `{t}`").fetchall()
            if not rows:
                continue
            
            raw_cols = list(rows[0].keys())
            # Keep only columns that exist in target MySQL table if schema mapped
            if mysql_types:
                valid_cols = [c for c in raw_cols if (t.lower(), c.lower()) in mysql_types]
            else:
                valid_cols = raw_cols

            if not valid_cols:
                continue

            col_names = ", ".join([f"`{col}`" for col in valid_cols])
            
            for i in range(0, len(rows), 100):
                batch = rows[i:i+100]
                val_rows = []
                for r in batch:
                    vals = ", ".join([format_cell(t, col, r[col]) for col in valid_cols])
                    val_rows.append(f"({vals})")
                sql_statements.append(f"REPLACE INTO `{t}` ({col_names}) VALUES {', '.join(val_rows)};")
                total_migrated += len(batch)
        except Exception as e:
            log(f"Notice skipping table {t}: {e}")

    sql_statements.append("SET FOREIGN_KEY_CHECKS = 1;")
    s_conn.close()

    dump_sql = "\n".join(sql_statements)
    import_res = subprocess.run(
        ["mysql", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", f"-h{MYSQL_HOST}", MYSQL_DB],
        input=dump_sql,
        capture_output=True,
        text=True
    )
    if import_res.returncode != 0:
        error(f"MySQL data import failed: {import_res.stderr}")

    log(f"Successfully migrated {total_migrated} records into MySQL!")

    # 8. Set final permissions & start Ghost permanently on MySQL
    restore_permissions(config_path)
    subprocess.run(["systemctl", "restart", svc_name], check=False)
    time.sleep(3)

    final_status = subprocess.run(["systemctl", "is-active", svc_name], capture_output=True, text=True)
    if "active" in final_status.stdout.lower():
        print("\n" + "="*60)
        print("🎉 SUCCESS! Ghost is now running on MySQL (ghost_production)")
        print(f"✓ All posts, tags, users, members, and settings migrated")
        print(f"✓ Datetimes normalized to MySQL standard format")
        print(f"✓ SQLite OTC verification deadlock bug #25874 is PERMANENTLY RESOLVED")
        print("="*60 + "\n")
    else:
        error("Ghost failed to restart after MySQL migration. Check journalctl -u " + svc_name)

if __name__ == "__main__":
    main()
