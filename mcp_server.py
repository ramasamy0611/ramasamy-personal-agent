#!/usr/bin/env python3
"""
Local MCP server — exposes Gmail, classifier, and WhatsApp as MCP tools.
Runs over stdio. Add new tools here to extend the agent's capabilities.
"""

from mcp.server.fastmcp import FastMCP
from gmail_fetcher import fetch_recent_emails, _get_gmail_service
from classifier import classify_emails, CATEGORIES
from whatsapp_notifier import send_whatsapp_summary
from statement_analyzer import is_statement_email, analyze_statement

mcp = FastMCP("email-agent")


@mcp.tool()
def gmail_fetch(hours: int = 24) -> str:
    """
    Fetch unread emails from Gmail for the last N hours.
    Read-only — never deletes or modifies emails.
    Returns a JSON string list of {id, subject, from, snippet, body}.
    """
    import json
    return json.dumps(fetch_recent_emails(hours=hours))


@mcp.tool()
def email_classify(emails: str) -> str:
    """
    Classify emails (JSON string list) using the local Ollama LLM.
    Returns a formatted summary string of important emails, or empty string if none match.
    """
    import json
    import asyncio
    email_list = json.loads(emails) if isinstance(emails, str) else emails
    return asyncio.run(classify_emails(email_list))


@mcp.tool()
def whatsapp_notify(message: str) -> bool:
    """
    Send a WhatsApp message via Meta Cloud API.
    Credentials are read from macOS Keychain — never from files.
    Returns True on success.
    """
    return send_whatsapp_summary(message)


@mcp.tool()
def list_categories() -> list[str]:
    """Return the list of email categories this agent watches."""
    return CATEGORIES


@mcp.tool()
def statement_analyze(emails_json: str) -> str:
    """
    Detect monthly bank statement email, extract PDF, generate spending chart
    and Ollama insights, send chart + insights to WhatsApp.
    Pass the same emails JSON from gmail_fetch.
    """
    import json
    import asyncio
    emails = json.loads(emails_json) if isinstance(emails_json, str) else emails_json
    statement = next((e for e in emails if is_statement_email(e)), None)
    if not statement:
        return "No monthly statement email found."
    service = _get_gmail_service()
    return asyncio.run(analyze_statement(service, statement))


if __name__ == "__main__":
    mcp.run(transport="stdio")
