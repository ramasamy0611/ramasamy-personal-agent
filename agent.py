#!/usr/bin/env python3
"""
General-purpose MCP host agent.
Connects to the local MCP server, discovers available tools, and orchestrates tasks.
Add new tools to mcp_server.py — this agent picks them up automatically.
"""

import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from classifier import classify_emails
from statement_analyzer import is_statement_email, analyze_statement
from gmail_fetcher import _get_gmail_service
from reminder import record_run
from utils import log, timer

SERVER_CMD = [
    sys.executable,  # same venv python
    "mcp_server.py",
]


async def run_email_task(session: ClientSession) -> None:
    """Default daily task: fetch → classify → notify."""
    log("=" * 50)
    log("AGENT START")
    log("=" * 50)

    log("[1/3] TOOL: gmail_fetch — START")
    with timer("gmail_fetch"):
        fetch_result = await session.call_tool("gmail_fetch", {"hours": 24})
        emails = json.loads(fetch_result.content[0].text) if fetch_result.content else []
    log(f"[1/3] TOOL: gmail_fetch — END ({len(emails)} emails fetched)")

    if not emails:
        log("No unread emails in last 24h — skipping notification.")
        record_run()
        log("AGENT DONE")
        return

    log("[2/3] TOOL: email_classify + statement_analyze — START")
    with timer("classify + statement"):
        statement_emails = [e for e in emails if is_statement_email(e)]
        tasks = [classify_emails(emails)]
        if statement_emails:
            print("=" * 60)
            print(f"  📄 MONTHLY STATEMENT DETECTED: '{statement_emails[0]['subject']}'")
            print(f"     From: {statement_emails[0]['from']}")
            print("     → Downloading PDF, extracting transactions, generating chart...")
            print("=" * 60)
            loop = asyncio.get_event_loop()
            service = await loop.run_in_executor(None, _get_gmail_service)
            tasks.append(analyze_statement(service, statement_emails[0]))
        else:
            log("  No monthly statement email found.")
        results = await asyncio.gather(*tasks)

    summary = results[0]
    if len(results) > 1:
        import os as _os
        chart = _os.path.join(_os.path.dirname(__file__), "spending_chart.png")
        print(f"\n  [statement] {results[1]}")
        if _os.path.exists(chart):
            print(f"  📁 Chart saved at: {chart}")
            print(f"     Run: open \"{chart}\"  to preview")
    log(f"[2/3] TOOL: email_classify — END ({'matches found' if summary else 'no matches'})")

    if not summary:
        log("No important emails — skipping WhatsApp notification.")
        record_run()
        log("=" * 50)
        log("AGENT DONE")
        log("=" * 50)
        return

    message = summary
    log("[3/3] TOOL: whatsapp_notify — START")
    # Always print what will be sent — MCP subprocess stdout isn't visible
    import os
    dry_run = os.environ.get("WA_DRY_RUN", "true").lower() != "false"
    if dry_run:
        print("  [whatsapp] DRY RUN — message not sent. This is what would go to WhatsApp:")
    else:
        print("  [whatsapp] Sending to WhatsApp:")
    print("─" * 60)
    print(message)
    print("─" * 60)
    with timer("whatsapp_notify"):
        await session.call_tool("whatsapp_notify", {"message": message})
    log("[3/3] TOOL: whatsapp_notify — END")

    record_run()
    log("=" * 50)
    log("AGENT DONE")
    log("=" * 50)


async def main():
    import os
    server_params = StdioServerParameters(
        command=SERVER_CMD[0],
        args=SERVER_CMD[1:],
        env={**os.environ},  # inherit all env vars including WA_DRY_RUN
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover available tools (makes this agent general-purpose)
            tools = await session.list_tools()
            log(f"Available tools: {[t.name for t in tools.tools]}")

            await run_email_task(session)


if __name__ == "__main__":
    import argparse
    import os
    parser = argparse.ArgumentParser(description="Email agent")
    parser.add_argument("--days", type=int, default=None,
                        help="Days of email history to fetch (default: 1)")
    parser.add_argument("--send", action="store_true",
                        help="Actually send to WhatsApp (default: dry run)")
    args = parser.parse_args()
    if args.days:
        os.environ["FETCH_HOURS"] = str(args.days * 24)
    if args.send:
        os.environ["WA_DRY_RUN"] = "false"
    asyncio.run(main())
