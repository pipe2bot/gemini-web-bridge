#!/usr/bin/env python3
import asyncio
import json
import sys
import aiohttp

SERVER_URL = "http://127.0.0.1:8765/v1/chat/completions"

async def chat_loop():
    print("=" * 60)
    print("  ⚡ Gemini Web Bridge Interactive Terminal Chat")
    print("  - Type prompt and press Enter")
    print("  - Commands: '/new' or '/reset' to start a new chat session")
    print("  - Commands: '/exit' or 'exit' to quit")
    print("=" * 60 + "\n")

    history = []
    should_reset_next = False

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                user_input = input("\nYou > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting chat...")
                break

            if not user_input:
                continue

            if user_input.lower() in ["/exit", "exit", "quit"]:
                print("Goodbye!")
                break

            if user_input.lower() in ["/new", "/reset"]:
                should_reset_next = True
                history = []
                print("[*] Next prompt will reset Gemini chat session.")
                continue

            history.append({"role": "user", "content": user_input})

            payload = {
                "model": "gemini-web",
                "messages": history,
                "stream": True,
                "new_chat": should_reset_next
            }
            should_reset_next = False

            print("Gemini > ", end="", flush=True)

            try:
                async with session.post(SERVER_URL, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        print(f"\n[-] Error ({resp.status}): {err_text}")
                        continue

                    full_response = ""
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                delta = chunk_json["choices"][0]["delta"].get("content", "")
                                if delta:
                                    print(delta, end="", flush=True)
                                    full_response += delta
                            except json.JSONDecodeError:
                                pass

                    print()  # newline
                    if full_response:
                        history.append({"role": "assistant", "content": full_response})

            except aiohttp.ClientError as e:
                print(f"\n[-] Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(chat_loop())
