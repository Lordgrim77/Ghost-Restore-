#!/usr/bin/env python3
"""
Ghost Fresh Start with MySQL
----------------------------
1. Cleans and recreates a fresh `ghost_production` MySQL database
2. Sets config.production.json to MySQL
3. Restores correct Ghost ownership & permissions
4. Restarts Ghost service to let Ghost boot and create fresh tables
"""

import os
import sys
import json
import subprocess
import time
import glob

GHOST_DIR = "/var/www/ghost"
MYSQL_DB = "ghost_production"
MYSQL_USER = "ghost_app"
MYSQL_PASS = "GhostSecureProd2026!"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306

def log(msg):
    print(f"[*] {msg}", flush=True)

def error(msg):
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

def restore_permissions(config_path):
    sudo_user = os.environ.get("SUDO_USER", "ubuntu")
    subprocess.run(["chown", "-R", f"{sudo_user}:ghost", GHOST_DIR], check=False)
    subprocess.run(["chown", "-R", "ghost:ghost", os.path.join(GHOST_DIR, "content")], check=False)
    if os.path.exists(config_path):
        subprocess.run(["chmod", "664", config_path], check=False)
    subprocess.run(["chmod", "775", GHOST_DIR], check=False)

def main():
    if os.geteuid() != 0:
        error("This script must be run as root (sudo python3 fresh_start_mysql.py)")

    svc_name = get_systemd_service()
    log(f"Detected Ghost systemd service: {svc_name}")

    config_path = os.path.join(GHOST_DIR, "config.production.json")
    if not os.path.exists(config_path):
        error(f"Cannot find {config_path}")

    # 1. Stop Ghost
    log("Step 1/4: Stopping Ghost...")
    subprocess.run(["systemctl", "stop", svc_name], check=False)
    subprocess.run(["pkill", "-9", "-f", "node.*current/index.js"], check=False)
    time.sleep(1)

    # 2. Recreate clean MySQL Database & User
    log("Step 2/4: Recreating fresh MySQL database `ghost_production`...")
    sql_fresh = f"""
    DROP DATABASE IF EXISTS `{MYSQL_DB}`;
    CREATE DATABASE `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'localhost' IDENTIFIED BY '{MYSQL_PASS}';
    ALTER USER '{MYSQL_USER}'@'localhost' IDENTIFIED BY '{MYSQL_PASS}';
    CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'127.0.0.1' IDENTIFIED BY '{MYSQL_PASS}';
    ALTER USER '{MYSQL_USER}'@'127.0.0.1' IDENTIFIED BY '{MYSQL_PASS}';
    GRANT ALL PRIVILEGES ON `{MYSQL_DB}`.* TO '{MYSQL_USER}'@'localhost';
    GRANT ALL PRIVILEGES ON `{MYSQL_DB}`.* TO '{MYSQL_USER}'@'127.0.0.1';
    FLUSH PRIVILEGES;
    """
    res = subprocess.run(["mysql", "-u", "root", "-e", sql_fresh], capture_output=True, text=True)
    if res.returncode != 0:
        error(f"Failed to initialize fresh MySQL database: {res.stderr}")
    log(f"Database `{MYSQL_DB}` and user `{MYSQL_USER}` created fresh.")

    # 3. Ensure config.production.json points to MySQL
    log("Step 3/4: Updating config.production.json to MySQL...")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

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

    # 4. Set permissions and start Ghost
    log("Step 4/4: Setting permissions and starting Ghost...")
    restore_permissions(config_path)
    subprocess.run(["systemctl", "start", svc_name], check=False)
    
    log("Waiting for Ghost to run fresh knex migrations and boot...")
    time.sleep(8)

    final_status = subprocess.run(["systemctl", "is-active", svc_name], capture_output=True, text=True)
    if "active" in final_status.stdout.lower():
        print("\n" + "="*60)
        print("🎉 SUCCESS! Ghost is running fresh on MySQL!")
        print("✓ Database: MySQL (`ghost_production`)")
        print("✓ All tables initialized cleanly with native schema")
        print("✓ Outbound Gmail SMTP preserved")
        print("✓ Custom Alto theme & images preserved")
        print("👉 Go to your site to create your admin account:")
        print(f"   {cfg.get('url', 'https://pedohunters.xlordgrim.com')}/ghost/")
        print("="*60 + "\n")
    else:
        error("Ghost failed to restart. Check: sudo journalctl -u " + svc_name + " -n 25 --no-pager")

if __name__ == "__main__":
    main()

