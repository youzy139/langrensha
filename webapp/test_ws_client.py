"""Mock 模式 WS 端到端测试：连上服务器，指定当狼，自动应答直到游戏结束。"""
import asyncio
import json
import sys

import websockets


async def main() -> int:
    got_role = {}
    asks = 0
    async with websockets.connect("ws://127.0.0.1:7100/ws") as ws:
        await ws.send(json.dumps({"t": "start", "config": "6p", "role": "werewolf"}))
        while True:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            except asyncio.TimeoutError:
                print("FAIL: 60s 无消息（卡死）")
                return 1
            t = m.get("t")
            if t == "role":
                got_role = m
                print("role:", m["role_name"], "| 队友:", m.get("mates"))
            elif t == "ask":
                asks += 1
                # 自动应答：选择题选第一个候选人，文本题给固定发言
                text = m["candidates"][0] if m.get("candidates") else "我是好人，过"
                await ws.send(json.dumps({"t": "answer", "text": text}))
            elif t == "game_over":
                print("game_over:", m["winner"], "|", m["reveal"])
            elif t == "review":
                assert len(m["md"]) > 50, "复盘内容为空！"
                print("review: 收到复盘（%d 字）" % len(m["md"]))
                break
    assert got_role.get("role") == "werewolf", "指定当狼失败！"
    assert asks > 0, "没有收到任何提问！"
    print(f"PASS: 指定角色=狼人 ✓, 收到 {asks} 次提问, 对局结束 ✓, 复盘推送 ✓")
    return 0


sys.exit(asyncio.run(main()))
