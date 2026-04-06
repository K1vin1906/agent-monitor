#!/usr/bin/env python3
"""Simulate MCP Server socket for Agent Monitor demo recording."""

import asyncio
import json
import os
import time

SOCKET_PATH = "/tmp/agent-monitor.sock"

async def send_event(writer, event):
    data = json.dumps(event) + "\n"
    writer.write(data.encode())
    await writer.drain()

async def handle_client(reader, writer):
    ts = lambda: int(time.time() * 1000)

    await asyncio.sleep(2)  # let monitor settle

    prompt = "Explain the difference between concurrency and parallelism in Go"

    # Start DeepSeek + Gemini
    await send_event(writer, {
        "type": "AGENT_START", "agent": "deepseek",
        "model": "deepseek-chat", "prompt": prompt, "timestamp": ts()
    })
    await asyncio.sleep(0.3)
    await send_event(writer, {
        "type": "AGENT_START", "agent": "gemini",
        "model": "gemini-2.5-flash", "prompt": prompt, "timestamp": ts()
    })

    ds_chunks = [
        "In Go, **concurrency** ", "is about dealing with ",
        "multiple things at once, ", "while **parallelism** is ",
        "about doing multiple things ", "at once.\n\n",
        "Go's goroutines are ", "concurrent by design — ",
        "they multiplex onto OS threads ", "via the scheduler. ",
        "True parallelism requires ", "multiple CPU cores.\n\n",
        "Key distinction:\n",
        "- `go func()` = concurrent\n",
        "- GOMAXPROCS > 1 = parallel",
    ]

    gm_chunks = [
        "Great question! ", "These are often confused.\n\n",
        "**Concurrency** = structure. ", "Designing your program to handle ",
        "multiple tasks that can progress ", "independently.\n\n",
        "**Parallelism** = execution. ", "Actually running multiple ",
        "computations simultaneously on ", "different processors.\n\n",
        "Rob Pike: ", "\"Concurrency is about dealing ",
        "with lots of things at once. ", "Parallelism is about doing ",
        "lots of things at once.\"",
    ]

    await asyncio.sleep(0.8)
    for i in range(max(len(ds_chunks), len(gm_chunks))):
        if i < len(ds_chunks):
            await send_event(writer, {
                "type": "AGENT_CHUNK", "agent": "deepseek",
                "delta": ds_chunks[i], "timestamp": ts()
            })
        await asyncio.sleep(0.12)
        if i < len(gm_chunks):
            await send_event(writer, {
                "type": "AGENT_CHUNK", "agent": "gemini",
                "delta": gm_chunks[i], "timestamp": ts()
            })
        await asyncio.sleep(0.12)

    await asyncio.sleep(0.5)
    await send_event(writer, {
        "type": "AGENT_END", "agent": "deepseek",
        "tokens": {"prompt": 42, "completion": 128, "total": 170},
        "duration_ms": 1840, "cost_usd": 0.000048, "timestamp": ts()
    })

    await asyncio.sleep(0.8)
    await send_event(writer, {
        "type": "AGENT_END", "agent": "gemini",
        "tokens": {"prompt": 42, "completion": 195, "total": 237},
        "duration_ms": 2650, "cost_usd": 0.000082, "timestamp": ts()
    })

    await asyncio.sleep(1.5)

    # Kimi with web search
    await send_event(writer, {
        "type": "AGENT_START", "agent": "kimi",
        "model": "moonshot-v1-32k",
        "prompt": "What are the latest changes in Go 1.24?",
        "systemPrompt": "Search the web for recent information",
        "timestamp": ts()
    })

    kimi_chunks = [
        "Based on my web search, ", "Go 1.24 was released in ",
        "February 2025:\n\n",
        "1. **Generic type aliases** ", "fully supported\n",
        "2. **go tool** runs ", "tools from modules\n",
        "3. **Weak pointers** ", "via runtime/weak\n",
        "4. Swiss Tables map ", "for better performance",
    ]

    await asyncio.sleep(1.0)
    for chunk in kimi_chunks:
        await send_event(writer, {
            "type": "AGENT_CHUNK", "agent": "kimi",
            "delta": chunk, "timestamp": ts()
        })
        await asyncio.sleep(0.18)

    await asyncio.sleep(0.5)
    await send_event(writer, {
        "type": "AGENT_END", "agent": "kimi",
        "tokens": {"prompt": 56, "completion": 163, "total": 219},
        "duration_ms": 3200, "cost_usd": 0.000035, "timestamp": ts()
    })

    await asyncio.sleep(10)  # hold for viewing
    writer.close()
    await writer.wait_closed()

async def main():
    # Remove stale socket
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass

    server = await asyncio.start_unix_server(handle_client, SOCKET_PATH)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
