# Email Agent — Project Architecture

> Local agentic AI that reads Gmail daily, classifies important emails using Ollama, sends a WhatsApp summary, and analyzes monthly bank statements with spending charts.

---

## Goals

- Read Gmail daily — **read-only**, never delete or modify
- Filter noise (promotions, OTPs, ads) before any AI call
- Classify important emails by category using **local Ollama** — no cloud AI
- Send grouped WhatsApp summary via **Meta Cloud API**
- Detect monthly bank statement PDFs → extract transactions → generate dark-theme spending chart → send chart + Ollama insights to WhatsApp
- All secrets in **macOS Keychain** — never in files or env vars
- Runs at **8 AM daily** via launchd, unattended

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        macOS (local)                        │
│                                                             │
│  ┌──────────────┐  stdio  ┌──────────────────────────────┐  │
│  │   agent.py   │◄───────►│       mcp_server.py          │  │
│  │  (MCP host)  │  MCP    │  (FastMCP server)            │  │
│  └──────┬───────┘         │  tools:                      │  │
│         │                 │  • gmail_fetch               │  │
│         │ direct import   │  • email_classify            │  │
│         │ (performance)   │  • whatsapp_notify           │  │
│         ▼                 │  • list_categories           │  │
│  ┌──────────────┐         │  • statement_analyze         │  │
│  │ classifier.py│         └──────────────────────────────┘  │
│  │ (async       │                                            │
│  │  parallel    │         ┌──────────────────────────────┐  │
│  │  Ollama)     │         │  External Services           │  │
│  └──────────────┘         │                              │  │
│                           │  Gmail API (read-only OAuth) │  │
│  ┌──────────────┐         │  Ollama :11434 (local LLM)   │  │
│  │statement_    │         │  Meta WhatsApp Cloud API     │  │
│  │analyzer.py   │         └──────────────────────────────┘  │
│  └──────────────┘                                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  utils.py    │  │ reminder.py  │  │  launchd plist   │  │
│  │  (Keychain,  │  │  (safety net │  │  (8 AM daily)    │  │
│  │   log, timer)│  │   reminder)  │  │                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

| Module | Role |
|---|---|
| `agent.py` | MCP host. Orchestrates fetch → classify+statement → notify. Parallel execution via `asyncio.gather`. |
| `mcp_server.py` | FastMCP server. Exposes 5 tools over stdio. Thin wrappers — logic lives in modules. |
| `gmail_fetcher.py` | Gmail OAuth2 (read-only). Batch API for metadata. Server-side query filter. |
| `classifier.py` | Keyword pre-filter pipeline + async parallel Ollama calls. Groups results by category. |
| `statement_analyzer.py` | PDF download → pdfplumber extraction → category mapping → matplotlib chart → Ollama insights → WhatsApp image. |
| `whatsapp_notifier.py` | Meta Cloud API sender. `DRY_RUN` env flag for safe testing. |
| `utils.py` | macOS Keychain read/write, `log()`, `timer()` context manager. |
| `reminder.py` | Tracks last run date. Sends WhatsApp reminder if agent hasn't run today. |

---

## Daily Email Flow — Sequence Diagram

```
launchd (8 AM)
    │
    ▼
agent.py::main()
    │
    ├─── MCP stdio ──► mcp_server.py starts
    │
    ├─[1]─ call_tool("gmail_fetch", {hours: 24})
    │           │
    │           ▼
    │       gmail_fetcher.fetch_recent_emails()
    │           │  Gmail query (server-side filter):
    │           │  is:unread after:DATE
    │           │  -category:promotions -category:social
    │           │  -category:updates -from:noreply
    │           │
    │           ├── list messages (1 HTTP call)
    │           └── batch metadata fetch (1 HTTP call, all emails)
    │                   └── returns [{id, subject, from, snippet}]
    │
    │  (if 0 emails → exit early, no WhatsApp)
    │
    ├─[2]─ asyncio.gather(
    │         classify_emails(emails),          ← direct import, not MCP
    │         analyze_statement(service, email) ← only if statement email found
    │       )
    │
    │   classify_emails():
    │       │
    │       ├── Step 1: keyword pre-filter (instant, no I/O)
    │       │       ├── _is_blocked()     → skip promotions/OTPs
    │       │       ├── _is_tech_blog()   → pass tech newsletters
    │       │       ├── _is_large_debit() → pass bank debits > ₹5000
    │       │       └── _keyword_match()  → trusted domain OR subject keyword
    │       │
    │       └── Step 2: async parallel Ollama (candidates only)
    │               │
    │               ├── aiohttp.ClientSession
    │               ├── asyncio.gather(*[ask_ollama(e) for e in candidates])
    │               │       └── POST http://127.0.0.1:11434/api/chat
    │               │           model: qwen2.5:7b
    │               │           → {categories: [...], summary: "..."}
    │               │
    │               └── _format_message() → grouped by category
    │                       ━━━ Bank / Finance ━━━
    │                         1. Subject line
    │                            ₹4,925 debited from ICICI
    │
    ├─[3]─ call_tool("whatsapp_notify", {message})
    │           │  (skipped if no important emails)
    │           │  (DRY_RUN=true → prints to stdout)
    │           └── Meta Cloud API POST /messages
    │
    └── record_run() → writes .last_run date file
```

---

## Bank Statement Flow — Sequence Diagram

```
agent.py detects statement email
    │
    ├── is_statement_email(email)
    │       subject contains: "credit card statement" / "e-statement" / etc.
    │       sender domain in: icicibank.com / hdfcbank.com / etc.
    │
    └── asyncio.gather(
            classify_emails(all_emails),
            analyze_statement(service, statement_email)  ← parallel
        )

analyze_statement():
    │
    ├─[executor]─ download_pdf_attachment(service, message_id)
    │                   Gmail API: get full message → find PDF part
    │                   → base64 decode → write to tempfile
    │
    ├─[executor]─ extract_transactions(pdf_path)
    │                   pdfplumber: page by page text extraction
    │                   regex: find lines with ₹ amounts
    │                   → [{description, amount}]
    │                   tempfile deleted immediately after
    │
    ├── categorize_transactions(transactions)
    │       keyword match per transaction description
    │       → {Food: ₹X, Transport: ₹Y, Shopping: ₹Z, ...}
    │
    ├── asyncio.gather(                          ← parallel
    │       run_in_executor(generate_chart),     ← matplotlib (CPU)
    │       generate_insights(categories)        ← Ollama async
    │   )
    │
    │   generate_chart():
    │       matplotlib dark theme (#1a1a2e)
    │       Left: donut chart by category
    │       Right: bar chart (spent vs remaining OR breakdown)
    │       → spending_chart.png
    │
    │   generate_insights():
    │       POST Ollama qwen2.5:7b
    │       prompt: total spent, breakdown, credit limit
    │       → 3-4 line practical recommendations
    │
    └─[executor]─ send_chart_whatsapp(chart_path, caption)
                    Step 1: POST /media → upload PNG → media_id
                    Step 2: POST /messages type=image → send
```

---

## Email Classification Pipeline

```
For each email:

  ┌─────────────────────────────────────────────────────┐
  │  Step 1: Keyword Pre-filter (no I/O, instant)       │
  │                                                     │
  │  _is_blocked()?                                     │
  │    sender in BLOCK_SENDERS                          │
  │    OR text contains BLOCK_KEYWORDS                  │
  │    (promotions, OTPs, discounts, newsletters)       │
  │    → SKIP (never reaches Ollama)                    │
  │                                                     │
  │  _is_tech_blog()?                                   │
  │    sender domain in TECH_BLOG_DOMAINS               │
  │    (medium.com, substack.com, bytebytego.com, ...)  │
  │    → PASS directly (no Ollama needed)               │
  │                                                     │
  │  _is_large_debit()?                                 │
  │    sender in TRUSTED_DOMAINS                        │
  │    AND text contains "debited/debit/withdrawn"      │
  │    AND amount regex > ₹5000                         │
  │    → PASS as "⚠️ Large Bank Debit Alert"            │
  │                                                     │
  │  _keyword_match()?                                  │
  │    sender domain in TRUSTED_DOMAINS                 │
  │    OR subject/snippet contains SUBJECT_KEYWORDS     │
  │    → PASS to Ollama                                 │
  │                                                     │
  │  else → SKIP                                        │
  └─────────────────────────────────────────────────────┘
              │
              ▼ candidates only
  ┌─────────────────────────────────────────────────────┐
  │  Step 2: Async Parallel Ollama                      │
  │                                                     │
  │  asyncio.gather(*[ask_ollama(e) for e in candidates]│
  │                                                     │
  │  System prompt: classify into one of 9 categories   │
  │  Response: {categories: [...], summary: "..."}      │
  │                                                     │
  │  Categories:                                        │
  │  • Bank / Finance                                   │
  │  • LIC / Insurance                                  │
  │  • Share Market / Investments                       │
  │  • Income Tax / IT Returns                          │
  │  • Employment / Salary / HR                         │
  │  • Job / Recruitment                                │
  │  • Training / Courses / Certification               │
  │  • Tech Blog / Article to Read                      │
  │  • ⚠️ Large Bank Debit Alert                        │
  └─────────────────────────────────────────────────────┘
              │
              ▼
  _format_message() — group by primary category
  ━━━ Bank / Finance ━━━
    1. Subject line
       One-line summary with ₹ amount
```

---

## Async Execution Model

```
agent.py event loop
    │
    ├── gmail_fetch (MCP call, awaited)
    │
    └── asyncio.gather()
            │
            ├── classify_emails()          ← async coroutine
            │       └── asyncio.gather()
            │               ├── ask_ollama(email_1)  ─┐
            │               ├── ask_ollama(email_2)   ├─ all parallel
            │               └── ask_ollama(email_N)  ─┘
            │
            └── analyze_statement()        ← async coroutine (if statement found)
                    ├── run_in_executor(download_pdf)    ← blocking I/O
                    ├── run_in_executor(extract_txns)    ← blocking CPU
                    └── asyncio.gather()
                            ├── run_in_executor(generate_chart)  ← CPU (matplotlib)
                            └── generate_insights()              ← async Ollama
```

All blocking calls (Gmail API, pdfplumber, matplotlib, requests) run in the default `ThreadPoolExecutor` via `loop.run_in_executor(None, fn)` — the event loop stays unblocked.

---

## Secret Management

```
macOS Keychain
    │
    ├── email-agent-wa-token      → Meta WhatsApp API access token
    ├── email-agent-wa-phone-id   → WhatsApp phone number ID
    └── email-agent-wa-to         → Recipient WhatsApp number

Gmail OAuth2
    ├── credentials.json          → OAuth2 client ID (from Google Cloud Console)
    └── .token.pickle             → Cached access + refresh token (auto-refreshed)

utils.py::get_secret(key)
    └── subprocess: security find-generic-password -s <key> -w
```

No secrets in `.env`, no secrets in code, no secrets in logs.

---

## Scheduler

```
launchd (com.emailagent.daily.plist)
    │
    ├── Runs at: 08:00 daily
    ├── Python: .venv/bin/python3 agent.py
    ├── stdout → logs/agent.log
    └── stderr → logs/agent.error.log

reminder.py (optional, separate plist at 09:00)
    └── If .last_run ≠ today → send WhatsApp reminder
```

Load/unload:
```bash
launchctl load   ~/Library/LaunchAgents/com.emailagent.daily.plist
launchctl unload ~/Library/LaunchAgents/com.emailagent.daily.plist
launchctl list | grep emailagent
```

---

## WhatsApp Message Format

```
📧 *Daily Email Summary*

━━━ Bank / Finance ━━━
  1. Transaction alert for your ICICI Bank Credit Card
     ₹4,925 debited from ICICI credit card

━━━ Tech Blog / Article to Read ━━━
  1. ByteByteGo Newsletter: System Design Weekly
     Weekly system design patterns and case studies

━━━ ⚠️ Large Bank Debit Alert ━━━
  1. HDFC Bank: Large debit of ₹12,500
     ₹12,500 debited — possible EMI or large purchase
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| MCP over direct function calls | Tool discovery at runtime — add tools without changing agent logic |
| `classify_emails` imported directly in `agent.py` (not via MCP) | Avoids double JSON serialisation of email list; async coroutine works naturally |
| Keyword pre-filter before Ollama | Eliminates 70-80% of emails instantly — Ollama only sees real candidates |
| `asyncio.gather` for Ollama calls | 4 emails in parallel ≈ same time as 1 sequential call |
| `run_in_executor` for blocking calls | Keeps event loop unblocked; chart + insights run simultaneously |
| macOS Keychain for secrets | Zero-file secret storage; survives reboots; no `.env` to accidentally commit |
| `DRY_RUN` env flag | Protects WhatsApp free-tier quota during development and testing |
| Gmail batch API | One HTTP round trip for all email metadata — faster than N individual calls |
| Server-side Gmail query filter | Reduces emails fetched from Gmail before any local processing |
| Dark theme chart | Better readability on phone screens; matches WhatsApp dark mode |

---

## File Reference

```
email-agent/
├── agent.py                    MCP host, main orchestrator
├── mcp_server.py               FastMCP server, 5 tools
├── classifier.py               Email filter + async Ollama classifier
├── gmail_fetcher.py            Gmail OAuth2 batch fetcher (read-only)
├── statement_analyzer.py       PDF → transactions → chart → insights
├── whatsapp_notifier.py        Meta Cloud API sender (DRY_RUN support)
├── utils.py                    Keychain, log, timer
├── reminder.py                 Daily run tracker + WhatsApp reminder
├── requirements.txt            Pinned dependencies
├── com.emailagent.daily.plist  launchd scheduler (8 AM daily)
├── credentials.json            Gmail OAuth2 client ID (not committed)
├── .token.pickle               Gmail cached token (not committed)
├── .last_run                   Date of last successful run (not committed)
├── spending_chart.png          Generated chart (not committed)
├── logs/                       launchd stdout/stderr (not committed)
├── AGENT_BOOTSTRAP.md          Generic MCP agent setup guide
├── PROJECT_ARCHITECTURE.md     This document
└── .gitignore                  Excludes all secrets and generated files
```
