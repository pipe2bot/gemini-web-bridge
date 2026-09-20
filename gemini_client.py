#!/usr/bin/env python3
"""
Gemini Web Bridge Python Client Helper
Allows any agent or Python script to seamlessly query Gemini Web UI via local bridge.
"""
import json
import urllib.request
import urllib.error

from typing import Optional

BRIDGE_URL = "http://127.0.0.1:8765/v1/chat/completions"

def query_gemini(
    prompt: str,
    system_prompt: Optional[str] = None,
    new_chat: bool = False,
    model: str = "gemini-web",
    image_path: Optional[str] = None,
    image_data: Optional[str] = None
) -> str:
    """
    Sends a query to the Gemini Web Bridge OpenAI endpoint.
    
    :param prompt: User prompt text
    :param system_prompt: Optional system instruction
    :param new_chat: If True, resets conversation thread before sending
    :param model: Model identifier ('gemini-web', 'gemini-thinking-web')
    :param image_path: Optional local file path to image attachment
    :param image_data: Optional base64 data URL or raw base64 string
    :return: Generated text response from Gemini Web UI
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "new_chat": new_chat,
        "stream": False
    }
    if image_path:
        payload["image_path"] = image_path
    elif image_data:
        payload["image_data"] = image_data

    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(BRIDGE_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini Bridge HTTP Error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini Bridge connection failed: {e}. Ensure server.py is running on port 8765.")

if __name__ == "__main__":
    reply = query_gemini("Hello! Confirm Gemini Web Bridge connection.")
    print("[+] Response:", reply)
