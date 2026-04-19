"""
Central configuration — all constants and env-var driven settings.
No secrets here. Secrets live in macOS Keychain via utils.get_secret().
"""
import os

# ── Ollama ────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", 30))

# ── Gmail ─────────────────────────────────────────────────────
FETCH_HOURS = int(os.environ.get("FETCH_HOURS", 24))
GMAIL_MAX_RESULTS = int(os.environ.get("GMAIL_MAX_RESULTS", 100))

# ── WhatsApp ──────────────────────────────────────────────────
WA_DRY_RUN = os.environ.get("WA_DRY_RUN", "true").lower() != "false"
WA_API_VERSION = os.environ.get("WA_API_VERSION", "v19.0")
WA_API_URL = f"https://graph.facebook.com/{WA_API_VERSION}/{{phone_id}}/messages"

# Keychain secret keys
KEYCHAIN_WA_TOKEN    = "email-agent-wa-token"
KEYCHAIN_WA_PHONE_ID = "email-agent-wa-phone-id"
KEYCHAIN_WA_TO       = "email-agent-wa-to"

# ── Classifier ────────────────────────────────────────────────
LARGE_DEBIT_THRESHOLD = int(os.environ.get("LARGE_DEBIT_THRESHOLD", 5000))

CATEGORIES = [
    "Bank / Finance",
    "LIC / Insurance",
    "Share Market / Investments",
    "Income Tax / IT Returns",
    "Employment / Salary / HR",
    "Job / Recruitment",
    "Training / Courses / Certification",
    "Tech Blog / Article to Read",
    "⚠️ Large Bank Debit Alert",
]

# ── Retry ─────────────────────────────────────────────────────
RETRY_ATTEMPTS = int(os.environ.get("RETRY_ATTEMPTS", 3))
RETRY_DELAY    = float(os.environ.get("RETRY_DELAY", 2.0))  # seconds
