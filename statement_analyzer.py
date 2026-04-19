"""
Bank statement analyzer — detects monthly statement email, extracts PDF,
generates spending chart + Ollama insights, sends via WhatsApp image.
"""

import os
import re
import base64
import tempfile
from datetime import datetime
from functools import partial

STATEMENT_SUBJECTS = [
    "credit card statement", "bank statement", "account statement",
    "e-statement", "monthly statement", "statement of account",
]

STATEMENT_DOMAINS = {
    "hdfcbank.com", "icicibank.com", "icici.bank.in", "sbi.co.in",
    "axisbank.com", "kotak.com", "yesbank.in", "indusind.com",
}

# Spending categories mapped from merchant keywords
SPEND_CATEGORIES = {
    "Food & Dining":     ["swiggy", "zomato", "restaurant", "cafe", "food", "dining", "hotel", "pizza", "burger"],
    "Groceries":         ["bigbasket", "blinkit", "zepto", "grofers", "dmart", "supermarket", "grocery", "milk"],
    "Transport":         ["uber", "ola", "rapido", "metro", "petrol", "fuel", "irctc", "railway", "bus", "cab"],
    "Entertainment":     ["netflix", "hotstar", "prime", "spotify", "youtube", "bookmyshow", "cinema", "pvr"],
    "Utilities":         ["electricity", "water", "gas", "broadband", "internet", "airtel", "jio", "bsnl", "tata sky", "dish tv"],
    "Shopping":          ["amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "reliance"],
    "Health":            ["pharmacy", "medical", "hospital", "clinic", "apollo", "medplus", "1mg", "netmeds"],
    "Education":         ["udemy", "coursera", "byju", "unacademy", "school", "college", "fees"],
    "Investments":       ["zerodha", "groww", "mutual fund", "sip", "lic", "insurance", "premium"],
    "Other":             [],
}


def is_statement_email(email: dict) -> bool:
    """Return True if email looks like a monthly bank statement."""
    subject = email.get("subject", "").lower()
    sender = email.get("from", "").lower()
    return (
        any(kw in subject for kw in STATEMENT_SUBJECTS) and
        any(d in sender for d in STATEMENT_DOMAINS)
    )


def download_pdf_attachment(service, message_id: str) -> str | None:
    """Download PDF attachment from Gmail message. Returns temp file path or None."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    def find_pdf(parts):
        for part in parts:
            if part.get("mimeType") == "application/pdf":
                att_id = part.get("body", {}).get("attachmentId")
                if att_id:
                    return att_id
            if "parts" in part:
                result = find_pdf(part["parts"])
                if result:
                    return result
        return None

    parts = msg.get("payload", {}).get("parts", [])
    att_id = find_pdf(parts)
    if not att_id:
        return None

    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=att_id
    ).execute()

    data = base64.urlsafe_b64decode(att["data"] + "==")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name


def extract_transactions(pdf_path: str) -> list[dict]:
    """Extract transactions from PDF using pdfplumber."""
    import pdfplumber

    transactions = []
    amount_pattern = re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)')

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Look for lines with amounts — basic heuristic
                amounts = amount_pattern.findall(line)
                if not amounts:
                    continue
                # Skip header lines
                if any(h in line.lower() for h in ["date", "description", "amount", "balance", "total"]):
                    continue

                try:
                    amount = float(amounts[-1].replace(",", ""))
                except ValueError:
                    continue

                if amount < 10:  # skip tiny amounts (likely page numbers)
                    continue

                transactions.append({
                    "description": line[:80],
                    "amount": amount,
                })

    return transactions


def categorize_transactions(transactions: list[dict]) -> dict[str, float]:
    """Map transactions to spending categories."""
    totals: dict[str, float] = {cat: 0.0 for cat in SPEND_CATEGORIES}

    for txn in transactions:
        desc = txn["description"].lower()
        matched = False
        for cat, keywords in SPEND_CATEGORIES.items():
            if cat == "Other":
                continue
            if any(kw in desc for kw in keywords):
                totals[cat] += txn["amount"]
                matched = True
                break
        if not matched:
            totals["Other"] += txn["amount"]

    return {k: v for k, v in totals.items() if v > 0}


def generate_chart(categories: dict[str, float], total_spent: float,
                   credit_limit: float = 0) -> str:
    """Generate spending chart. Returns path to PNG file."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.patch.set_facecolor("#1a1a2e")

    # --- Left: Donut chart by category ---
    ax1 = axes[0]
    ax1.set_facecolor("#1a1a2e")
    labels = list(categories.keys())
    values = list(categories.values())
    colors = plt.cm.Set3.colors[:len(labels)]

    wedges, texts, autotexts = ax1.pie(
        values, labels=None, autopct="%1.0f%%",
        colors=colors, startangle=90,
        wedgeprops={"edgecolor": "#1a1a2e", "linewidth": 2},
        pctdistance=0.75,
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(9)

    # Centre text
    ax1.text(0, 0, f"₹{total_spent:,.0f}\nTotal Spent",
             ha="center", va="center", fontsize=11,
             color="white", fontweight="bold")

    legend = [mpatches.Patch(color=colors[i], label=f"{labels[i]}: ₹{values[i]:,.0f}")
              for i in range(len(labels))]
    ax1.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.15),
               ncol=2, fontsize=8, framealpha=0, labelcolor="white")
    ax1.set_title("Spending by Category", color="white", fontsize=13, pad=15)

    # --- Right: Spent vs Remaining bar ---
    ax2 = axes[1]
    ax2.set_facecolor("#1a1a2e")

    if credit_limit > 0:
        remaining = max(0, credit_limit - total_spent)
        bars = ax2.bar(["Spent", "Remaining"], [total_spent, remaining],
                       color=["#e74c3c", "#2ecc71"], width=0.4, edgecolor="#1a1a2e")
        ax2.set_title(f"Spent vs Remaining\n(Limit: ₹{credit_limit:,.0f})",
                      color="white", fontsize=13)
    else:
        bars = ax2.bar(list(categories.keys()), list(categories.values()),
                       color=colors, edgecolor="#1a1a2e")
        ax2.set_title("Spending Breakdown", color="white", fontsize=13)
        ax2.tick_params(axis="x", rotation=30)

    for bar in bars:
        h = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2, h + total_spent * 0.01,
                 f"₹{h:,.0f}", ha="center", va="bottom", color="white", fontsize=10)

    ax2.set_facecolor("#16213e")
    ax2.tick_params(colors="white")
    ax2.spines[:].set_color("#444")
    ax2.yaxis.label.set_color("white")

    plt.suptitle(f"Monthly Spending Analysis — {datetime.now().strftime('%B %Y')}",
                 color="white", fontsize=15, fontweight="bold", y=1.01)
    plt.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.18, wspace=0.35)

    out_path = os.path.join(os.path.dirname(__file__), "spending_chart.png")
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return out_path


async def generate_insights(categories: dict[str, float], total_spent: float,
                            credit_limit: float = 0) -> str:
    """Generate Ollama insights for spending pattern."""
    import aiohttp

    remaining = credit_limit - total_spent if credit_limit > 0 else None
    breakdown = "\n".join(f"- {k}: ₹{v:,.0f}" for k, v in categories.items())

    prompt = f"""I am an Indian IT professional. Here is my monthly credit card spending:

Total spent: ₹{total_spent:,.0f}
{f'Credit limit: ₹{credit_limit:,.0f}' if credit_limit else ''}
{f'Remaining: ₹{remaining:,.0f}' if remaining else ''}

Breakdown:
{breakdown}

I am not a big spender. I want to:
1. Run the month smoothly without overspending
2. Know if any category is unusually high
3. Get 2-3 practical recommendations

Give me:
- A one-line overall assessment
- Top 2 concerns (if any)
- 2-3 actionable recommendations for the rest of the month
Keep it concise and practical. No generic advice."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": "qwen2.5:7b",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()
                return data["message"]["content"].strip()
    except Exception as e:
        return f"Could not generate insights: {e}"


def _print_ascii_chart(categories: dict[str, float], total_spent: float) -> None:
    """Print a simple ASCII bar chart to terminal for dry-run preview."""
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


def send_chart_whatsapp(chart_path: str, caption: str,
                        categories: dict[str, float] = None,
                        total_spent: float = 0) -> bool:
    """Upload chart image and send via WhatsApp Cloud API."""
    import os
    import requests
    from utils import get_secret, log

    if os.environ.get("WA_DRY_RUN", "true").lower() != "false":
        log("  [statement] DRY RUN — chart not sent.")
        print(f"  📁 Chart saved at: {chart_path}")
        if categories:
            _print_ascii_chart(categories, total_spent)
        print("─" * 60)
        print(caption)
        print("─" * 60)
        return True

    token = get_secret("email-agent-wa-token")
    phone_id = get_secret("email-agent-wa-phone-id")
    to = get_secret("email-agent-wa-to")

    if not all([token, phone_id, to]):
        log("  [statement] WhatsApp credentials missing")
        return False

    # Step 1: upload image to Meta
    with open(chart_path, "rb") as f:
        upload_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/media",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("chart.png", f, "image/png")},
            data={"messaging_product": "whatsapp"},
            timeout=30,
        )

    if not upload_resp.ok:
        log(f"  [statement] Image upload failed: {upload_resp.text}")
        return False

    media_id = upload_resp.json().get("id")

    # Step 2: send image message
    msg_resp = requests.post(
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

    if msg_resp.ok:
        log("  [statement] Chart sent via WhatsApp ✅")
        return True
    else:
        log(f"  [statement] Send failed: {msg_resp.text}")
        return False


async def analyze_statement(service, email: dict) -> str:
    """Full pipeline: download PDF → extract → chart → insights → send."""
    import asyncio
    import time
    from utils import log

    loop = asyncio.get_event_loop()

    log("  [statement] Downloading PDF attachment...")
    t0 = time.perf_counter()
    pdf_path = await loop.run_in_executor(None, download_pdf_attachment, service, email["id"])
    if not pdf_path:
        return "No PDF attachment found in statement email."
    log(f"  ⏱  PDF download: {time.perf_counter()-t0:.2f}s")

    log("  [statement] Extracting transactions...")
    t1 = time.perf_counter()
    transactions = await loop.run_in_executor(None, extract_transactions, pdf_path)
    os.unlink(pdf_path)
    log(f"  ⏱  Extracted {len(transactions)} transactions: {time.perf_counter()-t1:.2f}s")

    if not transactions:
        return "Could not extract transactions from PDF."

    categories = categorize_transactions(transactions)
    total_spent = sum(categories.values())

    log("  [statement] Generating chart + insights in parallel...")
    chart_path, insights = await asyncio.gather(
        loop.run_in_executor(None, partial(generate_chart, categories, total_spent)),
        generate_insights(categories, total_spent),
    )

    caption = f"📊 Monthly Spending: ₹{total_spent:,.0f}\n\n{insights[:800]}"
    await loop.run_in_executor(
        None, partial(send_chart_whatsapp, chart_path, caption, categories, total_spent)
    )

    return f"Statement analyzed. Total: ₹{total_spent:,.0f}. Chart + insights sent to WhatsApp."
