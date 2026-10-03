#!/usr/bin/env python3
import json
from server import format_tools_prompt, parse_tool_calls, extract_prompt_for_gemini

def test_tool_formatting():
    tools = [{
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Execute shell commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"}
                },
                "required": ["command"]
            }
        }
    }]
    prompt = format_tools_prompt(tools)
    assert "- Tool `terminal`: Execute shell commands." in prompt
    assert "* command (string (required)) - Shell command to run" in prompt
    assert "<tool_call>" in prompt
    print("[PASS] Tool formatting test passed.")

def test_tool_parsing_single():
    text = """Let me check files.
<tool_call>
{"name": "terminal", "arguments": {"command": "ls -l"}}
</tool_call>
Done."""
    cleaned, tc = parse_tool_calls(text)
    assert len(tc) == 1
    assert tc[0]["function"]["name"] == "terminal"
    assert json.loads(tc[0]["function"]["arguments"]) == {"command": "ls -l"}
    assert "<tool_call>" not in cleaned
    assert "Let me check files." in cleaned
    print("[PASS] Tool parsing single test passed.")

def test_tool_parsing_markdown():
    text = """<tool_call>
```json
{
  "name": "read_file",
  "arguments": {"path": "/etc/hosts"}
}
```
</tool_call>"""
    cleaned, tc = parse_tool_calls(text)
    assert len(tc) == 1
    assert tc[0]["function"]["name"] == "read_file"
    assert json.loads(tc[0]["function"]["arguments"]) == {"path": "/etc/hosts"}
    print("[PASS] Tool parsing markdown codeblock test passed.")

def test_tool_parsing_fallback():
    text = """```tool_call
{
  "name": "patch",
  "arguments": {"path": "a.txt", "old": "1", "new": "2"}
}
```"""
    cleaned, tc = parse_tool_calls(text)
    assert len(tc) == 1
    assert tc[0]["function"]["name"] == "patch"
    print("[PASS] Tool parsing fallback test passed.")

def test_extract_prompt_with_tools():
    messages = [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Check files"}
    ]
    tools = [{
        "type": "function",
        "function": {"name": "terminal", "description": "Run shell", "parameters": {}}
    }]
    full_prompt, _ = extract_prompt_for_gemini(messages, False, tools=tools)
    assert "Available Tools:" in full_prompt
    assert "Check files" in full_prompt
    print("[PASS] Extract prompt with tools passed.")

def test_extract_prompt_tool_result():
    messages = [
        {"role": "system", "content": "You are Hermes."},
        {"role": "user", "content": "Check files"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "terminal", "arguments": '{"command": "ls"}'}}]},
        {"role": "tool", "name": "terminal", "content": "file1.txt\nfile2.txt"}
    ]
    full_prompt, _ = extract_prompt_for_gemini(messages, False)
    assert "[Tool Result: terminal]" in full_prompt
    assert "file1.txt" in full_prompt
    print("[PASS] Extract prompt tool result passed.")

if __name__ == "__main__":
    test_tool_formatting()
    test_tool_parsing_single()
    test_tool_parsing_markdown()
    test_tool_parsing_fallback()
    test_extract_prompt_with_tools()
    test_extract_prompt_tool_result()
    print("ALL TESTS PASSED!")
