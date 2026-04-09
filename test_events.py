#!/usr/bin/env python3
"""模拟 MCP Server 发送事件，用于测试 Monitor"""

import asyncio
import json
import socket
import os
import time

SOCKET_PATH = "/tmp/agent-monitor.sock"


def make_server():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    srv.listen(5)
    return srv


def accept_all(srv):
    clients = []
    try:
        while True:
            conn, _ = srv.accept()
            clients.append(conn)
            print(f"  Client connected (total: {len(clients)})")
    except BlockingIOError:
        pass
    return clients


def broadcast(clients, event):
    event["timestamp"] = int(time.time() * 1000)
    line = (json.dumps(event) + "\n").encode()
    for c in clients:
        try:
            c.sendall(line)
        except Exception:
            pass


async def main():
    srv = make_server()
    loop = asyncio.get_event_loop()
    print(f"Test server listening on {SOCKET_PATH}")
    print("Start agent-monitor in another terminal...")
    print("Waiting for monitor to connect...")

    # 阻塞等待第一个 client 连接
    clients = []
    conn = await loop.run_in_executor(None, srv.accept)
    clients.append(conn[0])
    srv.setblocking(False)
    print(f"  Client connected! (total: {len(clients)})")

    # 接受可能的额外连接
    try:
        while True:
            c, _ = srv.accept()
            clients.append(c)
            print(f"  Client connected (total: {len(clients)})")
    except BlockingIOError:
        pass

    print("Press Enter to send test events...")
    await loop.run_in_executor(None, input)

    # ── 1. DELEGATE_ROUTE ──
    print("\n>>> 1. DELEGATE_ROUTE event")
    broadcast(clients, {
        "type": "DELEGATE_ROUTE",
        "task": "分析 2026 年 AI Agent 框架的技术趋势和主要竞品",
        "category": "research",
        "model": "gemini",
        "reason": "Gemini 擅长调研，已启用 Google Search 联网",
    })
    await asyncio.sleep(1)

    # ── 2. Gemini 非流式调用 ──
    print(">>> 2. Gemini non-streaming call")
    broadcast(clients, {
        "type": "AGENT_START", "agent": "gemini",
        "model": "gemini-3-flash-preview",
        "prompt": "分析 2026 年 AI Agent 框架的技术趋势",
        "systemPrompt": "You are a senior tech analyst",
    })
    await asyncio.sleep(2)
    broadcast(clients, {
        "type": "AGENT_END", "agent": "gemini",
        "model": "gemini-3-flash-preview",
        "content": "2026 年 AI Agent 框架趋势：\n1. MCP 协议成为事实标准\n2. 异构多模型协作兴起\n3. 本地+云混合部署",
        "tokens": {"prompt": 150, "completion": 420, "total": 570},
        "duration_ms": 3200,
        "cost_usd": 0.000183,
    })
    await asyncio.sleep(1)

    # ── 3. DeepSeek 流式调用 ──
    print(">>> 3. DeepSeek streaming call (AGENT_CHUNK)")
    broadcast(clients, {
        "type": "AGENT_START", "agent": "deepseek",
        "model": "deepseek-chat",
        "prompt": "写一个 Python async socket client",
        "systemPrompt": "",
    })
    chunks = [
        "```python\n",
        "import asyncio\n\n",
        "async def connect():\n",
        "    reader, writer = await asyncio.open_unix_connection(",
        "'/tmp/test.sock')\n",
        "    data = await reader.read(1024)\n",
        "    print(data.decode())\n",
        "```",
    ]
    for chunk in chunks:
        broadcast(clients, {"type": "AGENT_CHUNK", "agent": "deepseek", "delta": chunk})
        await asyncio.sleep(0.15)
    await asyncio.sleep(0.5)
    broadcast(clients, {
        "type": "AGENT_END", "agent": "deepseek",
        "model": "deepseek-chat",
        "tokens": {"prompt": 80, "completion": 200, "total": 280},
        "duration_ms": 1800,
        "cost_usd": 0.000067,
    })
    await asyncio.sleep(1)

    # ── 4. AGENT_RETRY + 最终成功 ──
    print(">>> 4. Kimi retry then succeed")
    broadcast(clients, {
        "type": "AGENT_START", "agent": "kimi",
        "model": "moonshot-v1-32k",
        "prompt": "今天有什么科技新闻",
        "systemPrompt": "",
    })
    await asyncio.sleep(0.5)
    broadcast(clients, {
        "type": "AGENT_RETRY", "agent": "kimi",
        "attempt": 1, "status": 429, "wait": 2000,
    })
    await asyncio.sleep(2)
    broadcast(clients, {
        "type": "AGENT_RETRY", "agent": "kimi",
        "attempt": 2, "status": 429, "wait": 4000,
    })
    await asyncio.sleep(2)
    broadcast(clients, {
        "type": "AGENT_END", "agent": "kimi",
        "model": "moonshot-v1-32k",
        "content": "今日科技新闻：Claude Code 发布异构多模型 MCP 协作功能...",
        "tokens": {"prompt": 120, "completion": 85, "total": 205},
        "duration_ms": 6500,
        "cost_usd": 0.000205,
    })
    await asyncio.sleep(1)

    # ── 5. 动态 agent 注册（未知 agent） ──
    print(">>> 5. Unknown agent 'qwen' — dynamic registration")
    broadcast(clients, {
        "type": "AGENT_START", "agent": "qwen",
        "model": "qwen-max",
        "prompt": "用通义千问测试动态注册",
        "systemPrompt": "",
    })
    await asyncio.sleep(1.5)
    # 流式 chunk
    for chunk in ["动态注册", "测试成功！", "新 agent 卡片", "已自动创建。"]:
        broadcast(clients, {"type": "AGENT_CHUNK", "agent": "qwen", "delta": chunk})
        await asyncio.sleep(0.2)
    await asyncio.sleep(0.5)
    broadcast(clients, {
        "type": "AGENT_END", "agent": "qwen",
        "model": "qwen-max",
        "tokens": {"prompt": 50, "completion": 30, "total": 80},
        "duration_ms": 2100,
        "cost_usd": 0.000040,
    })
    await asyncio.sleep(1)

    # ── 6. AGENT_ERROR ──
    print(">>> 6. DeepSeek error")
    broadcast(clients, {
        "type": "AGENT_START", "agent": "deepseek",
        "model": "deepseek-chat",
        "prompt": "This will fail",
        "systemPrompt": "",
    })
    await asyncio.sleep(0.5)
    broadcast(clients, {
        "type": "AGENT_ERROR", "agent": "deepseek",
        "error": "API rate limit exceeded",
        "errType": "rate_limit",
    })

    print("\nAll test events sent! Check the monitor.")
    print("  - Gemini: non-streaming call")
    print("  - DeepSeek: streaming (AGENT_CHUNK) + error")
    print("  - Kimi: retry x2 then succeed")
    print("  - Qwen: dynamic registration + streaming")
    print("  - DELEGATE_ROUTE in event log")
    print("  - Session summary should show totals")
    await asyncio.sleep(5)

    for c in clients:
        c.close()
    srv.close()
    os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    asyncio.run(main())
