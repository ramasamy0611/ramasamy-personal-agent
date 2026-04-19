"""
Email classifier — keyword pre-filter then async parallel Ollama calls.
No data leaves your machine.
"""

import asyncio
import json
import time
import aiohttp

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

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

# --- Block these first — promotions, ads, OTPs, newsletters ---
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

# --- Trusted sender domains (high-confidence, skip Ollama) ---
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
}

# --- Tech blogs/newsletters worth reading ---
TECH_BLOG_DOMAINS = {
    "medium.com", "substack.com", "dev.to", "hashnode.com",
    "thenewstack.io", "infoq.com", "dzone.com", "baeldung.com",
    "martinfowler.com", "thoughtworks.com", "aws.amazon.com",
    "cloud.google.com", "techcrunch.com", "theregister.com",
    "hackernewsletter.com", "tldr.tech", "bytebytego.com",
    "newsletter.pragmaticengineer.com", "architecturenotes.co",
}

# --- Sharp subject keywords ---
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

# Debit amounts above this (₹) trigger an alert
LARGE_DEBIT_THRESHOLD = 5000

SYSTEM_PROMPT = f"""You are an email classifier for an Indian IT professional.
Given an email subject, sender, and body snippet, determine which categories it belongs to:
{chr(10).join(f'- {c}' for c in CATEGORIES)}

Rules:
- For bank/finance emails: always extract the transaction amount in the summary (e.g. "₹4,925 debited from ICICI credit card")
- For "⚠️ Large Bank Debit Alert": only if amount > ₹5000
- For "Tech Blog / Article to Read": only if it's a technical article/newsletter
- Keep summary to one short sentence

Respond with JSON only:
{{"categories": ["Category1"], "summary": "one line summary"}}"""


async def classify_emails(emails: list[dict]) -> str:
    """Entry point — async coroutine, await directly from agent."""
    return await _classify_async(emails)


async def _classify_async(emails: list[dict]) -> str:
    # Step 1: keyword pre-filter (instant, no I/O)
    print(f"  [classify] Step 1: keyword filter on {len(emails)} emails...")
    candidates = []
    for e in emails:
        if _is_blocked(e):
            print(f"  [classify]   BLOCKED: '{e['subject'][:50]}'")
        elif _is_tech_blog(e) or _is_large_debit(e) or _keyword_match(e):
            print(f"  [classify]   PASS:    '{e['subject'][:50]}' from '{e['from'][:40]}'")
            candidates.append(e)
        else:
            print(f"  [classify]   SKIP:    '{e['subject'][:50]}'")
    print(f"  [classify] Step 1: {len(candidates)} passed keyword filter")

    if not candidates:
        print("  [classify] No candidates — skipping Ollama")
        return ""

    # Step 2: async parallel Ollama calls
    print(f"  [classify] Step 2: async parallel Ollama on {len(candidates)} candidates...")
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        tasks = [_ask_ollama_async(session, e) for e in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f"  ⏱  ollama parallel ({len(candidates)} calls): {time.perf_counter()-t0:.2f}s")

    important = []
    for email, result in zip(candidates, results):
        if isinstance(result, Exception):
            print(f"  [classify] error for '{email['subject'][:40]}': {result}")
            continue
        if result and result.get("categories"):
            print(f"  [classify]   → '{email['subject'][:50]}' matched: {result['categories']}")
            important.append({
                "subject": email["subject"],
                "from": email["from"],
                "categories": result["categories"],
                "summary": result.get("summary", ""),
            })

    print(f"  [classify] {len(important)} important emails found")
    return _format_message(important) if important else ""


async def _ask_ollama_async(session: aiohttp.ClientSession, email: dict) -> dict | None:
    t = time.perf_counter()
    prompt = f"Subject: {email['subject']}\nFrom: {email['from']}\nBody: {email['snippet']}"
    try:
        async with session.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            elapsed = time.perf_counter() - t
            usage = data.get("usage", {})
            tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            print(f"  ⏱  ollama '{email['subject'][:30]}': {elapsed:.2f}s{f', tokens={tokens}' if tokens else ''}")
            content = data["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception as e:
        print(f"  [classify] Ollama error: {e}")
        return None


def _is_blocked(email: dict) -> bool:
    """Return True if email is a promotion, ad, OTP, or newsletter — skip entirely."""
    sender = email.get("from", "").lower()
    subject = email.get("subject", "").lower()
    snippet = email.get("snippet", "").lower()
    text = subject + " " + snippet

    if any(b in sender for b in BLOCK_SENDERS):
        return True
    if any(b in text for b in BLOCK_KEYWORDS):
        return True
    return False


def _is_tech_blog(email: dict) -> bool:
    sender = email.get("from", "").lower()
    return any(domain in sender for domain in TECH_BLOG_DOMAINS)


def _is_large_debit(email: dict) -> bool:
    """Detect bank debit alerts with amount above threshold."""
    import re
    sender = email.get("from", "").lower()
    text = (email.get("subject", "") + " " + email.get("snippet", "")).lower()

    if not any(d in sender for d in TRUSTED_DOMAINS):
        return False
    if not any(w in text for w in ["debited", "debit", "withdrawn", "deducted"]):
        return False

    amounts = re.findall(r'(?:rs\.?|₹|inr)\s*([0-9,]+)', text)
    for amt in amounts:
        try:
            if int(amt.replace(",", "")) >= LARGE_DEBIT_THRESHOLD:
                return True
        except ValueError:
            pass
    return False


def _keyword_match(email: dict) -> bool:
    """Trusted sender domain or sharp subject keyword match."""
    sender = email.get("from", "").lower()
    if any(domain in sender for domain in TRUSTED_DOMAINS):
        return True
    text = email.get("subject", "").lower() + " " + email.get("snippet", "").lower()
    return any(kw in text for kw in SUBJECT_KEYWORDS)


def _format_message(items: list[dict]) -> str:
    # Group by primary category
    sections: dict[str, list[dict]] = {}
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
