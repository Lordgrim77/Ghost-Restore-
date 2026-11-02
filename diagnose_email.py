#!/usr/bin/env python3
"""
Ghost Email Diagnostic & Fix Utility
Checks:
1. config.production.json mail block (transport, host, port, user, pass)
2. Live SMTP connection & authentication
3. Ghost logs for recent email delivery failures
"""

import os
import sys
import json
import smtplib
import ssl
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

GHOST_DIR = "/var/www/ghost" if os.name != 'nt' else r"C:\Users\LordgrimxDJay\.gemini\antigravity\scratch\ghost-blog"

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as e:
        return "", str(e), 1

def main():
    print("=" * 65)
    print(" 🔍 GHOST EMAIL DIAGNOSTIC & HEALTH CHECK")
    print("=" * 65)

    config_path = os.path.join(GHOST_DIR, "config.production.json")
    if not os.path.exists(config_path):
        # Fallback to current directory or development
        for alt in ["config.production.json", "config.development.json", os.path.join(GHOST_DIR, "config.development.json")]:
            if os.path.exists(alt):
                config_path = alt
                break

    if not os.path.exists(config_path):
        print(f"❌ [CRITICAL] Could not locate Ghost config file at {config_path}")
        return

    print(f"[*] Reading config from: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"❌ [ERROR] Failed to parse config JSON: {e}")
        return

    site_url = cfg.get("url", "Unknown")
    print(f"[*] Site URL: {site_url}")

    mail_cfg = cfg.get("mail")
    if not mail_cfg:
        print("\n❌ [CRITICAL ISSUE FOUND]")
        print("   No 'mail' configuration found in config.production.json!")
        print("   Ghost is falling back to 'Direct' transport (port 25).")
        print("   Direct mail is blocked on 99% of cloud servers.")
        return

    transport = mail_cfg.get("transport", "direct").lower()
    from_addr = mail_cfg.get("from", "Not set")
    options = mail_cfg.get("options", {})
    host = options.get("host")
    port = options.get("port")
    service = options.get("service")
    auth = options.get("auth", {})
    user = auth.get("user", "")
    passwd = auth.get("pass", "")

    print(f"[*] Transport: {transport}")
    print(f"[*] Service: {service or 'None'}")
    print(f"[*] Host: {host or 'None'}")
    print(f"[*] Port: {port or 'None'}")
    print(f"[*] From Address: {from_addr}")
    print(f"[*] User: {user if user else 'Not configured'}")
    print(f"[*] Password: {'*' * len(passwd) if passwd else 'Not configured'}")

    # 1. Check for Direct Mail on Cloud Host
    if transport == "direct":
        print("\n❌ [CRITICAL ISSUE FOUND: DIRECT TRANSPORT]")
        print("   Ghost is configured with 'Direct' transport.")
        print("   Direct mail tries to connect to recipients via outbound port 25.")
        print("   Outbound port 25 is blocked on all major cloud VPS providers.")
        print("   Fix: Configure SMTP (e.g. Gmail SMTP, Mailgun, or Sendgrid).")
        return

    # 2. Live SMTP Connectivity & Authentication Test
    if transport == "smtp" and host and port:
        print("\n[*] Step 2: Testing live SMTP connection to " + f"{host}:{port}...")
        try:
            port = int(port)
            if port == 465 or options.get("secureConnection") is True:
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=12)
            else:
                server = smtplib.SMTP(host, port, timeout=12)
                server.starttls()
            
            print(f"   ✓ TCP Connection & SSL/TLS handshake to {host}:{port} SUCCEEDED!")

            if user and passwd:
                print(f"[*] Step 3: Testing SMTP credentials for '{user}'...")
                try:
                    server.login(user, passwd)
                    print(f"   ✓ Authentication SUCCESSFUL! SMTP server accepted credentials for {user}.")
                    
                    # Test sending a minimal test email
                    test_recipient = user
                    print(f"[*] Step 3b: Sending test message to {test_recipient}...")
                    test_msg = f"From: {from_addr or user}\r\nTo: {test_recipient}\r\nSubject: Ghost Email Test Verification\r\n\r\nHello,\r\nThis is a test email sent from Ghost SMTP Diagnostic tool.\r\nIf you see this, your outbound email is working perfectly!\r\n"
                    server.sendmail(user, [test_recipient], test_msg.encode('utf-8'))
                    print(f"   ✓ Test email sent successfully to {test_recipient}!")
                    print("   👉 Check your inbox (and Spam/Junk folder).")
                    server.quit()
                except smtplib.SMTPAuthenticationError as auth_err:
                    print(f"   ❌ [AUTHENTICATION FAILED]: {auth_err}")
                    print("   👉 If using Gmail:")
                    print("      1. Your Google App Password may have expired or been revoked.")
                    print("      2. Ensure 2-Step Verification is ON in your Google Account.")
                    print("      3. Generate a new App Password at: https://myaccount.google.com/apppasswords")
                    print("      4. Update your config with the new 16-character password.")
                    server.quit()
                    return
                except Exception as login_err:
                    print(f"   ❌ [LOGIN / SEND ERROR]: {login_err}")
                    server.quit()
                    return
            else:
                print("   ⚠️ No auth credentials provided in config.")
                server.quit()

        except Exception as conn_err:
            print(f"   ❌ [CONNECTION FAILED]: {conn_err}")
            print(f"   👉 Cannot reach {host}:{port}. Check firewall or host/port settings.")
            return

    # 3. Check Ghost Service Logs for Recent Mail Failures
    print("\n[*] Step 4: Checking Ghost systemd logs for recent email errors...")
    svc_cmd = "systemctl list-units --type=service | grep ghost_ | awk '{print $1}' | head -n 1"
    svc, _, _ = run_cmd(svc_cmd)
    if not svc:
        svc = "ghost_pedohunters-xlordgrim-com"

    log_cmd = f"journalctl -u {svc} -n 150 --no-pager | grep -iE 'mail|email|smtp|econnrefused|etimedout|eenvelope|535|550|magic-link|auth' | tail -n 20"
    logs, _, _ = run_cmd(log_cmd)
    if logs:
        print("--- Recent Relevant Ghost Logs ---")
        print(logs)
        print("----------------------------------")
    else:
        print("   (No recent email error logs found in systemd journal)")

    print("\n" + "=" * 65)
    print(" ✅ DIAGNOSTIC COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    main()
