# ⚡ Gemini Web Bridge
> When your agent hits API rate limits, don't stop working — offload to Gemini Web.

### 🛑 The Wall
You're in the middle of an intensive refactor, debugging session, or multi-step plan. Antigravity is in the zone.

Then it happens:
```text
HTTP 429: Rate limit exceeded. Quota resets in 3 hours 42 minutes.
```

Your pipeline freezes. But right in your browser, Gemini Web UI is sitting wide awake with full Extended Thinking enabled.

### 💸 The Rate-Limited Agent & The Idle Web Session
A Google One AI subscription (Google AI Pro / Ultra) powers first-party agentic tools like **Google Antigravity** alongside the **Gemini Web UI** (`gemini.google.com`). 

However, they operate in separate usage silos:
- **Antigravity**: During intense refactoring or autonomous coding loops, Antigravity eventually hits hourly turn limits and rate caps.
- **Gemini Web UI**: Meanwhile, your included web interface quota sits completely idle in an open tab with fresh deliberation budgets and native Extended Thinking.

**Gemini Web Bridge** connects Antigravity directly into that idle browser session. It exposes your active web interface as a local OpenAI-compatible endpoint (`http://127.0.0.1:8765/v1/chat/completions`). When Antigravity hits rate limits or needs to offload token-heavy architectural planning and diagnostics, it delegates the reasoning straight to Gemini Web. You keep moving without idling through cooldowns.

---

## 🛟 The Practical Fallback

| You Hit The Rate Limit | With Gemini Web Bridge |
| :--- | :--- |
| 🛑 Blocked by API limits mid-task | ⚡ Antigravity routes reasoning to Gemini Web seamlessly |
| 💸 Burning precious tokens on broad diagnostic exploration | 🧠 Heavy deliberation runs in an isolated browser session |
| ⏳ Idling hours waiting for token windows to reset | 🔄 Drop-in OpenAI endpoint: zero workflow interruption |

> **Honest note on token economics**: Antigravity still needs a small token budget to orchestrate, dispatch sub-tasks, and review incoming patches. What disappears is the massive token drain: multi-thousand-token reasoning traces, exploratory brainstorming, and heavy initial drafts execute entirely inside Gemini Web for zero API cost.

Drop-in `http://127.0.0.1:8765/v1/chat/completions`. Compatible with Antigravity subagent offloading, OpenAI SDKs, and local workflows.

---

## 🔧 Architecture

One local process + one lightweight Firefox extension. No cloud relay, no third-party proxies, zero telemetry.

```text
 Antigravity  (Google DeepMind Agent · subagents · Python client)
      │
      │  OpenAI-compatible HTTP POST (/v1/chat/completions)
      ▼
 ┌───────────────────────────────────────────────────────────┐
 │  gemini-web-bridge  (http://127.0.0.1:8765)               │
 │  aiohttp server · request queues · WebSocket multiplexer  │
 └───────────────────────────────────────────────────────────┘
      │
      │  WebSocket (ws://127.0.0.1:8765)
      ▼
 ┌───────────────────────────────────────────────────────────┐
 │  Firefox Extension  (gemini-bridge@local)                 │
 │  background.js (tab routing) · content.js (DOM automation)│
 └───────────────────────────────────────────────────────────┘
      │
      │  Native Angular CDK overlay selection & prompt insertion
      ▼
 Gemini Web UI  (https://gemini.google.com/app)
 [Flash Extended · Full Deliberation Active]
```

---

## ⚡ Quick Start

### 1. Python Virtualenv & Server Setup
```bash
uv venv
source .venv/bin/activate
uv pip install aiohttp websockets
```

Run server:
```bash
python3 -u server.py
```

*(Optional)* Run as a persistent background `systemd` user service:
```ini
# ~/.config/systemd/user/gemini-web-bridge.service
[Unit]
Description=Gemini Web Bridge Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/pipe2bot/me/cyber/ai/gemini-web-brige
ExecStart=/home/pipe2bot/me/cyber/ai/gemini-web-brige/.venv/bin/python3 -u server.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
```
```bash
systemctl --user daemon-reload
systemctl --user enable --now gemini-web-bridge.service
```

---

## 🔌 Extension Installation Guide

Package extension source first:
```bash
cd extension && zip -FSr ../extension.xpi manifest.json background.js content.js && cd ..
```

### Method 1: Temporary Add-on (Dev / No Root / 30 Seconds)
Fastest way to test without root permissions. Temporary add-ons stay loaded until Firefox quits.

1. In Firefox, open URL bar and type:
   ```text
   about:debugging#/runtime/this-firefox
   ```
2. Click **"Load Temporary Add-on..."**.
3. Select `extension/manifest.json` (or `extension.xpi`).
4. Switch to your Gemini tab at `https://gemini.google.com/app`.
5. You will see the centered status badge:
   ```text
   ⚡ Gemini Bridge: Active
   ```

*To reload after editing code:* Click **Reload** in `about:debugging`, then press `F5` on the Gemini tab.

---

### Method 2: Permanent Sideload (Linux Enterprise Policy / Zero-Click Auto-Load)
Persists permanently across all Firefox launches, updates, and reboots without AMO signing barriers (`SCOPE_APPLICATION`).

#### Step A: Configure Enterprise Policy
```bash
sudo mkdir -p /etc/firefox/policies
sudo bash -c 'cat <<EOF > /etc/firefox/policies/policies.json
{
  "policies": {
    "ExtensionSettings": {
      "gemini-bridge@local": {
        "installation_mode": "force_installed"
      }
    }
  }
}
EOF'
```

#### Step B: Symlink Extension Package
```bash
sudo mkdir -p /usr/lib/firefox/browser/extensions
sudo ln -sf "$(pwd)/extension.xpi" /usr/lib/firefox/browser/extensions/gemini-bridge@local.xpi
```

#### Step C: Restart Firefox
Restart Firefox. The extension is permanently locked and loaded under `about:addons`.

---

## 🧪 Verification

Run the built-in unit test suite to verify end-to-end communication, automatic Angular CDK thinking toggle, and response integrity:

```bash
python3 test_extended_thinking.py
```

Expected output:
```text
..
----------------------------------------------------------------------
Ran 2 tests in 8.733s

OK
```

---

## 💬 API Usage

### OpenAI SDK Compatible
```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="sk-local")

response = client.chat.completions.create(
    model="gemini-thinking-web",
    messages=[{"role": "user", "content": "Explain quantum decoherence simply."}],
    extra_body={"thinking": True, "include_thoughts": True}
)

print(response.choices[0].message.content)
```

### Standalone Helper (`gemini_client.py`)
```python
from gemini_client import query_gemini

answer = query_gemini(
    prompt="Solve this math puzzle: If 2x + 5 = 19, what is x?",
    model="gemini-thinking-web"
)
print(answer)
```

---

## ⚠️ Disclaimer

Developed and tested based on **Mozilla Firefox**. Chromium-based browsers and other platforms are currently untested.


