#!/usr/bin/env python3
import os
import subprocess
import unittest

CLI_PATH = os.path.join(os.path.dirname(__file__), "gemini-web-bridge")
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "Pasted image 20260717110900.png")
PDF_PATH = os.path.join(os.path.dirname(__file__), "test_sample.pdf")

class TestGeminiWebBridgeCLI(unittest.TestCase):

    def test_01_positional_prompt(self):
        cmd = [CLI_PATH, "--no-thinking", "output exactly: alpha-test"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("alpha-test", proc.stdout)

    def test_02_stdin_piping(self):
        cmd = [CLI_PATH, "--no-thinking"]
        proc = subprocess.run(
            cmd,
            input="output exactly: bravo-test",
            capture_output=True,
            text=True,
            timeout=60
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("bravo-test", proc.stdout)

    def test_03_extended_thinking(self):
        cmd = [CLI_PATH, "-n", "Are you running with extended thinking enabled? Answer briefly."]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        content = proc.stdout.lower()
        self.assertTrue(
            "thinking" in content or "yes" in content or "reason" in content,
            f"Unexpected output: {proc.stdout[:200]}"
        )

    def test_04_image_attachment(self):
        cmd = [CLI_PATH, "-f", IMAGE_PATH, "What is the document name in this screenshot?"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("Quarterly Report_20201231", proc.stdout)

    def test_05_pdf_attachment(self):
        cmd = [CLI_PATH, "-f", PDF_PATH, "--no-thinking", "What is the exact text inside this PDF?"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("Gemini Web Bridge PDF Test: Success", proc.stdout)

    def test_06_alias_gwb(self):
        cmd = ["gwb", "--no-thinking", "output exactly: charlie-test"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("charlie-test", proc.stdout)

    def test_07_relative_path_attachment(self):
        cwd = os.path.dirname(os.path.abspath(__file__))
        cmd = [CLI_PATH, "-f", "test_sample.pdf", "--no-thinking", "What is the exact text inside this PDF?"]
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertIn("Gemini Web Bridge PDF Test: Success", proc.stdout)

if __name__ == "__main__":
    unittest.main()
