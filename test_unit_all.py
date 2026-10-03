#!/usr/bin/env python3
"""Unit tests for all internal functions of gemini-web-bridge."""

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import server
from gemini_client import query_gemini


class TestServerFunctions(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.sample_png = os.path.join(self.test_dir.name, "test.png")
        with open(self.sample_png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

    def tearDown(self):
        self.test_dir.cleanup()

    # 1. file_to_data_url
    def test_file_to_data_url_valid(self):
        url = server.file_to_data_url(self.sample_png)
        self.assertTrue(url.startswith("data:image/png;base64,"))
        payload = url.split(",", 1)[1]
        self.assertEqual(base64.b64decode(payload), b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

    def test_file_to_data_url_missing(self):
        with self.assertRaises(FileNotFoundError):
            server.file_to_data_url(os.path.join(self.test_dir.name, "nonexistent.png"))

    # 2. extract_image_payload
    def test_extract_image_payload_image_path(self):
        body = {"image_path": self.sample_png}
        res = server.extract_image_payload(body, [])
        self.assertIsNotNone(res)
        self.assertTrue(res.startswith("data:image/png;base64,"))

    def test_extract_image_payload_image_data(self):
        body = {"image_data": "iVBORw0KGgoAAAANSUhEUg=="}
        res = server.extract_image_payload(body, [])
        self.assertEqual(res, "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==")

    def test_extract_image_payload_openai_format(self):
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this:"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,12345"}}
            ]
        }]
        res = server.extract_image_payload({}, messages)
        self.assertEqual(res, "data:image/jpeg;base64,12345")

    def test_extract_image_payload_none(self):
        self.assertIsNone(server.extract_image_payload({}, []))

    # 3. process_thought_output
    def test_process_thought_output_native(self):
        raw = "> Thinking Process:\nAnalyzing problem step-by-step\n\n42"
        self.assertEqual(server.process_thought_output(raw, include_thoughts=False), "42")
        self.assertIn("> Thinking Process:\nAnalyzing problem step-by-step", server.process_thought_output(raw, include_thoughts=True))

    def test_process_thought_output_structured(self):
        raw = "Thinking Process:\nDeconstructing equation\nFinal Answer:\nx = 7"
        self.assertEqual(server.process_thought_output(raw, include_thoughts=False), "x = 7")
        self.assertIn("> Thinking Process:\nDeconstructing equation\n\nx = 7", server.process_thought_output(raw, include_thoughts=True))

    def test_process_thought_output_xml_tags(self):
        raw = "<thought>Calculating 2+2</thought>Result is 4."
        self.assertEqual(server.process_thought_output(raw, include_thoughts=False), "Result is 4.")
        self.assertIn("> Thinking Process:\nCalculating 2+2\n\nResult is 4.", server.process_thought_output(raw, include_thoughts=True))

    def test_process_thought_output_plain(self):
        raw = "Simple answer without thoughts."
        self.assertEqual(server.process_thought_output(raw, include_thoughts=False), raw)
        self.assertEqual(server.process_thought_output("", include_thoughts=True), "")

    # 4. format_tools_prompt
    def test_format_tools_prompt(self):
        tools = [{
            "function": {
                "name": "exec_cmd",
                "description": "Run shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string", "description": "Command string"}
                    },
                    "required": ["cmd"]
                }
            }
        }]
        prompt = server.format_tools_prompt(tools)
        self.assertIn("Tool `exec_cmd`", prompt)
        self.assertIn("cmd (string (required))", prompt)
        self.assertIn("<tool_call>", prompt)

    def test_format_tools_prompt_empty(self):
        self.assertEqual(server.format_tools_prompt([]), "")

    # 5. parse_tool_calls
    def test_parse_tool_calls_standard(self):
        text = "Hello\n<tool_call>\n{\"name\": \"exec_cmd\", \"arguments\": {\"cmd\": \"whoami\"}}\n</tool_call>\nBye"
        cleaned, calls = server.parse_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "exec_cmd")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"cmd": "whoami"})
        self.assertNotIn("<tool_call>", cleaned)
        self.assertIn("Hello", cleaned)

    def test_parse_tool_calls_markdown_fence(self):
        text = "<tool_call>\n```json\n{\"name\": \"read\", \"arguments\": {\"path\": \"/tmp\"}}\n```\n</tool_call>"
        _, calls = server.parse_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "read")

    def test_parse_tool_calls_fallback_fence(self):
        text = "```tool_call\n{\"name\": \"ping\", \"arguments\": {}}\n```"
        _, calls = server.parse_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "ping")

    def test_parse_tool_calls_invalid_json(self):
        text = "<tool_call>not-valid-json</tool_call>"
        cleaned, calls = server.parse_tool_calls(text)
        self.assertEqual(len(calls), 0)

    # 6. extract_prompt_for_gemini
    def test_extract_prompt_single_message(self):
        msgs = [{"role": "user", "content": "What is Python?"}]
        prompt, img = server.extract_prompt_for_gemini(msgs, new_chat=True)
        self.assertEqual(prompt, "What is Python?")
        self.assertIsNone(img)

    def test_extract_prompt_multiturn_continuation(self):
        msgs = [
            {"role": "user", "content": "Query 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Query 2"}
        ]
        prompt, _ = server.extract_prompt_for_gemini(msgs, new_chat=False)
        self.assertEqual(prompt, "Query 2")

    def test_extract_prompt_tool_result_continuation(self):
        msgs = [
            {"role": "user", "content": "Query"},
            {"role": "assistant", "content": "Calling tool", "tool_calls": [{"function": {"name": "test", "arguments": "{}"}}]},
            {"role": "tool", "name": "test", "content": "output 123"}
        ]
        prompt, _ = server.extract_prompt_for_gemini(msgs, new_chat=False)
        self.assertIn("[Tool Result: test]\noutput 123", prompt)

    def test_extract_prompt_empty(self):
        prompt, img = server.extract_prompt_for_gemini([], new_chat=True)
        self.assertEqual(prompt, "Hello")
        self.assertIsNone(img)

    # 7. gemini_client.query_gemini
    @patch("gemini_client.urllib.request.urlopen")
    def test_query_gemini(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Mocked bridge response"}}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = query_gemini("Test prompt")
        self.assertEqual(res, "Mocked bridge response")


class TestServerAsyncRoutes(AioHTTPTestCase):

    async def get_application(self):
        return server.init_app()

    async def test_models_endpoint(self):
        resp = await self.client.request("GET", "/v1/models")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["object"], "list")
        model_ids = [m["id"] for m in data["data"]]
        self.assertIn("gemini-thinking-web", model_ids)
        self.assertIn("gemini-web", model_ids)


if __name__ == "__main__":
    unittest.main()
