"""
Statement analyzer service — PDF → transactions → chart → Ollama insights → WhatsApp.
"""
import asyncio
import base64
import os
import re
import tempfile
from datetime import datetime
from functools import partial

from src.config import OLLAMA_URL, OLLAMA_MODEL, RETRY_ATTEMPTS, RETRY_DELAY

STATEMENT_SUBJECTS = [
    "credit card statement", "bank statement", "account statement",
    "e-statement", "monthly statement", "statement of account",
]
STATEMENT_DOMAINS = {
    "hdfcbank.com", "icicibank.com", "icici.bank.in", "sbi.co.in",
    "axisbank.com", "kotak.com", "yesbank.in", "indusind.com",
}
SPEND_CATEGORIES = {
    "Food & Dining":  ["swiggy", "zomato", "restaurant", "cafe", "food", "dining", "hotel", "pizza", "burger"],
    "Groceries":      ["bigbasket", "blinkit", "zepto", "grofers", "dmart", "supermarket", "grocery", "milk"],
    "Transport":      ["uber", "ola", "rapido", "metro", "petrol", "fuel", "irctc", "railway", "bus", "cab"],
    "Entertainment":  ["netflix", "hotstar", "prime", "spotify", "youtube", "bookmyshow", "cinema", "pvr"],
    "Utilities":      ["electricity", "water", "gas", "broadband", "internet", "airtel", "jio", "bsnl"],
    "Shopping":       ["amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "reliance"],
    "Health":         ["pharmacy", "medical", "hospital", "clinic", "apollo", "medplus", "1mg", "netmeds"],
    "Education":      ["udemy", "coursera", "byju", "unacademy", "school", "college", "fees"],
    "Investments":    ["zerodha", "groww", "mutual fund", "sip", "lic", "insurance", "premium"],
    "Other":          [],
}


def is_statement_email(email: dict) -> bool:
    subject = email.get("subject", "").lower()
    sender = email.get("from", "").lower()
    return (
        any(kw in subject for kw in STATEMENT_SUBJECTS) and
        any(d in sender for d in STATEMENT_DOMAINS)
    )


def download_pdf(service, message_id: str) -> str | None:
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

    att_id = find_pdf(msg.get("payload", {}).get("parts", []))
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
    import pdfplumber
    transactions = []
    amount_pattern = re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)')
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                line = line.strip()
                if not line:
                    continue
                amounts = amount_pattern.findall(line)
                if not amounts:
                    continue
                if any(h in line.lower() for h in ["date", "description", "amount", "balance", "total"]):
                    continue
                try:
                    amount = float(amounts[-1].replace(",", ""))
                except ValueError:
                    continue
                if amount >= 10:
                    transactions.append({"description": line[:80], "amount": amount})
    return transactions


def categorize(transactions: list[dict]) -> dict[str, float]:
    totals = {cat: 0.0 for cat in SPEND_CATEGORIES}
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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.patch.set_facecolor("#1a1a2e")

    ax1 = axes[0]
    ax1.set_facecolor("#1a1a2e")
    labels, values = list(categories.keys()), list(categories.values())
    colors = plt.cm.Set3.colors[:len(labels)]

    wedges, texts, autotexts = ax1.pie(
        values, labels=None, autopct="%1.0f%%", colors=colors, startangle=90,
        wedgeprops={"edgecolor": "#1a1a2e", "linewidth": 2}, pctdistance=0.75,
    )
    for t in autotexts:
        t.set_color("white"); t.set_fontsize(9)
    ax1.text(0, 0, f"₹{total_spent:,.0f}\nTotal Spent",
             ha="center", va="center", fontsize=11, color="white", fontweight="bold")
    ax1.legend(
        handles=[mpatches.Patch(color=colors[i], label=f"{labels[i]}: ₹{values[i]:,.0f}")
                 for i in range(len(labels))],
        loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=8,
        framealpha=0, labelcolor="white",
    )
    ax1.set_title("Spending by Category", color="white", fontsize=13, pad=15)

    ax2 = axes[1]
    ax2.set_facecolor("#16213e")
    if credit_limit > 0:
        remaining = max(0, credit_limit - total_spent)
        bars = ax2.bar(["Spent", "Remaining"], [total_spent, remaining],
                       color=["#e74c3c", "#2ecc71"], width=0.4, edgecolor="#1a1a2e")
        ax2.set_title(f"Spent vs Remaining\n(Limit: ₹{credit_limit:,.0f})", color="white", fontsize=13)
    else:
        bars = ax2.bar(labels, values, color=colors, edgecolor="#1a1a2e")
        ax2.set_title("Spending Breakdown", color="white", fontsize=13)
        ax2.tick_params(axis="x", rotation=30)

    for bar in bars:
        h = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2, h + total_spent * 0.01,
                 f"₹{h:,.0f}", ha="center", va="bottom", color="white", fontsize=10)
    ax2.tick_params(colors="white")
    ax2.spines[:].set_color("#444")

    plt.suptitle(f"Monthly Spending — {datetime.now().strftime('%B %Y')}",
                 color="white", fontsize=15, fontweight="bold", y=1.01)
    plt.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.18, wspace=0.35)

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "spending_chart.png")
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    return out_path


async def generate_insights(categories: dict[str, float], total_spent: float,
                            credit_limit: float = 0) -> str:
    import aiohttp
    remaining = credit_limit - total_spent if credit_limit > 0 else None
    breakdown = "\n".join(f"- {k}: ₹{v:,.0f}" for k, v in categories.items())
    prompt = f"""I am an Indian IT professional. Monthly credit card spending:
Total: ₹{total_spent:,.0f}{f', Limit: ₹{credit_limit:,.0f}' if credit_limit else ''}
{f'Remaining: ₹{remaining:,.0f}' if remaining else ''}
{breakdown}
Give: one-line assessment, top 2 concerns, 2-3 practical recommendations. Be concise."""

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    data = await resp.json()
                    return data["message"]["content"].strip()
        except Exception as e:
            if attempt == RETRY_ATTEMPTS:
                return f"Could not generate insights: {e}"
            await asyncio.sleep(RETRY_DELAY)
    return ""


async def analyze(service, email: dict) -> str:
    """Full pipeline: PDF → extract → chart → insights → send."""
    import time
    from utils import log
    from src.tools.whatsapp import send_image

    loop = asyncio.get_event_loop()

    log("  [statement] Downloading PDF...")
    t0 = time.perf_counter()
    pdf_path = await loop.run_in_executor(None, download_pdf, service, email["id"])
    if not pdf_path:
        return "No PDF attachment found."
    log(f"  ⏱  PDF download: {time.perf_counter()-t0:.2f}s")

    log("  [statement] Extracting transactions...")
    transactions = await loop.run_in_executor(None, extract_transactions, pdf_path)
    os.unlink(pdf_path)
    log(f"  [statement] {len(transactions)} transactions extracted")

    if not transactions:
        return "Could not extract transactions from PDF."

    categories = categorize(transactions)
    total_spent = sum(categories.values())

    log("  [statement] Generating chart + insights in parallel...")
    chart_path, insights = await asyncio.gather(
        loop.run_in_executor(None, partial(generate_chart, categories, total_spent)),
        generate_insights(categories, total_spent),
    )

    caption = f"📊 Monthly Spending: ₹{total_spent:,.0f}\n\n{insights[:800]}"
    await loop.run_in_executor(
        None, partial(send_image, chart_path, caption, categories, total_spent)
    )
    return f"Statement analyzed. Total: ₹{total_spent:,.0f}. Chart + insights sent to WhatsApp."
