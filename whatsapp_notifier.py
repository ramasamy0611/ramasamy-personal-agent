"""
WhatsApp notifier — sends messages via Meta WhatsApp Cloud API.
Credentials stored in macOS Keychain, never in code or .env files.
"""

import os
import requests
from utils import get_secret, log

# Set WA_DRY_RUN=false to actually send. Defaults to True (safe).
DRY_RUN = os.environ.get("WA_DRY_RUN", "true").lower() != "false"

KEYCHAIN_WA_TOKEN = "email-agent-wa-token"
KEYCHAIN_WA_PHONE_ID = "email-agent-wa-phone-id"
KEYCHAIN_WA_TO = "email-agent-wa-to"

META_API_URL = "https://graph.facebook.com/v19.0/{phone_id}/messages"


def send_whatsapp_summary(message: str) -> bool:
    """Send a WhatsApp text message. Returns True on success."""
    dry_run = os.environ.get("WA_DRY_RUN", "true").lower() != "false"
    if dry_run:
        log("  [whatsapp] DRY RUN — message not sent. This is what would go to WhatsApp:")
        print("─" * 60)
        print(message)
        print("─" * 60)
        return True

    token = get_secret(KEYCHAIN_WA_TOKEN)
    phone_id = get_secret(KEYCHAIN_WA_PHONE_ID)
    to_number = get_secret(KEYCHAIN_WA_TO)

    if not all([token, phone_id, to_number]):
        log("  [whatsapp] ERROR: credentials not found in Keychain.")
        return False

    url = META_API_URL.format(phone_id=phone_id)
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to_number,
                  "type": "text", "text": {"body": message}},
            timeout=15,
        )
        response.raise_for_status()
        log("  [whatsapp] Message sent successfully ✅")
        return True
    except requests.HTTPError as e:
        log(f"  [whatsapp] ERROR {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        log(f"  [whatsapp] ERROR: {e}")
        return False
