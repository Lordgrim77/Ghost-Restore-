#!/usr/bin/env python3
import subprocess
import json
import sys

new_lexical = {
  "root": {
    "children": [
      {
        "children": [
          {
            "detail": 0,
            "format": 0,
            "mode": "normal",
            "style": "",
            "text": "Welcome to Pedo Hunters. Your subscription has been confirmed.",
            "type": "extended-text",
            "version": 1
          }
        ],
        "direction": "ltr",
        "format": "",
        "indent": 0,
        "type": "paragraph",
        "version": 1
      },
      {
        "children": [
          {
            "detail": 0,
            "format": 0,
            "mode": "normal",
            "style": "",
            "text": "You will receive investigative releases, intelligence briefings, and official updates directly in your inbox. You can access the ",
            "type": "extended-text",
            "version": 1
          },
          {
            "children": [
              {
                "detail": 0,
                "format": 0,
                "mode": "normal",
                "style": "",
                "text": "publication archives",
                "type": "extended-text",
                "version": 1
              }
            ],
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "type": "link",
            "version": 1,
            "rel": "noreferrer",
            "target": None,
            "title": None,
            "url": "__GHOST_URL__/"
          },
          {
            "detail": 0,
            "format": 0,
            "mode": "normal",
            "style": "",
            "text": " at any time to review all reports and developments.",
            "type": "extended-text",
            "version": 1
          }
        ],
        "direction": "ltr",
        "format": "",
        "indent": 0,
        "type": "paragraph",
        "version": 1
      },
      {
        "children": [
          {
            "detail": 0,
            "format": 0,
            "mode": "normal",
            "style": "",
            "text": "For confidential tips, inquiries, or official communications, contact our desk at ",
            "type": "extended-text",
            "version": 1
          },
          {
            "children": [
              {
                "detail": 0,
                "format": 0,
                "mode": "normal",
                "style": "",
                "text": "contact@pedohunters.help",
                "type": "extended-text",
                "version": 1
              }
            ],
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "type": "link",
            "version": 1,
            "rel": "noreferrer",
            "target": None,
            "title": None,
            "url": "mailto:contact@pedohunters.help"
          },
          {
            "detail": 0,
            "format": 0,
            "mode": "normal",
            "style": "",
            "text": ".",
            "type": "extended-text",
            "version": 1
          }
        ],
        "direction": "ltr",
        "format": "",
        "indent": 0,
        "type": "paragraph",
        "version": 1
      }
    ],
    "direction": "ltr",
    "format": "",
    "indent": 0,
    "type": "root",
    "version": 1
  }
}

lexical_escaped = json.dumps(new_lexical).replace("'", "''").replace("\\", "\\\\")

queries = [
    # 1. Update automated welcome email
    f"""UPDATE ghost_production.welcome_email_automated_emails 
        SET lexical = '{lexical_escaped}',
            sender_name = 'Pedo Hunters',
            sender_email = 'noreply@pedohunters.help',
            sender_reply_to = 'contact@pedohunters.help',
            subject = 'Welcome to Pedo Hunters';""",

    # 2. Update email design settings
    """UPDATE ghost_production.email_design_settings 
       SET sender_name = 'Pedo Hunters',
           sender_email = 'noreply@pedohunters.help',
           sender_reply_to = 'contact@pedohunters.help',
           footer_content = '<p>Official Publication &bull; Contact: <a href=\"mailto:contact@pedohunters.help\" style=\"color: #ffffff; text-decoration: underline;\">contact@pedohunters.help</a></p>',
           show_badge = 0;""",

    # 3. Update newsletters
    """UPDATE ghost_production.newsletters 
       SET sender_name = 'Pedo Hunters',
           sender_email = 'noreply@pedohunters.help',
           sender_reply_to = 'contact@pedohunters.help',
           footer_content = '<p>Official Publication &bull; Contact: <a href=\"mailto:contact@pedohunters.help\" style=\"color: #ffffff; text-decoration: underline;\">contact@pedohunters.help</a></p>',
           show_badge = 0;""",

    # 4. Update settings
    """UPDATE ghost_production.settings 
       SET value = 'noreply@pedohunters.help' 
       WHERE key = 'members_support_address';"""
]

def run():
    print("[*] Applying email sender & welcome configuration to Ghost MySQL database...")
    for q in queries:
        try:
            subprocess.run(["mysql", "-e", q], check=True, stderr=subprocess.PIPE)
            print("   ✓ Query executed successfully.")
        except Exception as e:
            print(f"   ! Notice: {e}")

if __name__ == "__main__":
    run()

