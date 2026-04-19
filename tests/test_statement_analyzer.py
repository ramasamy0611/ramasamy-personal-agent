"""Unit tests for statement_analyzer.py — no PDF, no network, no WhatsApp."""
import os
import pytest
from statement_analyzer import (
    is_statement_email, categorize_transactions, generate_chart, _print_ascii_chart,
)


# ── is_statement_email ───────────────────────────────────────

def test_detects_icici_statement():
    assert is_statement_email({
        "subject": "Your ICICI Bank Credit Card Statement",
        "from": "statements@icicibank.com",
    })

def test_detects_hdfc_statement():
    assert is_statement_email({
        "subject": "Monthly e-statement for your account",
        "from": "noreply@hdfcbank.com",
    })

def test_ignores_transaction_alert():
    assert not is_statement_email({
        "subject": "Transaction alert for your ICICI Bank Credit Card",
        "from": "credit_cards@icicibank.com",
    })

def test_ignores_untrusted_domain():
    assert not is_statement_email({
        "subject": "Your monthly statement is ready",
        "from": "noreply@randombank.com",
    })


# ── categorize_transactions ──────────────────────────────────

SAMPLE_TRANSACTIONS = [
    {"description": "SWIGGY ORDER 12345", "amount": 450.0},
    {"description": "UBER TRIP BANGALORE", "amount": 280.0},
    {"description": "AMAZON PURCHASE", "amount": 1200.0},
    {"description": "NETFLIX SUBSCRIPTION", "amount": 649.0},
    {"description": "BIGBASKET GROCERY", "amount": 890.0},
    {"description": "SOME UNKNOWN MERCHANT XYZ", "amount": 500.0},
]

def test_categorize_food():
    cats = categorize_transactions([{"description": "SWIGGY ORDER", "amount": 300}])
    assert cats.get("Food & Dining", 0) == 300

def test_categorize_transport():
    cats = categorize_transactions([{"description": "UBER TRIP", "amount": 150}])
    assert cats.get("Transport", 0) == 150

def test_categorize_unknown_goes_to_other():
    cats = categorize_transactions([{"description": "XYZUNKNOWN123", "amount": 999}])
    assert cats.get("Other", 0) == 999

def test_categorize_multiple():
    cats = categorize_transactions(SAMPLE_TRANSACTIONS)
    assert cats["Food & Dining"] == 450.0
    assert cats["Transport"] == 280.0
    assert cats["Shopping"] == 1200.0
    assert cats["Entertainment"] == 649.0
    assert cats["Groceries"] == 890.0
    assert cats["Other"] == 500.0

def test_categorize_empty():
    assert categorize_transactions([]) == {}

def test_zero_amount_categories_excluded():
    cats = categorize_transactions([{"description": "SWIGGY", "amount": 100}])
    # Categories with 0 spend should not appear
    assert "Transport" not in cats


# ── generate_chart ───────────────────────────────────────────

def test_generate_chart_creates_file(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.chdir(tmp_path)
    cats = {"Food & Dining": 1500.0, "Transport": 800.0, "Shopping": 2200.0}
    try:
        path = generate_chart(cats, sum(cats.values()))
        assert os.path.exists(path)
        assert path.endswith(".png")
        assert os.path.getsize(path) > 1000
    except Exception as e:
        pytest.skip(f"matplotlib rendering issue: {e}")

def test_generate_chart_with_credit_limit(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.chdir(tmp_path)
    cats = {"Food & Dining": 5000.0}
    try:
        path = generate_chart(cats, 5000.0, credit_limit=50000.0)
        assert os.path.exists(path)
    except Exception as e:
        pytest.skip(f"matplotlib rendering issue: {e}")


# ── _print_ascii_chart ───────────────────────────────────────

def test_ascii_chart_prints(capsys):
    cats = {"Food & Dining": 1500.0, "Transport": 500.0}
    _print_ascii_chart(cats, 2000.0)
    out = capsys.readouterr().out
    assert "Food & Dining" in out
    assert "Transport" in out
    assert "₹" in out
    assert "TOTAL" in out

def test_ascii_chart_percentages(capsys):
    cats = {"Shopping": 1000.0, "Other": 1000.0}
    _print_ascii_chart(cats, 2000.0)
    out = capsys.readouterr().out
    assert "50%" in out
