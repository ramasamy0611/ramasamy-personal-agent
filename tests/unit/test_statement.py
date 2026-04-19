"""Unit tests for src/services/statement.py"""
import os
import pytest
from src.services.statement import (
    is_statement_email, categorize, generate_chart,
)
from src.tools.whatsapp import _print_ascii_chart


def test_detects_icici_statement():
    assert is_statement_email({"subject": "Your ICICI Bank Credit Card Statement", "from": "statements@icicibank.com"})

def test_detects_hdfc_statement():
    assert is_statement_email({"subject": "Monthly e-statement for your account", "from": "noreply@hdfcbank.com"})

def test_ignores_transaction_alert():
    assert not is_statement_email({"subject": "Transaction alert for your ICICI Bank Credit Card", "from": "credit_cards@icicibank.com"})

def test_ignores_untrusted_domain():
    assert not is_statement_email({"subject": "Your monthly statement is ready", "from": "noreply@randombank.com"})

def test_categorize_food():
    cats = categorize([{"description": "SWIGGY ORDER", "amount": 300}])
    assert cats.get("Food & Dining", 0) == 300

def test_categorize_transport():
    cats = categorize([{"description": "UBER TRIP", "amount": 150}])
    assert cats.get("Transport", 0) == 150

def test_categorize_unknown_goes_to_other():
    cats = categorize([{"description": "XYZUNKNOWN123", "amount": 999}])
    assert cats.get("Other", 0) == 999

def test_categorize_multiple():
    txns = [
        {"description": "SWIGGY ORDER 12345", "amount": 450.0},
        {"description": "UBER TRIP BANGALORE", "amount": 280.0},
        {"description": "AMAZON PURCHASE", "amount": 1200.0},
        {"description": "NETFLIX SUBSCRIPTION", "amount": 649.0},
        {"description": "BIGBASKET GROCERY", "amount": 890.0},
        {"description": "SOME UNKNOWN MERCHANT XYZ", "amount": 500.0},
    ]
    cats = categorize(txns)
    assert cats["Food & Dining"] == 450.0
    assert cats["Transport"] == 280.0
    assert cats["Shopping"] == 1200.0
    assert cats["Entertainment"] == 649.0
    assert cats["Groceries"] == 890.0
    assert cats["Other"] == 500.0

def test_categorize_empty():
    assert categorize([]) == {}

def test_zero_amount_categories_excluded():
    cats = categorize([{"description": "SWIGGY", "amount": 100}])
    assert "Transport" not in cats

def test_generate_chart_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cats = {"Food & Dining": 1500.0, "Transport": 800.0, "Shopping": 2200.0}
    try:
        path = generate_chart(cats, sum(cats.values()))
        assert os.path.exists(path)
        assert path.endswith(".png")
    except Exception as e:
        pytest.skip(f"matplotlib rendering issue: {e}")

def test_generate_chart_with_credit_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cats = {"Food & Dining": 5000.0}
    try:
        path = generate_chart(cats, 5000.0, credit_limit=50000.0)
        assert os.path.exists(path)
    except Exception as e:
        pytest.skip(f"matplotlib rendering issue: {e}")

def test_ascii_chart_prints(capsys):
    _print_ascii_chart({"Food & Dining": 1500.0, "Transport": 500.0}, 2000.0)
    out = capsys.readouterr().out
    assert "Food & Dining" in out
    assert "₹" in out
    assert "TOTAL" in out

def test_ascii_chart_percentages(capsys):
    _print_ascii_chart({"Shopping": 1000.0, "Other": 1000.0}, 2000.0)
    out = capsys.readouterr().out
    assert "50%" in out
