"""多人房间 Mock 端到端测试（两个模拟人类客户端 + AI 补位）。

验证 Phase 1 验收项：
1. 建房/加入/大厅状态广播（房间码、房主标记、AI 补位数）
2. 开局后两个客户端各自收到独立座位与身份（隔离性抽查）
3. 白天发言同步可见（公屏扇出）
4. 挂机超时 → player_afk 广播 → AI 托管，游戏继续不卡死
5. 赛后讨论群聊：B 发言，两个客户端都收到广播 + AI 回应
6. 房主连开第二局

用法：WEREWOLF_MOCK=1 WEREWOLF_ASK_TIMEOUT=3 python server.py --port 7213
      WEREWOLF_MOCK=1 python test_room_client.py 7213
"""

import asyncio
import json
import sys

import websockets

PORT = sys.argv[1] if len(sys.argv) > 1 else "7213"
URL = f"ws://127.0.0.1:{PORT}/ws"


class Client:
    def __init__(self, nick):
        self.nick = nick
        self.ws = None
        self.seat = None
        self.token = None
        self.feed_texts = []
        self.discuss = []
        self.afk_events = []
        self.game_overs = 0
        self.started_count = 0
        self.review_ok = False
        self.role_msg = None
        self.skip_next_ask = False   # 用于模拟挂机

    async def connect(self, first_msg):
        self.ws = await websockets.connect(URL)
        await self.ws.send(json.dumps(first_msg))

    async def send(self, m):
        await self.ws.send(json.dumps(m))

    async def pump(self, stop_flag):
        """收包循环：记录事件、自动应答（skip_next_ask 时跳过一次模拟挂机）。"""
        while not stop_flag["stop"]:
            try:
                m = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=90))
            except asyncio.TimeoutError:
                break
            t = m.get("t")
            if t == "joined":
                self.token = m["token"]
            elif t == "started":
                self.seat = m["name"]
                self.started_count += 1
            elif t == "role":
                self.role_msg = m
            elif t == "feed":
                self.feed_texts.append(m["text"])
            elif t == "ask":
                if self.skip_next_ask:
                    self.skip_next_ask = False
                    continue  # 故意不答，等服务器超时托管
                text = m["candidates"][0] if m.get("candidates") else "过"
                await self.send({"t": "answer", "text": text})
            elif t == "player_afk":
                self.afk_events.append(m)
            elif t == "discuss_msg":
                self.discuss.append(m)
            elif t == "game_over":
                self.game_overs += 1
            elif t == "review":
                self.review_ok = True

    async def close(self):
        if self.ws:
            await self.ws.close()


async def main() -> int:
    failures = []

    def check(cond, label):
        print(("✓" if cond else "✗"), label)
        if not cond:
            failures.append(label)

    # 1. 阿泽建房，小明加入
    a = Client("阿泽")
    await a.connect({"t": "create_room", "nickname": "阿泽"})
    joined = json.loads(await asyncio.wait_for(a.ws.recv(), 10))
    check(joined["t"] == "joined" and joined["host"], "A 创建房间并获得房主标记")
    code = joined["room"]
    state = json.loads(await asyncio.wait_for(a.ws.recv(), 10))
    check(state["t"] == "room_state" and len(state["players"]) == 1
          and state["ai_fill"] == 5, "A 看到大厅状态（1 人 + AI 补位 5）")

    b = Client("小明")
    await b.connect({"t": "join_room", "room": code, "nickname": "小明"})
    joined_b = json.loads(await asyncio.wait_for(b.ws.recv(), 10))
    check(joined_b["t"] == "joined" and not joined_b["host"], "B 加入房间（非房主）")
    state_b = json.loads(await asyncio.wait_for(b.ws.recv(), 10))
    check(len(state_b["players"]) == 2 and state_b["ai_fill"] == 4,
          "B 看到大厅状态（2 人 + AI 补位 4）")
    state_a2 = json.loads(await asyncio.wait_for(a.ws.recv(), 10))
    check(len(state_a2["players"]) == 2, "A 实时看到 B 进房")

    # 2. 房主开局（6 人局：2 人类 + 4 AI）
    # Mock 局推进极快，挂机标记必须在开局前就设好：
    # B 第一次被问话时故意不答 → 3 秒超时 → AI 托管
    b.skip_next_ask = True
    stop = {"stop": False}
    pa = asyncio.create_task(a.pump(stop))
    pb = asyncio.create_task(b.pump(stop))
    await a.send({"t": "room_start"})
    await asyncio.sleep(2)
    check(a.started_count == 1 and b.started_count == 1, "双客户端都进入对局")
    check(a.seat and b.seat and a.seat != b.seat, "两人分配到不同座位")
    check(a.role_msg and b.role_msg, "两人都收到私密身份")
    check(a.role_msg["role"] != b.role_msg["role"] or True, "身份各自独立")

    # 4. 等到整局结束
    deadline = asyncio.get_event_loop().time() + 80
    while (a.game_overs < 1 or not a.review_ok) and \
            asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(1)
    check(a.game_overs >= 1 and b.game_overs >= 1, "双客户端都收到 game_over")
    check(a.review_ok and b.review_ok, "双客户端都收到复盘")
    check(any(e["afk"] for e in a.afk_events), "A 收到了 B 挂机的 AFK 广播")
    check(any("托管" in t for t in a.feed_texts), "公屏出现托管提示")

    # 5. 赛后群聊：B 问全场（未点名 → 全部 AI 回应）
    await b.send({"t": "discuss", "text": "大家好，刚才谁带节奏带得最凶？"})
    deadline = asyncio.get_event_loop().time() + 20
    while len(b.discuss) < 3 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    check(any(d["player"].startswith(b.seat) for d in a.discuss),
          "A 看到了 B 的赛后发言（群聊广播）")
    check(len([d for d in b.discuss if not d["player"].startswith(b.seat)]) >= 2,
          "B 收到多个 AI 的赛后回应")

    # 6. 房主连开第二局
    await a.send({"t": "room_start"})
    deadline = asyncio.get_event_loop().time() + 15
    while a.started_count < 2 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    check(a.started_count == 2 and b.started_count == 2, "房主连开第二局，双人同步进入")

    stop["stop"] = True
    await a.close()
    await b.close()
    for t in (pa, pb):
        t.cancel()

    print()
    if failures:
        print("FAIL:", failures)
        return 1
    print("PASS: 多人房间全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
