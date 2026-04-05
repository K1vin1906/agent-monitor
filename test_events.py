#!/usr/bin/env python3
"""模拟 MCP Server 发送事件，用于测试 Monitor"""

import asyncio
import json
import time

SOCKET_PATH = "/tmp/agent-monitor.sock"


async def send_event(writer, event):
    event["timestamp"] = int(time.time() * 1000)
    writer.write((json.dumps(event) + "\n").encode())
    await writer.drain()


async def main():
    print(f"Connecting to {SOCKET_PATH}...")

    # 先启动一个模拟的 UDS server（模拟 MCP Server 端）
    import socket, os
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    clients = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    server.setblocking(False)

    loop = asyncio.get_event_loop()

    print(f"Test server listening on {SOCKET_PATH}")
    print("Start agent-monitor in another terminal, then press Enter to send test events...")
    await loop.run_in_executor(None, input)

    # Accept any connected clients
    try:
        while True:
            conn, _ = server.accept()
            clients.append(conn)
            print(f"Client connected (total: {len(clients)})")
    except BlockingIOError:
        pass

    if not clients:
        print("No monitor connected. Start the monitor first!")
        server.close()
        os.unlink(SOCKET_PATH)
        return

    def broadcast(event):
        event["timestamp"] = int(time.time() * 1000)
        line = (json.dumps(event) + "\n").encode()
        for c in clients:
            try:
                c.sendall(line)
            except:
                pass

    # Simulate Gemini call
    print("\n>>> Simulating Gemini call...")
    broadcast({"type": "AGENT_START", "agent": "gemini", "model": "gemini-3-flash-preview",
               "prompt": "Analyze the architecture of a TUI monitoring tool", "systemPrompt": "You are a senior architect"})
    await asyncio.sleep(3)
    broadcast({"type": "AGENT_END", "agent": "gemini", "model": "gemini-3-flash-preview",
               "content": "Here's my analysis:\n1. Use Unix Domain Sockets for IPC\n2. Textual for TUI rendering\n3. AsyncIO for concurrent processing",
               "tokens": {"prompt": 120, "completion": 350, "total": 470}})

    await asyncio.sleep(1)

    # Simulate DeepSeek call
    print(">>> Simulating DeepSeek call...")
    broadcast({"type": "AGENT_START", "agent": "deepseek", "model": "deepseek-chat",
               "prompt": "Write a Python async socket client", "systemPrompt": ""})
    await asyncio.sleep(2)
    broadcast({"type": "AGENT_END", "agent": "deepseek", "model": "deepseek-chat",
               "content": "```python\nimport asyncio\n\nasync def connect():\n    reader, writer = await asyncio.open_unix_connection('/tmp/test.sock')\n    data = await reader.read(1024)\n    print(data.decode())\n```",
               "tokens": {"prompt": 80, "completion": 200, "total": 280}})

    await asyncio.sleep(1)

    # Simulate error
    print(">>> Simulating error...")
    broadcast({"type": "AGENT_START", "agent": "deepseek", "model": "deepseek-chat",
               "prompt": "This will fail", "systemPrompt": ""})
    await asyncio.sleep(1)
    broadcast({"type": "AGENT_ERROR", "agent": "deepseek", "error": "API rate limit exceeded"})

    print("\nDone! Check the monitor.")
    await asyncio.sleep(5)

    for c in clients:
        c.close()
    server.close()
    os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    asyncio.run(main())
