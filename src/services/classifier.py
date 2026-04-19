"""
Email classifier service — keyword pre-filter + async parallel Ollama.
Split into: filter → ollama → formatter (ISP compliant).
"""
import asyncio
import json
import time

import aiohttp

from src.config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    LARGE_DEBIT_THRESHOLD, CATEGORIES, RETRY_ATTEMPTS, RETRY_DELAY,
)

# ── Block list ────────────────────────────────────────────────
BLOCK_KEYWORDS = [
    "unsubscribe", "opt out", "opt-out",
    "% off", "discount", "sale ends", "limited offer", "exclusive deal",
    "flash sale", "buy now", "shop now", "order now", "free delivery",
    "cashback offer", "promo code", "coupon",
    "otp", "one time password", "verification code", "do not share",
    "newsletter", "weekly digest", "monthly digest",
    "congratulations you won", "you have been selected",
    "click here to claim", "winner",
]
BLOCK_SENDERS = [
    "noreply@amazon", "deals@", "offers@", "promotions@",
    "newsletter@", "marketing@", "no-reply@flipkart",
    "noreply@swiggy", "noreply@zomato", "alerts@myntra",
    "noreply@meesho", "noreply@ajio",
]
TRUSTED_DOMAINS = {
    "hdfcbank.com", "icicibank.com", "icici.bank.in", "icicibank.net",
    "sbi.co.in", "onlinesbi.com", "axisbank.com",
    "kotak.com", "yesbank.in", "indusind.com", "federalbank.co.in",
    "idfcfirstbank.com", "rbl.co.in",
    "paytm.com", "phonepe.com",
    "zerodha.com", "groww.in", "upstox.com", "angelone.in",
    "nsdl.co.in", "cdslindia.com", "bseindia.com", "nseindia.com",
    "mfuonline.com", "camsonline.com", "kfintech.com",
    "licindia.in", "hdfclife.com", "iciciprulife.com", "sbilife.co.in",
    "maxlifeinsurance.com", "bajajfinserv.in",
    "incometax.gov.in", "tin-nsdl.com", "traces.gov.in",
    "epfindia.gov.in", "uidai.gov.in",
    "naukri.com", "linkedin.com", "indeed.com", "foundit.in",
    "udemy.com", "coursera.org",
    "icicisecurities.com",
}
TECH_BLOG_DOMAINS = {
    "medium.com", "substack.com", "dev.to", "hashnode.com",
    "thenewstack.io", "infoq.com", "dzone.com", "baeldung.com",
    "martinfowler.com", "thoughtworks.com", "aws.amazon.com",
    "cloud.google.com", "techcrunch.com", "theregister.com",
    "hackernewsletter.com", "tldr.tech", "bytebytego.com",
    "newsletter.pragmaticengineer.com", "architecturenotes.co",
    "javarevisited.substack.com",
}
SUBJECT_KEYWORDS = [
    "account statement", "bank statement", "credit card statement",
    "emi due", "loan statement", "fd maturity", "fd receipt",
    "net banking", "cheque bounce", "minimum balance",
    "demat account", "contract note", "dividend credited",
    "mutual fund", "sip installment", "portfolio statement",
    "statement of accounts for funds", "fund statement", "folio statement",
    "consolidated account statement", "cas statement",
    "redemption", "units allotted", "nav statement",
    "capital gains", "annual statement",
    "income tax", "itr filed", "itr verified", "form 16",
    "tds certificate", "tax refund", "26as", "ais statement",
    "advance tax", "tax demand",
    "policy renewal", "premium due", "premium receipt",
    "policy document", "claim settled", "maturity amount",
    "salary credited", "payslip", "offer letter", "appointment letter",
    "relieving letter", "experience letter", "increment letter",
    "appraisal", "joining date", "full and final",
    "job opportunity", "interview scheduled", "interview invitation",
    "application shortlisted", "hiring for", "job opening",
    "course completion", "certificate issued", "training schedule",
    "workshop registration", "webinar invite",
]

SYSTEM_PROMPT = f"""You are an email classifier for an Indian IT professional.
Given an email subject, sender, and body snippet, determine which categories it belongs to:
{chr(10).join(f'- {c}' for c in CATEGORIES)}

Rules:
- For bank/finance emails: always extract the transaction amount in the summary
- For "⚠️ Large Bank Debit Alert": only if amount > ₹{LARGE_DEBIT_THRESHOLD:,}
- Keep summary to one short sentence

Respond with JSON only:
{{"categories": ["Category1"], "summary": "one line summary"}}"""


# ── Filter (Single Responsibility) ───────────────────────────

def is_blocked(email: dict) -> bool:
    sender = email.get("from", "").lower()
    text = email.get("subject", "").lower() + " " + email.get("snippet", "").lower()
    return any(b in sender for b in BLOCK_SENDERS) or any(b in text for b in BLOCK_KEYWORDS)


def is_tech_blog(email: dict) -> bool:
    return any(d in email.get("from", "").lower() for d in TECH_BLOG_DOMAINS)


def is_large_debit(email: dict) -> bool:
    import re
    sender = email.get("from", "").lower()
    text = (email.get("subject", "") + " " + email.get("snippet", "")).lower()
    if not any(d in sender for d in TRUSTED_DOMAINS):
        return False
    if not any(w in text for w in ["debited", "debit", "withdrawn", "deducted"]):
        return False
    for amt in re.findall(r'(?:rs\.?|₹|inr)\s*([0-9,]+)', text):
        try:
            if int(amt.replace(",", "")) >= LARGE_DEBIT_THRESHOLD:
                return True
        except ValueError:
            pass
    return False


def is_keyword_match(email: dict) -> bool:
    sender = email.get("from", "").lower()
    if any(d in sender for d in TRUSTED_DOMAINS):
        return True
    text = email.get("subject", "").lower() + " " + email.get("snippet", "").lower()
    return any(kw in text for kw in SUBJECT_KEYWORDS)


# ── Ollama (Single Responsibility) ───────────────────────────

async def _ask_ollama(session: aiohttp.ClientSession, email: dict) -> dict | None:
    prompt = f"Subject: {email['subject']}\nFrom: {email['from']}\nBody: {email['snippet']}"
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            t = time.perf_counter()
            async with session.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT),
            ) as resp:
                data = await resp.json()
                elapsed = time.perf_counter() - t
                print(f"  ⏱  ollama '{email['subject'][:30]}': {elapsed:.2f}s")
                content = data["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content)
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                print(f"  [classifier] Ollama error after {attempt} attempts: {e}")
                return None
            await asyncio.sleep(RETRY_DELAY)
    return None


# ── Formatter (Single Responsibility) ────────────────────────

def format_message(items: list[dict]) -> str:
    if not items:
        return ""
    sections: dict[str, list] = {}
    for item in items:
        cat = item["categories"][0] if item["categories"] else "Other"
        sections.setdefault(cat, []).append(item)

    lines = ["📧 *Daily Email Summary*\n"]
    for cat, emails in sections.items():
        lines.append(f"━━━ {cat} ━━━")
        for i, e in enumerate(emails, 1):
            lines.append(f"  {i}. {e['subject']}")
            lines.append(f"     {e['summary']}")
        lines.append("")
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────

async def classify_emails(emails: list[dict]) -> str:
    print(f"  [classifier] Step 1: keyword filter on {len(emails)} emails...")
    candidates = []
    for e in emails:
        if is_blocked(e):
            print(f"  [classifier]   BLOCKED: '{e['subject'][:50]}'")
        elif is_tech_blog(e) or is_large_debit(e) or is_keyword_match(e):
            print(f"  [classifier]   PASS:    '{e['subject'][:50]}'")
            candidates.append(e)
        else:
            print(f"  [classifier]   SKIP:    '{e['subject'][:50]}'")
    print(f"  [classifier] {len(candidates)} passed keyword filter")

    if not candidates:
        return ""

    print(f"  [classifier] Step 2: async parallel Ollama on {len(candidates)} candidates...")
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_ask_ollama(session, e) for e in candidates],
            return_exceptions=True,
        )
    print(f"  ⏱  ollama parallel ({len(candidates)} calls): {time.perf_counter()-t0:.2f}s")

    important = []
    for email, result in zip(candidates, results):
        if isinstance(result, Exception) or not result:
            continue
        if result.get("categories"):
            print(f"  [classifier]   → '{email['subject'][:50]}' matched: {result['categories']}")
            important.append({
                "subject": email["subject"],
                "from": email["from"],
                "categories": result["categories"],
                "summary": result.get("summary", ""),
            })

    print(f"  [classifier] {len(important)} important emails found")
    return format_message(important)
