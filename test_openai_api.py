#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

def test_models():
    print("[*] Testing GET /v1/models...")
    req = urllib.request.Request("http://127.0.0.1:8765/v1/models")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print("[+] Models response:", json.dumps(data, indent=2))
    except urllib.error.URLError as e:
        print("[-] Error:", e)

def test_chat_completion():
    print("\n[*] Testing POST /v1/chat/completions (OpenAI compatible API)...")
    url = "http://127.0.0.1:8765/v1/chat/completions"
    payload = {
        "model": "gemini-web",
        "messages": [
            {"role": "system", "content": "You are a concise AI assistant."},
            {"role": "user", "content": "What is 2 + 2?"}
        ],
        "new_chat": True
    }
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print("[+] OpenAI Completion Response:")
            print(json.dumps(data, indent=2))
    except urllib.error.HTTPError as e:
        print("[-] HTTP Error:", e.code, e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print("[-] Connection Error:", e)

if __name__ == "__main__":
    test_models()
    test_chat_completion()
