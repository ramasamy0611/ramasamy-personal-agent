#!/usr/bin/env python3
"""MCP server — exposes Gmail, classifier, WhatsApp, statement as tools."""
import json
import asyncio

from mcp.server.fastmcp import FastMCP

from src.tools.gmail import fetch_recent_emails, get_service
from src.services.classifier import classify_emails, CATEGORIES
from src.tools.whatsapp import send_message
from src.services.statement import is_statement_email, analyze

mcp = FastMCP("ramasamy-personal-agent")


@mcp.tool()
def gmail_fetch(hours: int = 24) -> str:
    """Fetch unread emails from Gmail. Read-only."""
    return json.dumps(fetch_recent_emails(hours=hours))


@mcp.tool()
def email_classify(emails: str) -> str:
    """Classify emails using local Ollama. Returns formatted summary."""
    email_list = json.loads(emails) if isinstance(emails, str) else emails
    return asyncio.run(classify_emails(email_list))


@mcp.tool()
def whatsapp_notify(message: str) -> bool:
    """Send a WhatsApp message via Meta Cloud API."""
    return send_message(message)


@mcp.tool()
def list_categories() -> list[str]:
    """Return the list of email categories watched."""
    return CATEGORIES


@mcp.tool()
def statement_analyze(emails_json: str) -> str:
    """Detect monthly bank statement, extract PDF, generate chart + insights."""
    emails = json.loads(emails_json) if isinstance(emails_json, str) else emails_json
    statement = next((e for e in emails if is_statement_email(e)), None)
    if not statement:
        return "No monthly statement email found."
    service = get_service()
    return asyncio.run(analyze(service, statement))


if __name__ == "__main__":
    mcp.run(transport="stdio")
