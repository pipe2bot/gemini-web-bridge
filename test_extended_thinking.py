#!/usr/bin/env python3
import json
import re
import unittest
import urllib.request

SERVER_URL = "http://127.0.0.1:8765/v1/chat/completions"

class TestExtendedThinking(unittest.TestCase):
    def test_01_extended_thinking_active(self):
        payload = {
            "model": "gemini-thinking-web",
            "messages": [
                {"role": "user", "content": "are you on extended thinking mode"}
            ],
            "thinking": True,
            "include_thoughts": True,
            "new_chat": False
        }
        req = urllib.request.Request(
            SERVER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].lower()
            self.assertTrue(
                any(token in content for token in ["yes", "active", "extended thinking", "thinking mode"]),
                f"Model response did not confirm thinking mode: {content}"
            )

    def test_02_dom_mode_picker_state(self):
        payload = {
            "model": "gemini-thinking-web",
            "messages": [{"role": "user", "content": "__DUMP_BUTTONS__"}],
            "thinking": True
        }
        req = urllib.request.Request(
            SERVER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            btns = json.loads(data["choices"][0]["message"]["content"])
            pickers = [b for b in btns if "mode picker" in (b.get("label") or "").lower()]
            self.assertTrue(len(pickers) > 0, "Mode picker button not found in DOM")
            label_or_text = f"{pickers[0].get('label', '')} {pickers[0].get('text', '')}".lower()
            self.assertTrue(
                "extended" in label_or_text or "thinking" in label_or_text,
                f"Picker button does not show Extended Thinking: {label_or_text}"
            )

if __name__ == "__main__":
    unittest.main()
