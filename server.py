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

def format_tools_prompt(tools: list) -> str:
    if not tools:
        return ""
    lines = [
        "You are an AI assistant with planning capabilities. When a task requires external data, execution, or file operations, select the appropriate tool and output the execution command strictly as a JSON object inside <tool_call> tags.",
        "",
        "Available Tools:"
    ]
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name", "")
        desc = (fn.get("description") or "").strip().split("\n")[0]
        params = fn.get("parameters", {})
        props = params.get("properties", {})
        req = set(params.get("required", []))
        param_strs = []
        for p, info in props.items():
            ptype = info.get("type", "any")
            req_str = " (required)" if p in req else ""
            pdesc = f" - {info.get('description')}" if info.get("description") else ""
            param_strs.append(f"  * {p} ({ptype}{req_str}){pdesc}")
        lines.append(f"- Tool `{name}`: {desc}")
        if param_strs:
            lines.extend(param_strs)
    lines.append("")
    lines.append("Tool Call Format:")
    lines.append("To call a tool, output:")
    lines.append("<tool_call>")
    lines.append('{"name": "tool_name", "arguments": {"param": "value"}}')
    lines.append("</tool_call>")
    lines.append("If no tool is needed, respond with standard markdown without <tool_call> tags.")
    return "\n".join(lines)

def parse_tool_calls(text: str):
    tool_calls = []
    pattern = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    cleaned_text = pattern.sub("", text).strip()

    for match in matches:
        raw_json = match.group(1).strip()
        if raw_json.startswith("```"):
            raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
            raw_json = re.sub(r"\s*```$", "", raw_json)
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and "name" in parsed:
                args = parsed.get("arguments", {})
                if not isinstance(args, (str, dict)):
                    args = {}
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": parsed["name"],
                        "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                    }
                })
        except Exception:
            continue

    if not tool_calls:
        fb_pattern = re.compile(r"```tool_call\s*([\s\S]*?)\s*```", re.IGNORECASE)
        fb_matches = list(fb_pattern.finditer(text))
        if fb_matches:
            cleaned_text = fb_pattern.sub("", text).strip()
            for match in fb_matches:
                raw_json = match.group(1).strip()
                try:
                    parsed = json.loads(raw_json)
                    if isinstance(parsed, dict) and "name" in parsed:
                        args = parsed.get("arguments", {})
                        tool_calls.append({
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": parsed["name"],
                                "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                            }
                        })
                except Exception:
                    pass

    return cleaned_text, tool_calls

def extract_prompt_for_gemini(messages, new_chat, tools=None):
    if not messages:
        return "Hello", None

    extracted_image_data = None

    if not new_chat and len(messages) > 1:
        trailing_tools = []
        for m in reversed(messages):
            if m.get("role") == "tool":
                trailing_tools.append(m)
            else:
                break
        trailing_tools.reverse()

        target_messages = []
        for m in messages:
            if m.get("role") == "system":
                target_messages.append(m)

        if trailing_tools:
            target_messages.extend(trailing_tools)
        else:
            target_messages.append(messages[-1])
    else:
        target_messages = messages

    prompt_parts = []

    if tools:
        prompt_parts.append(format_tools_prompt(tools))

    for msg in target_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "tool":
            tool_name = msg.get("name") or "tool"
            prompt_parts.append(f"[Tool Result: {tool_name}]\n{content}")
            continue

        if role == "assistant" and msg.get("tool_calls"):
            tc_blocks = []
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                tc_blocks.append(f"<tool_call>\n{json.dumps({'name': fn.get('name'), 'arguments': args})}\n</tool_call>")
            if content:
                prompt_parts.append(content)
            prompt_parts.append("\n".join(tc_blocks))
            continue

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
                        elif msg_type == "heartbeat":
                            await queue.put({"type": "heartbeat"})
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

    full_prompt, extracted_image_data = extract_prompt_for_gemini(messages, new_chat, tools=body.get("tools"))
    image_data = extract_image_payload(body, messages) or extracted_image_data
    req_id = f"chatcmpl-{uuid.uuid4()}"
    tools = body.get("tools")

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
            if tools:
                full_text = ""
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        await response.write(b": keep-alive\n\n")
                        continue

                    if item["type"] == "heartbeat":
                        await response.write(b": keep-alive\n\n")
                        continue
                    elif item["type"] == "chunk":
                        full_text = item["text"]
                    elif item["type"] == "complete":
                        full_text = item.get("text", full_text)
                        cleaned_text, tool_calls = parse_tool_calls(full_text)
                        if tool_calls:
                            chunk_data = {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "role": "assistant",
                                        "content": cleaned_text.strip() or None,
                                        "tool_calls": [
                                            {
                                                "index": i,
                                                "id": tc["id"],
                                                "type": "function",
                                                "function": {
                                                    "name": tc["function"]["name"],
                                                    "arguments": tc["function"]["arguments"]
                                                }
                                            }
                                            for i, tc in enumerate(tool_calls)
                                        ]
                                    },
                                    "finish_reason": None
                                }]
                            }
                            await response.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8"))
                            final_chunk = {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "tool_calls"
                                }]
                            }
                            await response.write(f"data: {json.dumps(final_chunk)}\n\n".encode("utf-8"))
                        else:
                            proc = process_thought_output(full_text, include_thoughts)
                            chunk_data = {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": proc},
                                    "finish_reason": None
                                }]
                            }
                            await response.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8"))
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
            else:
                last_length = 0
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        # Keep-alive SSE comment ping every 10s to keep HTTP/TCP socket alive
                        await response.write(b": keep-alive\n\n")
                        continue

                    if item["type"] == "heartbeat":
                        await response.write(b": keep-alive\n\n")
                        continue
                    elif item["type"] == "chunk":
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
            full_text = await asyncio.wait_for(future, timeout=300.0)
            processed_text = process_thought_output(full_text, include_thoughts)
            cleaned_text, tool_calls = parse_tool_calls(processed_text) if tools else (processed_text, [])

            if tool_calls:
                msg = {
                    "role": "assistant",
                    "content": cleaned_text.strip() or None,
                    "tool_calls": tool_calls
                }
                finish_reason = "tool_calls"
            else:
                msg = {
                    "role": "assistant",
                    "content": processed_text
                }
                finish_reason = "stop"

            return web.json_response({
                "id": req_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": msg,
                    "finish_reason": finish_reason
                }]
            })
        except asyncio.TimeoutError:
            return web.json_response({"error": {"message": "Request timed out waiting for Gemini response (300s limit)."}}, status=504)
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
