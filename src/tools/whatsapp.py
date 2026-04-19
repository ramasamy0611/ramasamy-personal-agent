"""
WhatsApp tool — Meta Cloud API sender with retry.
Credentials from macOS Keychain. Respects WA_DRY_RUN.
"""
import time
import requests

from src.config import (
    WA_API_URL, KEYCHAIN_WA_TOKEN, KEYCHAIN_WA_PHONE_ID,
    KEYCHAIN_WA_TO, RETRY_ATTEMPTS, RETRY_DELAY,
)
from utils import get_secret, log


def _is_dry_run() -> bool:
    import os
    return os.environ.get("WA_DRY_RUN", "true").lower() != "false"


def send_message(message: str) -> bool:
    """Send a WhatsApp text message. Returns True on success."""
    if _is_dry_run():
        log("  [whatsapp] DRY RUN — message not sent. This is what would go to WhatsApp:")
        print("─" * 60)
        print(message)
        print("─" * 60)
        return True

    token    = get_secret(KEYCHAIN_WA_TOKEN)
    phone_id = get_secret(KEYCHAIN_WA_PHONE_ID)
    to       = get_secret(KEYCHAIN_WA_TO)

    if not all([token, phone_id, to]):
        log("  [whatsapp] ERROR: credentials not found in Keychain.")
        return False

    url = WA_API_URL.format(phone_id=phone_id)
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            log("  [whatsapp] Message sent ✅")
            return True
        except requests.HTTPError as e:
            log(f"  [whatsapp] HTTP {e.response.status_code}: {e.response.text}")
            return False  # don't retry HTTP errors (bad token, etc.)
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                log(f"  [whatsapp] ERROR after {attempt} attempts: {e}")
                return False
            log(f"  [whatsapp] attempt {attempt} failed: {e} — retrying...")
            time.sleep(RETRY_DELAY)
    return False


def send_image(chart_path: str, caption: str,
               categories: dict = None, total_spent: float = 0) -> bool:
    """Upload chart image and send via WhatsApp. Falls back to ASCII in dry-run."""
    if _is_dry_run():
        log("  [whatsapp] DRY RUN — chart not sent.")
        print(f"  📁 Chart saved at: {chart_path}")
        if categories:
            _print_ascii_chart(categories, total_spent)
        print("─" * 60)
        print(caption)
        print("─" * 60)
        return True

    token    = get_secret(KEYCHAIN_WA_TOKEN)
    phone_id = get_secret(KEYCHAIN_WA_PHONE_ID)
    to       = get_secret(KEYCHAIN_WA_TO)

    if not all([token, phone_id, to]):
        return False

    # Step 1: upload image
    with open(chart_path, "rb") as f:
        upload = requests.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/media",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("chart.png", f, "image/png")},
            data={"messaging_product": "whatsapp"},
            timeout=30,
        )
    if not upload.ok:
        log(f"  [whatsapp] Image upload failed: {upload.text}")
        return False

    media_id = upload.json().get("id")

    # Step 2: send image message
    resp = requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"id": media_id, "caption": caption[:1024]},
        },
        timeout=15,
    )
    if resp.ok:
        log("  [whatsapp] Chart sent ✅")
        return True
    log(f"  [whatsapp] Send failed: {resp.text}")
    return False


def _print_ascii_chart(categories: dict, total_spent: float) -> None:
    max_val = max(categories.values()) if categories else 1
    bar_width = 30
    print("\n📊 Spending Chart (dry-run preview)")
    print("─" * 60)
    for cat, amt in sorted(categories.items(), key=lambda x: -x[1]):
        filled = int((amt / max_val) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = amt / total_spent * 100
        print(f"  {cat:<22} {bar} ₹{amt:>8,.0f} ({pct:.0f}%)")
    print(f"\n  {'TOTAL':<22} {'─'*bar_width} ₹{total_spent:>8,.0f}")
    print("─" * 60)
