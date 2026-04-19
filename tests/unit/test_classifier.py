"""Unit tests for src/services/classifier.py"""
from src.services.classifier import (
    is_blocked, is_tech_blog, is_large_debit, is_keyword_match, format_message,
)


def email(subject="", sender="", snippet=""):
    return {"subject": subject, "from": sender, "snippet": snippet}


def test_blocked_by_keyword_unsubscribe():
    assert is_blocked(email(snippet="click here to unsubscribe from this list"))

def test_blocked_by_keyword_otp():
    assert is_blocked(email(subject="Your OTP is 482910 do not share"))

def test_blocked_by_sender():
    assert is_blocked(email(sender="deals@somestore.com"))

def test_blocked_promo():
    assert is_blocked(email(subject="50% off sale ends tonight! Shop now"))

def test_not_blocked_bank_alert():
    assert not is_blocked(email(subject="Transaction alert", sender="credit_cards@icicibank.com"))

def test_tech_blog_bytebytego():
    assert is_tech_blog(email(sender="bytebytego@substack.com"))

def test_tech_blog_medium():
    assert is_tech_blog(email(sender="noreply@medium.com"))

def test_not_tech_blog_random():
    assert not is_tech_blog(email(sender="hr@somecompany.com"))

def test_large_debit_detected():
    assert is_large_debit(email(sender="alerts@hdfcbank.com", snippet="Rs. 12,500 debited from your HDFC account"))

def test_large_debit_below_threshold():
    assert not is_large_debit(email(sender="alerts@hdfcbank.com", snippet="Rs. 499 debited from your account"))

def test_large_debit_untrusted_sender():
    assert not is_large_debit(email(sender="alerts@randombank.com", snippet="Rs. 15,000 debited"))

def test_large_debit_no_debit_word():
    assert not is_large_debit(email(sender="alerts@icicibank.com", snippet="Your account balance is Rs. 50,000"))

def test_keyword_match_trusted_domain():
    assert is_keyword_match(email(sender="noreply@zerodha.com"))

def test_keyword_match_subject_keyword():
    assert is_keyword_match(email(subject="Your Form 16 is ready for download"))

def test_keyword_match_itr():
    assert is_keyword_match(email(subject="ITR filed successfully for AY 2024-25"))

def test_keyword_match_job():
    assert is_keyword_match(email(subject="Interview scheduled for Senior Engineer role"))

def test_no_match_random():
    assert not is_keyword_match(email(subject="Your Amazon order has shipped", sender="ship@amazon.com"))

def test_format_groups_by_category():
    items = [
        {"subject": "ICICI Alert", "from": "icici", "categories": ["Bank / Finance"], "summary": "₹500 debited"},
        {"subject": "ByteByteGo", "from": "bb", "categories": ["Tech Blog / Article to Read"], "summary": "JVM internals"},
        {"subject": "HDFC Alert", "from": "hdfc", "categories": ["Bank / Finance"], "summary": "₹200 debited"},
    ]
    msg = format_message(items)
    assert "Bank / Finance" in msg
    assert "Tech Blog / Article to Read" in msg

def test_format_empty_returns_empty():
    assert format_message([]) == ""

def test_format_header_present():
    items = [{"subject": "Test", "from": "x", "categories": ["Job / Recruitment"], "summary": "Java role"}]
    assert "📧 *Daily Email Summary*" in format_message(items)
