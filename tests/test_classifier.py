"""Unit tests for classifier.py — keyword filter pipeline. No Ollama, no network."""
from classifier import (
    _is_blocked, _is_tech_blog, _is_large_debit, _keyword_match, _format_message,
)


def email(subject="", sender="", snippet=""):
    return {"subject": subject, "from": sender, "snippet": snippet}


# ── _is_blocked ──────────────────────────────────────────────

def test_blocked_by_keyword_unsubscribe():
    assert _is_blocked(email(snippet="click here to unsubscribe from this list"))

def test_blocked_by_keyword_otp():
    assert _is_blocked(email(subject="Your OTP is 482910 do not share"))

def test_blocked_by_sender():
    assert _is_blocked(email(sender="deals@somestore.com"))

def test_blocked_promo():
    assert _is_blocked(email(subject="50% off sale ends tonight! Shop now"))

def test_not_blocked_bank_alert():
    assert not _is_blocked(email(subject="Transaction alert", sender="credit_cards@icicibank.com"))


# ── _is_tech_blog ────────────────────────────────────────────

def test_tech_blog_bytebytego():
    assert _is_tech_blog(email(sender="bytebytego@substack.com"))

def test_tech_blog_medium():
    assert _is_tech_blog(email(sender="noreply@medium.com"))

def test_not_tech_blog_random():
    assert not _is_tech_blog(email(sender="hr@somecompany.com"))


# ── _is_large_debit ──────────────────────────────────────────

def test_large_debit_detected():
    assert _is_large_debit(email(
        sender="alerts@hdfcbank.com",
        snippet="Rs. 12,500 debited from your HDFC account"
    ))

def test_large_debit_below_threshold():
    assert not _is_large_debit(email(
        sender="alerts@hdfcbank.com",
        snippet="Rs. 499 debited from your account"
    ))

def test_large_debit_untrusted_sender():
    assert not _is_large_debit(email(
        sender="alerts@randombank.com",
        snippet="Rs. 15,000 debited"
    ))

def test_large_debit_no_debit_word():
    assert not _is_large_debit(email(
        sender="alerts@icicibank.com",
        snippet="Your account balance is Rs. 50,000"
    ))


# ── _keyword_match ───────────────────────────────────────────

def test_keyword_match_trusted_domain():
    assert _keyword_match(email(sender="noreply@zerodha.com"))

def test_keyword_match_subject_keyword():
    assert _keyword_match(email(subject="Your Form 16 is ready for download"))

def test_keyword_match_itr():
    assert _keyword_match(email(subject="ITR filed successfully for AY 2024-25"))

def test_keyword_match_job():
    assert _keyword_match(email(subject="Interview scheduled for Senior Engineer role"))

def test_no_match_random():
    assert not _keyword_match(email(subject="Your Amazon order has shipped", sender="ship@amazon.com"))


# ── _format_message ──────────────────────────────────────────

def test_format_groups_by_category():
    items = [
        {"subject": "ICICI Alert", "from": "icici", "categories": ["Bank / Finance"], "summary": "₹500 debited"},
        {"subject": "ByteByteGo", "from": "bb", "categories": ["Tech Blog / Article to Read"], "summary": "JVM internals"},
        {"subject": "HDFC Alert", "from": "hdfc", "categories": ["Bank / Finance"], "summary": "₹200 debited"},
    ]
    msg = _format_message(items)
    assert "Bank / Finance" in msg
    assert "Tech Blog / Article to Read" in msg
    assert "ICICI Alert" in msg
    assert "ByteByteGo" in msg
    # Bank section should have 2 items
    assert msg.count("₹") == 2

def test_format_empty_returns_empty():
    # _format_message always returns the header; empty list means no sections
    msg = _format_message([])
    assert "━━━" not in msg  # no category sections

def test_format_header_present():
    items = [{"subject": "Test", "from": "x", "categories": ["Job / Recruitment"], "summary": "Java role"}]
    assert "📧 *Daily Email Summary*" in _format_message(items)
