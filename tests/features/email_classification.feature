Feature: Email Classification
  As an Indian IT professional
  I want important emails classified by category
  So that I receive only relevant WhatsApp notifications

  Scenario: Block promotional emails
    Given an email from "deals@somestore.com" with subject "50% off sale ends tonight"
    When the classifier processes it
    Then the email is blocked

  Scenario: Block OTP emails
    Given an email with subject "Your OTP is 482910 do not share"
    When the classifier processes it
    Then the email is blocked

  Scenario: Pass bank transaction alert
    Given an email from "credit_cards@icicibank.com" with subject "Transaction alert for your ICICI Bank Credit Card"
    When the classifier processes it
    Then the email passes the keyword filter

  Scenario: Pass tech blog from ByteByteGo
    Given an email from "bytebytego@substack.com" with subject "EP211: How the JVM Works"
    When the classifier processes it
    Then the email passes the keyword filter

  Scenario: Flag large debit above threshold
    Given an email from "alerts@hdfcbank.com" with snippet "Rs. 12,500 debited from your account"
    When the classifier processes it
    Then the email is flagged as a large debit alert

  Scenario: Skip irrelevant emails
    Given an email from "noreply@netflix.com" with subject "What did you think of With Love?"
    When the classifier processes it
    Then the email is skipped

  Scenario: Group results by category
    Given 3 important emails across 2 categories
    When the formatter groups them
    Then the output contains section headers per category
