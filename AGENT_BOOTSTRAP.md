# Agentic AI with MCP — Bootstrap Prompt for AI Agents

> **Purpose:** Hand this document to any AI coding agent (Kiro, Cursor, Copilot, Claude, etc.) to build a fully local, general-purpose agentic AI system using the Model Context Protocol (MCP) with any external tools — from scratch, without a single manual command.

---

## What You Are Building

A **fully local agentic AI system** where:

- An **MCP host agent** (`agent.py`) orchestrates tasks by calling tools over stdio
- An **MCP server** (`mcp_server.py`) exposes capabilities as typed tools via FastMCP
- A **local LLM** (Ollama) does all AI inference — no data leaves the machine
- External integrations (email, messaging, APIs, files) are wrapped as MCP tools
- Secrets are stored in **macOS Keychain only** — never in files or env vars
- The agent runs on a **schedule** via macOS launchd

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Agent protocol | MCP (Model Context Protocol) | Typed tools, stdio transport, language-agnostic |
| MCP library | `mcp[cli]==1.6.0` (FastMCP) | Minimal boilerplate, decorator-based tools |
| Local LLM | Ollama `qwen2.5:7b` | Fast, 7B fits in 8 GB RAM, good instruction following |
| Async HTTP | `aiohttp` | Parallel Ollama calls without threads |
| Secret store | macOS Keychain (`security` CLI) | Zero-file secret storage |
| Scheduler | macOS launchd plist | Reliable, no cron, survives reboots |
| Python | 3.11+ in a venv | Isolated, reproducible |

---

## Project Layout

```
my-agent/
├── agent.py              # MCP host — orchestrates all tasks
├── mcp_server.py         # MCP server — exposes tools via FastMCP
├── utils.py              # Keychain helpers, log(), timer()
├── requirements.txt      # Pinned dependencies
├── com.myagent.plist     # launchd scheduler
├── .gitignore            # Never commit secrets or tokens
└── logs/                 # stdout/stderr from launchd
```

Add one Python module per external integration (e.g. `gmail_fetcher.py`, `slack_notifier.py`). Import and expose them as tools in `mcp_server.py`.

---

## Step-by-Step Build Instructions

### 1. Bootstrap the project

```bash
mkdir ~/Projects/my-agent && cd ~/Projects/my-agent
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```
# requirements.txt — always pin versions
mcp[cli]==1.6.0
aiohttp==3.9.5
requests==2.31.0
```

```bash
pip install -r requirements.txt
```

### 3. Store secrets in Keychain

Never use `.env` files or hardcode secrets. Use macOS Keychain:

```bash
# Store a secret
security add-generic-password -s "my-agent-api-key" -a "my-agent" -w "YOUR_SECRET_VALUE"

# Read it back (verify)
security find-generic-password -s "my-agent-api-key" -w
```

In Python (`utils.py`):

```python
import subprocess

def get_secret(key: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", key, "-w"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None
```

### 4. Build `utils.py`

```python
import subprocess, sys, time
from contextlib import contextmanager
from datetime import datetime

def get_secret(key: str) -> str | None:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", key, "-w"],
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

@contextmanager
def timer(label: str):
    t = time.perf_counter()
    yield
    print(f"  ⏱  {label}: {time.perf_counter()-t:.2f}s")
```

### 5. Build `mcp_server.py`

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-agent")

@mcp.tool()
def my_tool(param: str) -> str:
    """Tool description — shown to the agent."""
    # implement here
    return "result"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Rules for MCP tools:
- Return `str`, `bool`, `list`, or `dict` — FastMCP serialises these automatically
- For complex objects, return `json.dumps(obj)` and parse on the host side
- Async tools: use `async def` and `await` — FastMCP handles the event loop
- Blocking I/O inside async tools: wrap with `loop.run_in_executor(None, fn, *args)`

### 6. Build `agent.py`

```python
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from utils import log, timer

SERVER_CMD = [sys.executable, "mcp_server.py"]

async def main():
    server_params = StdioServerParameters(command=SERVER_CMD[0], args=SERVER_CMD[1:])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover tools (makes agent general-purpose)
            tools = await session.list_tools()
            log(f"Tools: {[t.name for t in tools.tools]}")

            # Call a tool
            with timer("my_tool"):
                result = await session.call_tool("my_tool", {"param": "value"})
            output = result.content[0].text
            log(f"Result: {output}")

asyncio.run(main())
```

### 7. Add Ollama for local LLM inference

```bash
# Install Ollama (one-time)
brew install ollama
ollama pull qwen2.5:7b
ollama serve  # runs on http://127.0.0.1:11434
```

Async parallel inference pattern (call multiple emails/items at once):

```python
import aiohttp, asyncio, json

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

async def ask_ollama(session: aiohttp.ClientSession, prompt: str) -> str:
    async with session.post(
        OLLAMA_URL,
        json={"model": MODEL,
              "messages": [{"role": "user", "content": prompt}],
              "stream": False},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        data = await resp.json()
        return data["message"]["content"].strip()

async def classify_many(items: list[str]) -> list[str]:
    async with aiohttp.ClientSession() as session:
        tasks = [ask_ollama(session, item) for item in items]
        return await asyncio.gather(*tasks)  # all in parallel
```

### 8. Handle blocking calls in async context

Any blocking I/O or CPU-heavy work inside an `async` function must use an executor:

```python
import asyncio
from functools import partial

loop = asyncio.get_event_loop()

# Blocking I/O (file read, pickle, requests)
result = await loop.run_in_executor(None, blocking_function, arg1, arg2)

# CPU-heavy (matplotlib, pdfplumber)
result = await loop.run_in_executor(None, partial(cpu_function, arg1, arg2))

# Run two blocking tasks in parallel
result_a, result_b = await asyncio.gather(
    loop.run_in_executor(None, task_a),
    loop.run_in_executor(None, task_b),
)
```

### 9. Add a dry-run flag for external APIs

Protect free-tier quotas during development:

```python
import os

# WA_DRY_RUN=false python agent.py  → actually sends
# python agent.py                   → prints only (safe default)
DRY_RUN = os.environ.get("WA_DRY_RUN", "true").lower() != "false"

def send_message(text: str) -> bool:
    if DRY_RUN:
        print("─" * 60)
        print(text)
        print("─" * 60)
        return True
    # real API call here
```

### 10. Schedule with launchd (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.myagent.daily.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.myagent.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/my-agent/.venv/bin/python3</string>
        <string>/path/to/my-agent/agent.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/my-agent/logs/agent.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/my-agent/logs/agent.error.log</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
```

```bash
mkdir -p ~/Projects/my-agent/logs
cp com.myagent.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.myagent.daily.plist
launchctl list | grep myagent   # verify loaded
```

---

## Adding a New External Tool

1. Create `my_integration.py` with the logic
2. Add a `@mcp.tool()` function in `mcp_server.py` that calls it
3. Call it from `agent.py` via `session.call_tool("tool_name", {...})`
4. Store any API keys in Keychain, read via `get_secret()`

No changes to the agent protocol — tools are discovered automatically at startup.

---

## .gitignore (always include)

```
.venv/
*.pickle
*.token
.last_run
logs/
credentials.json
*.pyc
__pycache__/
spending_chart.png
```

---

## Common Pitfalls

| Pitfall | Fix |
|---|---|
| FastMCP tool returns a complex object | Return `json.dumps(obj)` instead |
| `asyncio.run()` inside an async function | Use `await coroutine()` directly |
| Blocking `requests` inside `async def` | Wrap with `run_in_executor` |
| Secrets in `.env` or code | Use macOS Keychain only |
| `import asyncio` at module level but unused | Remove it — import locally where needed |
| Gmail batch API SSL crash in threads | Use Google's `new_batch_http_request()` not `ThreadPoolExecutor` |
| Ollama calls sequential | Use `asyncio.gather(*[ask_ollama(...) for item in items])` |

---

## Verification Checklist

Before running the agent:

```bash
# 1. Syntax check all files
python3 -m py_compile agent.py mcp_server.py utils.py && echo "✅ OK"

# 2. Verify Ollama is running
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool

# 3. Verify secrets exist
security find-generic-password -s "my-agent-api-key" -w

# 4. Dry run first
python3 agent.py   # DRY_RUN=true by default

# 5. Live run
WA_DRY_RUN=false python3 agent.py
```
