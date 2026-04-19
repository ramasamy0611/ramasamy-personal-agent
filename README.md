# Email Agent

Reads Gmail daily, classifies important emails using local Ollama (`qwen2.5:7b`), and sends a WhatsApp summary via Meta Cloud API.

**Everything runs locally. No email deletion. Secrets stored in macOS Keychain.**

---

## Setup

### 1. Install dependencies
```bash
cd ~/Projects/repo/email-agent
pip3 install -r requirements.txt
```

### 2. Gmail OAuth2 credentials
1. Go to https://console.cloud.google.com
2. Create project → Enable **Gmail API**
3. APIs & Services → Credentials → Create OAuth 2.0 Client ID → Desktop app
4. Download JSON → save as `credentials.json` in this folder
5. First run will open a browser to authorise — token saved locally as `.token.pickle`

### 3. Meta WhatsApp Cloud API
1. Go to https://developers.facebook.com → Create App → Business
2. Add WhatsApp product → get your **Phone Number ID** and **Access Token**
3. Add your personal WhatsApp number as a test recipient

### 4. Store secrets in Keychain (never in files)
```bash
python3 utils.py set-secret email-agent-wa-token      YOUR_META_ACCESS_TOKEN
python3 utils.py set-secret email-agent-wa-phone-id   YOUR_PHONE_NUMBER_ID
python3 utils.py set-secret email-agent-wa-to         YOUR_WHATSAPP_NUMBER  # e.g. 919876543210
```

### 5. Test manually
```bash
python3 agent.py
```

### 6. Schedule daily at 8 AM (launchd)
```bash
mkdir -p ~/Projects/repo/email-agent/logs
cp com.emailagent.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.emailagent.daily.plist
```

To unload:
```bash
launchctl unload ~/Library/LaunchAgents/com.emailagent.daily.plist
```

---

## Categories watched
- Bank / Finance
- LIC / Insurance
- Share Market / Investments
- Income Tax / IT Returns
- Employment / Salary / HR
- Job / Recruitment
- Training / Courses / Certification

---

## Security
- Gmail scope: **read-only** (`gmail.readonly`) — cannot delete, send, or modify
- All secrets in **macOS Keychain** — not in `.env` or code
- `credentials.json` and `.token.pickle` are in `.gitignore`
- Local LLM only — email content never sent to cloud AI
- Ollama bound to `127.0.0.1:11434` — not exposed to network
