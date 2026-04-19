# Pre-Commit Checklist

Run through this before every `git commit` or `git push`.

---

## 1. Secrets & Sensitive Files — Must NOT be staged

Run `git status` and confirm these are absent from the staged list:

| File | Why sensitive |
|---|---|
| `credentials.json` | Gmail OAuth2 client secret |
| `.token.pickle` | Gmail access + refresh token |
| `.last_run` | Runtime state (not useful in repo) |
| `spending_chart.png` | Generated output |
| `logs/` | May contain email subjects or amounts |
| `.venv/` | Local virtualenv |
| `__pycache__/` | Compiled bytecode |
| `.env` | Would contain plaintext secrets if ever created |
| `*.pem`, `*.key` | Private keys |

Quick check:
```bash
git status --short
# None of the above should appear with A (added) or M (modified)
```

Hard stop — if any of these appear, do NOT commit:
```bash
git reset HEAD credentials.json .token.pickle  # unstage immediately
```

---

## 2. Scan Staged Files for Hardcoded Secrets

```bash
git diff --cached | grep -iE "(token|secret|password|api_key|bearer|access_key|phone_id)" 
```

Expected: no matches, or only variable *names* (not values).  
If a real token value appears (long alphanumeric string), unstage and move it to Keychain.

---

## 3. Scan for Indian PII

```bash
git diff --cached | grep -iE "(\+91|919[0-9]{9}|[A-Z]{5}[0-9]{4}[A-Z]|[0-9]{12})"
```

Catches: mobile numbers, PAN numbers, Aadhaar numbers.  
If found, replace with a placeholder and store real value in Keychain.

---

## 4. Verify .gitignore is Effective

```bash
git check-ignore -v credentials.json .token.pickle .last_run spending_chart.png
```

All four should print a `.gitignore` rule. If any prints nothing, add it to `.gitignore` before committing.

---

## 5. Python Syntax Check

```bash
cd ~/Projects/repo/email-agent
.venv/bin/python3 -m py_compile agent.py mcp_server.py classifier.py gmail_fetcher.py \
    statement_analyzer.py whatsapp_notifier.py utils.py reminder.py && echo "✅ All OK"
```

---

## 6. Dry-Run Smoke Test

```bash
cd ~/Projects/repo/email-agent
.venv/bin/python3 agent.py   # WA_DRY_RUN defaults to true — safe to run
```

Expected: fetches emails, classifies, prints WhatsApp message to terminal. No actual send.

---

## 7. Commit Message Format

```
<type>: <short summary under 70 chars>

Types: feat | fix | docs | refactor | chore
```

Examples:
```
feat: add bank statement PDF analysis with spending chart
fix: wrap blocking Gmail calls in run_in_executor
docs: add PROJECT_ARCHITECTURE and PRE_COMMIT_CHECKLIST
chore: pin all dependencies in requirements.txt
```

---

## First-Time GitHub Setup (one-off)

```bash
# 1. Set git identity
git config --global user.name  "Your Name"
git config --global user.email "your@email.com"

# 2. Init repo
cd ~/Projects/repo/email-agent
git init
git branch -M main

# 3. Create private repo on GitHub at https://github.com/new
#    Name: email-agent | Private | No README | No .gitignore

# 4. Add remote
git remote add origin https://github.com/<your-username>/email-agent.git

# 5. Stage only safe files (explicit, not git add .)
git add agent.py mcp_server.py classifier.py gmail_fetcher.py \
        statement_analyzer.py whatsapp_notifier.py utils.py reminder.py \
        requirements.txt com.emailagent.daily.plist \
        README.md AGENT_BOOTSTRAP.md PROJECT_ARCHITECTURE.md \
        PRE_COMMIT_CHECKLIST.md .gitignore

# 6. Final check before commit
git status --short   # only the files above should appear

# 7. Commit and push
git commit -m "feat: initial commit — local email agent with Ollama, Gmail, WhatsApp"
git push -u origin main
```

---

## Ongoing Commits

```bash
git add <specific files>   # never: git add .
git status --short         # verify staged list
# run checks 1–5 above
git commit -m "<type>: <summary>"
git push
```

> **Rule:** Always `git add <file>` explicitly. Never `git add .` — it bypasses your mental check.
