#!/usr/bin/env python3
"""
MCP host agent — orchestrates fetch → classify → notify.
Usage:
  python agent.py                  # dry run, last 24h
  python agent.py --days 7         # last 7 days
  python agent.py --send           # actually send to WhatsApp
  python agent.py --days 60 --send # 2 months, send
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.services.classifier import classify_emails
from src.services.statement import is_statement_email, analyze
from src.tools.gmail import get_service
from src.config import FETCH_HOURS
from utils import log, timer
from reminder import record_run

SERVER_CMD = [sys.executable, "src/mcp_server.py"]


async def run(session: ClientSession) -> None:
    log("=" * 50)
    log("AGENT START")
    log("=" * 50)

    hours = int(os.environ.get("FETCH_HOURS", FETCH_HOURS))

    log(f"[1/3] gmail_fetch — last {hours // 24} day(s)")
    with timer("gmail_fetch"):
        result = await session.call_tool("gmail_fetch", {"hours": hours})
        emails = json.loads(result.content[0].text) if result.content else []
    log(f"[1/3] gmail_fetch — {len(emails)} emails fetched")

    if not emails:
        log("No unread emails — skipping.")
        record_run()
        return

    log("[2/3] classify + statement")
    with timer("classify + statement"):
        statement_emails = [e for e in emails if is_statement_email(e)]
        tasks = [classify_emails(emails)]

        if statement_emails:
            print("=" * 60)
            print(f"  📄 MONTHLY STATEMENT: '{statement_emails[0]['subject']}'")
            print(f"     From: {statement_emails[0]['from']}")
            print("=" * 60)
            loop = asyncio.get_event_loop()
            service = await loop.run_in_executor(None, get_service)
            tasks.append(analyze(service, statement_emails[0]))
        else:
            log("  No monthly statement found.")

        results = await asyncio.gather(*tasks)

    summary = results[0]

    if len(results) > 1:
        print(f"\n  [statement] {results[1]}")
        chart = os.path.join(os.path.dirname(__file__), "spending_chart.png")
        if os.path.exists(chart):
            print(f"  📁 Chart: {chart}")
            print(f'     Run: open "{chart}"')

    log(f"[2/3] classify — {'matches found' if summary else 'no matches'}")

    if not summary:
        log("No important emails — skipping WhatsApp.")
        record_run()
        return

    dry_run = os.environ.get("WA_DRY_RUN", "true").lower() != "false"
    label = "DRY RUN — not sent" if dry_run else "Sending to WhatsApp"
    print(f"\n  [whatsapp] {label}:")
    print("─" * 60)
    print(summary)
    print("─" * 60)

    log("[3/3] whatsapp_notify")
    with timer("whatsapp_notify"):
        await session.call_tool("whatsapp_notify", {"message": summary})
    log("[3/3] whatsapp_notify — done")

    record_run()
    log("=" * 50)
    log("AGENT DONE")
    log("=" * 50)


async def main():
    server_params = StdioServerParameters(
        command=SERVER_CMD[0], args=SERVER_CMD[1:], env={**os.environ}
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            log(f"Tools: {[t.name for t in tools.tools]}")
            await run(session)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Personal email agent")
    parser.add_argument("--days", type=int, help="Days of history to fetch (default: 1)")
    parser.add_argument("--send", action="store_true", help="Actually send to WhatsApp")
    args = parser.parse_args()
    if args.days:
        os.environ["FETCH_HOURS"] = str(args.days * 24)
    if args.send:
        os.environ["WA_DRY_RUN"] = "false"
    asyncio.run(main())
