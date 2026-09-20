#!/usr/bin/env python3
import json
import os
import unittest
import urllib.request

SERVER_URL = "http://127.0.0.1:8765/v1/chat/completions"
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "Pasted image 20260717110900.png")

class TestAttachmentSupport(unittest.TestCase):
    def test_01_image_attachment_ocr(self):
        self.assertTrue(os.path.isfile(IMAGE_PATH), f"Test image missing: {IMAGE_PATH}")

        payload = {
            "model": "gemini-web",
            "messages": [
                {
                    "role": "user",
                    "content": "Perform OCR on this image. What is the document name mentioned in the prompt?"
                }
            ],
            "image_path": IMAGE_PATH,
            "new_chat": True
        }
        req = urllib.request.Request(
            SERVER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            self.assertIn("Quarterly Report_20201231", content)

    def test_02_attachment_with_extended_thinking(self):
        payload = {
            "model": "gemini-thinking-web",
            "messages": [
                {
                    "role": "user",
                    "content": "Analyze this screenshot. What application created Event 300 and what document was being modified?"
                }
            ],
            "image_path": IMAGE_PATH,
            "thinking": True,
            "include_thoughts": True,
            "new_chat": True
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
            content = data["choices"][0]["message"]["content"]
            self.assertIn("Quarterly Report_20201231", content)
            self.assertTrue(
                "thinking process" in content.lower() or "word" in content.lower(),
                f"Expected reasoning trace or application identification: {content[:200]}"
            )

    def test_03_pdf_document_attachment(self):
        pdf_path = os.path.join(os.path.dirname(__file__), "test_sample.pdf")
        self.assertTrue(os.path.isfile(pdf_path), f"PDF test fixture missing: {pdf_path}")

        payload = {
            "model": "gemini-web",
            "messages": [
                {
                    "role": "user",
                    "content": "What is the exact text inside this attached PDF?"
                }
            ],
            "image_path": pdf_path,
            "new_chat": True
        }
        req = urllib.request.Request(
            SERVER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            self.assertIn("Gemini Web Bridge PDF Test: Success", content)

if __name__ == "__main__":
    unittest.main()
