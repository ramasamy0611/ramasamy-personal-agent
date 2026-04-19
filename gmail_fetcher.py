"""
Gmail fetcher — reads unread emails from last 24h using read-only OAuth2.
Never deletes or modifies emails.
"""

import os
import pickle
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Read-only scope — cannot delete, send, or modify emails
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".token.pickle")


def _get_gmail_service():
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
                    "credentials.json not found. "
                    "Download it from Google Cloud Console and place it in the project folder."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


def fetch_recent_emails(hours: int = None) -> list[dict]:
    """Fetch unread emails from the last `hours` hours. Read-only."""
    import time
    import os
    if hours is None:
        hours = int(os.environ.get("FETCH_HOURS", 24))
    service = _get_gmail_service()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Fetch all unread emails — let classifier.py do the filtering.
    # Avoid Gmail category filters: they silently drop legitimate emails
    # (job alerts, tax notices, bank alerts) that land in Updates/Social.
    query = f"is:unread after:{since.strftime('%Y/%m/%d')}"

    t0 = time.perf_counter()
    result = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = result.get("messages", [])
    print(f"  [gmail] Query returned {len(messages)} messages ({time.perf_counter()-t0:.2f}s)")

    if not messages:
        return []

    # Batch fetch metadata for all in one HTTP round trip
    t1 = time.perf_counter()
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

    emails = list(results.values())
    print(f"  ⏱  batch metadata fetch ({len(emails)} emails): {time.perf_counter()-t1:.2f}s")
    return emails



