"""
Gmail tool — read-only OAuth2 fetcher with retry.
Never deletes or modifies emails.
"""
import os
import pickle
import time
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import FETCH_HOURS, GMAIL_MAX_RESULTS, RETRY_ATTEMPTS, RETRY_DELAY

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CREDENTIALS_FILE = os.path.join(_BASE, "credentials.json")
TOKEN_FILE = os.path.join(_BASE, ".token.pickle")


def get_service():
    """Build and return an authenticated Gmail service. Caches token locally."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "credentials.json not found. Download from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


def fetch_recent_emails(hours: int = None) -> list[dict]:
    """Fetch unread emails from the last `hours` hours. Read-only."""
    hours = hours or FETCH_HOURS
    service = get_service()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = f"is:unread after:{since.strftime('%Y/%m/%d')}"

    t0 = time.perf_counter()
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            result = service.users().messages().list(
                userId="me", q=query, maxResults=GMAIL_MAX_RESULTS
            ).execute()
            break
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            print(f"  [gmail] fetch attempt {attempt} failed: {e} — retrying...")
            time.sleep(RETRY_DELAY)

    messages = result.get("messages", [])
    print(f"  [gmail] Query returned {len(messages)} messages ({time.perf_counter()-t0:.2f}s)")
    if not messages:
        return []

    results = {}

    def handle_response(request_id, response, exception):
        if exception:
            return
        headers = {h["name"]: h["value"] for h in response["payload"]["headers"]}
        results[request_id] = {
            "id": response["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "snippet": response.get("snippet", ""),
            "body": "",
        }

    t1 = time.perf_counter()
    batch = service.new_batch_http_request()
    for msg in messages:
        batch.add(
            service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ),
            callback=handle_response,
            request_id=msg["id"]
        )
    batch.execute()
    print(f"  ⏱  batch metadata fetch ({len(results)} emails): {time.perf_counter()-t1:.2f}s")
    return list(results.values())
