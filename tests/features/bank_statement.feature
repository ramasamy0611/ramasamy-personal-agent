Feature: Bank Statement Analysis
  As an Indian IT professional
  I want my monthly bank statement analyzed automatically
  So that I receive spending insights and a chart on WhatsApp

  Scenario: Detect ICICI bank statement email
    Given an email from "statements@icicibank.com" with subject "Your ICICI Bank Credit Card Statement"
    When the statement detector checks it
    Then the email is identified as a monthly statement

  Scenario: Ignore transaction alert as statement
    Given an email from "credit_cards@icicibank.com" with subject "Transaction alert for your ICICI Bank Credit Card"
    When the statement detector checks it
    Then the email is not identified as a monthly statement

  Scenario: Categorize food spending
    Given a transaction "SWIGGY ORDER 12345" for Rs 450
    When transactions are categorized
    Then it falls under "Food & Dining"

  Scenario: Categorize unknown merchant as Other
    Given a transaction "XYZUNKNOWN MERCHANT" for Rs 999
    When transactions are categorized
    Then it falls under "Other"

  Scenario: Generate spending chart
    Given categorized spending data
    When the chart is generated
    Then a PNG file is created at spending_chart.png
