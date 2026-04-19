#!/usr/bin/env python3
"""
Reminder — sends a WhatsApp reminder if the agent hasn't run today.
Scheduled separately at a later time (e.g. 9 AM) as a safety net.
"""

import os
from datetime import date
from whatsapp_notifier import send_whatsapp_summary

LAST_RUN_FILE = os.path.join(os.path.dirname(__file__), ".last_run")


def record_run():
    """Call this at the end of a successful agent run."""
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(date.today()))


def has_run_today() -> bool:
    if not os.path.exists(LAST_RUN_FILE):
        return False
    with open(LAST_RUN_FILE) as f:
        return f.read().strip() == str(date.today())


if __name__ == "__main__":
    if not has_run_today():
        send_whatsapp_summary(
            "⚠️ *Email Agent Reminder*\n\n"
            "Your email agent hasn't run today.\n"
            "Please turn on your Mac and let it run, or trigger it manually:\n"
            "`cd ~/Projects/repo/email-agent && python3 agent.py`"
        )
