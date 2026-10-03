# AGENTS.md — Gemini Web Bridge Guide

Operational specifications, architectural invariants, and workflows for autonomous agents and engineers maintaining `gemini-web-bridge`.

---

## 1. Project Overview & Architecture

`gemini-web-bridge` exposes a local OpenAI-compatible HTTP endpoint (`http://127.0.0.1:8765/v1/chat/completions`) backed by a live browser session on Gemini Web (`https://gemini.google.com/app`). Enables autonomous agents (Hermes Agent, Antigravity) to offload reasoning, planning, and code generation without direct API costs or rate limits.

### Architecture Flow
```text
[AI Agent / Client]
       │
       ▼ (HTTP POST /v1/chat/completions)
[server.py] (aiohttp + websockets, port 8765)
       │
       ▼ (WebSocket ws://127.0.0.1:8765/ws)
[extension/background.js] (Firefox WebExtension)
       │
       ▼ (browser.tabs.sendMessage)
[extension/content.js] (Injected into gemini.google.com/app)
       │
       ▼ (Synthetic DOM events, MutationObserver)
[Gemini Web UI]
```

### Component Breakdown
- **`server.py`**:
  - Exposes `/v1/chat/completions`, `/v1/models`, `/health`, `/new-chat`, `/status`, and `/ws`.
  - Translates OpenAI JSON payloads into WebSocket bridge tasks.
  - Converts images and local file paths into base64 Data URLs.
  - Manages concurrent request queue and WebSocket heartbeat/disconnections.
- **`extension/background.js`**:
  - Connects to `ws://127.0.0.1:8765/ws`.
  - Finds and pins the active Gemini Web tab.
  - Forwards requests to `content.js` and relays chunks/final responses back to `server.py`.
- **`extension/content.js`**:
  - Interacts with Gemini Web DOM.
  - Enforces model picker selection (`Flash Extended` / `3.8 Flash`).
  - Injects prompts into rich-text editor (`.ql-editor` / `rich-textarea`).
  - Injects attachments via synthetic `DataTransfer` file inputs.
  - Observes response generation using `MutationObserver` and baseline `generationStarted` gating.
- **Verification Scripts**:
  - `test_unit_all.py`: Isolated offline unit test suite for all server/client functions (no browser required).
  - `test_openai_api.py`: Validates OpenAI API endpoint compatibility.
  - `test_extended_thinking.py`: Validates Extended Thinking model selection and thought output.
  - `test_attachment_support.py`: Validates multimodal image/doc handling and OCR.
  - `test_tool_calling.py`: Validates OpenAI tool-calling emulation parsing and formatting.
  - `test_gemini_web_bridge_cli.py`: Validates CLI wrapper piping, arguments, and attachments.
- **Cache & Troubleshooting**:
  - `hotcache.md`: Live operational status and selector mappings.
  - `TROUBLESHOOT.md`: Root cause analysis records of incidents and regressions.
  - `log.md`: Chronological task execution log.

---

## 2. Key Architectural Invariants & Rules

1. **Strict Flash Extended Routing**:
   - When reasoning/thinking is requested, `content.js` MUST select `Flash Extended` and target `3.8 Flash`.
   - Never fall back to `Flash-Lite` or standard models without explicit instruction.
2. **Zero Synthetic System Prompt Wrappers**:
   - Pass user prompts and multi-turn messages directly without synthetic system persona boilerplate unless requested by user.
3. **Non-Destructive DOM Automation**:
   - Use standard event dispatching (`input`, `change`, `keydown`) and `DataTransfer`.
   - Never use arbitrary `setTimeout` delays when DOM predicates (`MutationObserver`, `waitForSelector`) can determine completion.
4. **Clean Baseline Check**:
   - Guard against premature resolution race conditions: confirm response generation has actively begun before listening for completion.
5. **Scoped DOM Selectors for Busy/Loading States**:
   - Always scope loading spinners, progress bars, and upload gates to `.input-area` (`container.querySelector`). Root-level `document.querySelector('[role="progressbar"]')` will match persistent background UI spinners and hang forever.
6. **Quill Editor Keystroke Emulation**:
   - Never use `document.execCommand('selectAll')` in Firefox (wipes the whole document body selection). Use DOM `Range` + `Selection` to clear/insert text.
   - Always dispatch `keyup` and `keydown` events on `.ql-editor` after text insertion to trigger Angular/Quill change detection; otherwise `button[aria-label*="Send message"]` will not mount and will remain as `Dictate (^⇧D)`.
7. **Enterprise Policy & Sideload Scope**:
   - Lock `extensions.autoDisableScopes: 0` in `/etc/firefox/policies/policies.json` to prevent Firefox from marking `/usr/lib/firefox/browser/extensions/` sideloaded extensions as `userDisabled: true`.
8. **PEP 668 Environment**:
   - Always run Python within `uv venv` (`.venv/bin/python3`). Never install packages to system Python.

---

## 3. Developer & Agent Workflows

### Starting / Managing the Service
- **Systemd User Service**:
  ```bash
  systemctl --user status gemini-web-bridge.service
  systemctl --user restart gemini-web-bridge.service
  journalctl --user -u gemini-web-bridge.service -f
  ```
- **Manual Run (foreground debugging)**:
  ```bash
  source .venv/bin/activate
  python3 -u server.py
  ```

### Packaging & Sideloading the Extension
- Firefox loads the extension automatically via `/etc/firefox/policies/policies.json` or sideloaded at `/usr/lib/firefox/browser/extensions/gemini-bridge@local.xpi`.
- To rebuild `extension.xpi` after changing `extension/`:
  ```bash
  cd extension && zip -FSr ../extension.xpi manifest.json background.js content.js && cd ..
  ```
- After rebuilding `extension.xpi`, restart Firefox to flush cached bytecode and reload the extension.

### Running Test Suites
Run offline unit tests:
```bash
.venv/bin/python3 test_unit_all.py
```
Run live integration test scripts against the active bridge:
```bash
.venv/bin/python3 test_openai_api.py
.venv/bin/python3 test_extended_thinking.py
.venv/bin/python3 test_attachment_support.py
.venv/bin/python3 test_tool_calling.py
.venv/bin/python3 test_gemini_web_bridge_cli.py
```

### Triaging DOM Changes
1. Inspect Gemini Web UI DOM via Firefox DevTools (F12).
2. Check model menu trigger: `bard-mode-menu-button`, `gem-menu-item`.
3. Check prompt editor: `.ql-editor`, `div[contenteditable="true"]`.
4. Check send button: `button[aria-label*="Send"]`.
5. Update `hotcache.md` and log any breaking fixes in `TROUBLESHOOT.md`.

---

## 4. Coding Standards

- **Root Cause First**: Fix bugs at the source mechanism (e.g. race condition baseline or DOM selector hierarchy), not superficial symptom wrappers.
- **Terse & Functional**: No unnecessary abstractions, no dummy boilerplate.
- **Durability**: Always update `hotcache.md` and `log.md` when adjusting bridge behavior or architecture.
