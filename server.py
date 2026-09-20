#!/usr/bin/env python3
import asyncio
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import time
import uuid
from aiohttp import web

def file_to_data_url(file_path: str) -> str:
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Local image file not found: {file_path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png"

    with open(path, "rb") as f:
        encoded_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded_data}"

def extract_image_payload(body: dict, messages: list) -> str | None:
    for key in ["image_path", "attachment", "attachments"]:
        val = body.get(key)
        if val:
            target = val[0] if isinstance(val, list) else val
            if isinstance(target, str):
                return file_to_data_url(target) if os.path.isfile(os.path.expanduser(target)) else target

    if body.get("image_data"):
        raw_val = body["image_data"]
        if isinstance(raw_val, str):
            if os.path.isfile(os.path.expanduser(raw_val)):
                return file_to_data_url(raw_val)
            if raw_val.startswith("data:"):
                return raw_val
            return f"data:image/png;base64,{raw_val}"

    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    img_info = part.get("image_url", {})
                    url = img_info.get("url") if isinstance(img_info, dict) else img_info
                    if not url:
                        continue
                    if url.startswith("data:"):
                        return url
                    if os.path.isfile(os.path.expanduser(url)):
                        return file_to_data_url(url)
                    return url
    return None

CONNECTED_EXTENSIONS = set()
PENDING_REQUESTS = {}

def process_thought_output(text: str, include_thoughts: bool) -> str:
    if not text:
        return ""
    # 1. Native formatted: > Thinking Process:\n...\n\n<answer>
    native_match = re.match(r"^>\s*Thinking Process:\s*\n(.*?)\n\n([\s\S]*)$", text, re.DOTALL)
    if native_match:
        thoughts = native_match.group(1).strip()
        answer = native_match.group(2).strip()
        return f"> Thinking Process:\n{thoughts}\n\n{answer}" if (include_thoughts and thoughts) else answer

    # 2. Structured delimiters: Thinking Process ... Final Answer
    section_match = re.search(
        r"(?:^|\b)(?:##\s*|>\s*)?Thinking Process:?\s*(.*?)(?:(?:##\s*|>\s*)?Final Answer:?\s*([\s\S]*)|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if section_match and section_match.group(2) is not None:
        thoughts = section_match.group(1).strip()
        answer = section_match.group(2).strip()
        return f"> Thinking Process:\n{thoughts}\n\n{answer}" if (include_thoughts and thoughts) else (answer or thoughts)

    # 3. XML tags <thought>...</thought>
    tag_match = re.search(r"<thought>(.*?)</thought>([\s\S]*)", text, re.IGNORECASE | re.DOTALL)
    if tag_match:
        thoughts = tag_match.group(1).strip()
        answer = tag_match.group(2).strip()
        return f"> Thinking Process:\n{thoughts}\n\n{answer}" if (include_thoughts and thoughts) else (answer or thoughts)

    return text

def extract_prompt_for_gemini(messages, new_chat):
    if not messages:
        return "Hello", None

    extracted_image_data = None

    if not new_chat and len(messages) > 1:
        target_messages = []
        for m in messages:
            if m.get("role") == "system":
                target_messages.append(m)
        target_messages.append(messages[-1])
    else:
        target_messages = messages

    prompt_parts = []

    for msg in target_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_blocks = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_blocks.append(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        img_obj = block.get("image_url", {})
                        extracted_image_data = img_obj.get("url")
            combined_text = " ".join(text_blocks)
            prompt_parts.append(combined_text)
        elif isinstance(content, str):
            if role == "system":
                prompt_parts.append(f"System instruction: {content}")
            else:
                prompt_parts.append(content)

    full_prompt = "\n\n".join(prompt_parts) if prompt_parts else "Hello"
    return full_prompt, extracted_image_data

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    role = None
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")
                msg_role = data.get("role")

                if msg_role == "extension" or msg_type == "register":
                    role = "extension"
                    CONNECTED_EXTENSIONS.add(ws)
                    print("[Server] Extension WebSocket connected.")
                    await ws.send_json({"status": "registered"})
                    continue

                if role == "extension":
                    req_id = data.get("id")
                    if req_id in PENDING_REQUESTS:
                        queue, future = PENDING_REQUESTS[req_id]
                        if msg_type == "chunk":
                            await queue.put({"type": "chunk", "text": data.get("text")})
                        elif msg_type == "complete":
                            await queue.put({"type": "complete", "text": data.get("text")})
                            if not future.done():
                                future.set_result(data.get("text"))
                        elif msg_type == "error":
                            err_msg = data.get("error", "Unknown error")
                            await queue.put({"type": "error", "error": err_msg})
                            if not future.done():
                                future.set_exception(RuntimeError(err_msg))

                elif msg_role == "agent" or msg_type == "generate":
                    role = "agent"
                    prompt = data.get("prompt")
                    new_chat = data.get("new_chat", False)
                    image_data = data.get("image_data") or data.get("image") or data.get("image_path")
                    if image_data and isinstance(image_data, str) and os.path.isfile(os.path.expanduser(image_data)):
                        image_data = file_to_data_url(image_data)
                    include_thoughts = data.get("include_thoughts", False)
                    thinking = data.get("thinking", None)
                    req_id = str(uuid.uuid4())
                    queue = asyncio.Queue()
                    loop = asyncio.get_running_loop()
                    future = loop.create_future()

                    PENDING_REQUESTS[req_id] = (queue, future)

                    if not CONNECTED_EXTENSIONS:
                        await ws.send_json({"status": "error", "error": "No extension connected."})
                        continue

                    ext_ws = next(iter(CONNECTED_EXTENSIONS))
                    await ext_ws.send_json({
                        "command": "generate",
                        "id": req_id,
                        "prompt": prompt,
                        "new_chat": new_chat,
                        "image_data": image_data,
                        "include_thoughts": include_thoughts,
                        "thinking": thinking,
                        "model": data.get("model", "gemini-web")
                    })

                    try:
                        while True:
                            item = await queue.get()
                            if item["type"] == "chunk":
                                await ws.send_json({"status": "chunk", "id": req_id, "text": item["text"]})
                            elif item["type"] == "complete":
                                await ws.send_json({"status": "complete", "id": req_id, "text": item["text"]})
                                break
                            elif item["type"] == "error":
                                await ws.send_json({"status": "error", "id": req_id, "error": item["error"]})
                                break
                    finally:
                        PENDING_REQUESTS.pop(req_id, None)

            elif msg.type == web.WSMsgType.ERROR:
                print(f"[Server] WebSocket error: {ws.exception()}")

    finally:
        if ws in CONNECTED_EXTENSIONS:
            CONNECTED_EXTENSIONS.remove(ws)
            print("[Server] Extension WebSocket disconnected.")

    return ws

async def handle_models(request):
    return web.json_response({
        "object": "list",
        "data": [
          {"id": "gemini-web", "object": "model", "created": int(time.time()), "owned_by": "google"},
          {"id": "gemini-thinking-web", "object": "model", "created": int(time.time()), "owned_by": "google"}
        ]
    })

async def handle_chat_completions(request):
    if not CONNECTED_EXTENSIONS:
        return web.json_response({"error": {"message": "No Chrome/Firefox Extension connected to Gemini bridge."}}, status=503)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": {"message": "Invalid JSON body"}}, status=400)

    messages = body.get("messages", [])
    model = body.get("model", "gemini-web")
    stream = body.get("stream", False)
    new_chat = body.get("new_chat", False)
    include_thoughts = body.get("include_thoughts", False)
    thinking = body.get("thinking", None)

    if model in ["gemini-thinking", "gemini-thinking-web", "gemini-2.0-flash-thinking"]:
        thinking = True
    elif model in ["gemini-web", "gemini-flash", "gemini-1.5-flash", "gemini-2.0-flash"] and thinking is None:
        thinking = False

    full_prompt, extracted_image_data = extract_prompt_for_gemini(messages, new_chat)
    image_data = extract_image_payload(body, messages) or extracted_image_data
    req_id = f"chatcmpl-{uuid.uuid4()}"

    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    PENDING_REQUESTS[req_id] = (queue, future)

    ext_ws = next(iter(CONNECTED_EXTENSIONS))
    await ext_ws.send_json({
        "command": "generate",
        "id": req_id,
        "prompt": full_prompt,
        "new_chat": new_chat,
        "image_data": image_data,
        "include_thoughts": include_thoughts,
        "thinking": thinking,
        "model": model
    })

    if stream:
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
        await response.prepare(request)

        try:
            last_length = 0
            while True:
                item = await queue.get()
                if item["type"] == "chunk":
                    new_text = item["text"][last_length:]
                    last_length = len(item["text"])
                    chunk_data = {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": new_text},
                            "finish_reason": None
                        }]
                    }
                    await response.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8"))
                elif item["type"] == "complete":
                    final_chunk = {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    await response.write(f"data: {json.dumps(final_chunk)}\n\n".encode("utf-8"))
                    await response.write(b"data: [DONE]\n\n")
                    break
                elif item["type"] == "error":
                    err_data = {"error": {"message": item["error"]}}
                    await response.write(f"data: {json.dumps(err_data)}\n\n".encode("utf-8"))
                    break
        finally:
            PENDING_REQUESTS.pop(req_id, None)

        return response

    else:
        try:
            full_text = await asyncio.wait_for(future, timeout=120.0)
            processed_text = process_thought_output(full_text, include_thoughts)
            return web.json_response({
                "id": req_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": processed_text
                    },
                    "finish_reason": "stop"
                }]
            })
        except asyncio.TimeoutError:
            return web.json_response({"error": {"message": "Request timed out waiting for Gemini response."}}, status=504)
        except Exception as e:
            return web.json_response({"error": {"message": str(e)}}, status=500)
        finally:
            PENDING_REQUESTS.pop(req_id, None)

def init_app():
    app = web.Application()
    app.router.add_get("/", websocket_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    return app

if __name__ == "__main__":
    app = init_app()
    print("[Server] Gemini Web Bridge starting HTTP & WebSocket server on http://127.0.0.1:8765")
    web.run_app(app, host="127.0.0.1", port=8765, print=None)
