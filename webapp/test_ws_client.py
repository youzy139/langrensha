"""Mock 模式 WS 端到端测试：连上服务器，指定当狼，自动应答直到游戏结束，
然后验证赛后讨论、历史存档回看、以及同一连接连开第二局。"""
import asyncio
import json
import sys
from pathlib import Path

import websockets

PORT = sys.argv[1] if len(sys.argv) > 1 else "7100"


async def recv_until(ws, want_types, timeout=60):
    """接收消息直到集齐目标类型；期间自动应答 ask，并统计狼人频道消息数。"""
    got = {}
    asks = 0
    wolf_msgs = 0
    kinds = set()
    while not want_types.issubset(got):
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        t = m.get("t")
        if t == "ask":
            asks += 1
            assert m.get("action"), f"ask 缺 action 字段：{m}"
            text = m["candidates"][0] if m.get("candidates") else "我是好人，过"
            await ws.send(json.dumps({"t": "answer", "text": text}))
        else:
            if t == "feed":
                kinds.add(m.get("kind"))
                if m.get("kind") == "wolf":
                    wolf_msgs += 1
                    assert m.get("speaker"), "狼人频道消息缺 speaker"
            got.setdefault(t, m)
    got["_kinds"] = kinds
    return got, asks, wolf_msgs


async def play_game(ws, role="werewolf"):
    """开一局并等到复盘推送。返回 (got, asks, wolf_msgs)。"""
    await ws.send(json.dumps({"t": "start", "config": "6p", "role": role}))
    return await recv_until(ws, {"role", "game_over", "review"})


async def main() -> int:
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        # 第一局：指定当狼
        got, asks, wolf_msgs = await play_game(ws, "werewolf")
        assert got["role"].get("role") == "werewolf", "指定当狼失败！"
        assert asks > 0, "没有收到任何提问！"
        assert wolf_msgs > 0, "当狼却没收到狼人频道消息！"
        assert len(got["review"]["md"]) > 50, "复盘内容为空！"
        need = {"phase", "speech", "vote", "notice"}
        assert need <= got["_kinds"], f"结构化消息不全：缺 {need - got['_kinds']}"
        over = got["game_over"]
        assert over["players"] and all("role" in p and "alive" in p for p in over["players"]), "game_over 缺身份"
        print(f"第一局: 当狼 ✓ {asks} 次提问 ✓ 狼人频道 {wolf_msgs} 条 ✓ "
              f"复盘 {len(got['review']['md'])} 字 ✓ 胜者={got['game_over']['winner']}")

        # 赛后讨论：问全场一个问题，应收到 5 个 AI（6 人局减人类）的回应
        await ws.send(json.dumps({"t": "discuss", "text": "你们当时怎么想的？"}))
        replies = 0
        while replies < 5:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if m.get("t") == "discuss_msg":
                replies += 1
                assert m.get("text"), "讨论回应为空！"
        print(f"赛后讨论: 收到 {replies} 个 AI 回应 ✓")

        # 历史存档：列表里应有刚打完的这局
        await ws.send(json.dumps({"t": "history"}))
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert m.get("t") == "history_list" and m["games"], "历史列表为空！"
        latest = m["games"][0]
        print(f"历史列表: {len(m['games'])} 局 ✓ 最新={latest['id']}")

        # 回看历史：应收到完整 feed + 复盘
        await ws.send(json.dumps({"t": "load_history", "id": latest["id"]}))
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert m.get("t") == "history_game", "历史回看失败！"
        g = m["game"]
        assert g["feed"] and g.get("review"), "历史存档缺对话或复盘！"
        assert g.get("final"), "存档缺终局身份"
        # 存档落在 data/mock/web/<id>/（Mock 模式不污染真实记录）
        root = Path(__file__).resolve().parent.parent
        d = root / "data" / "mock" / "web" / latest["id"]
        assert (d / "record.json").is_file() and (d / "events.jsonl").is_file(), f"存档目录不对：{d}"
        assert not list(root.glob("game_log_web_*.jsonl")), "根目录又出现了 game_log_web_*.jsonl"
        print(f"历史回看: {len(g['feed'])} 条对话 + 复盘 ✓")

        # 同一连接再开第二局（验证"再来一局"流程不需要刷新页面）
        got2, _, _ = await play_game(ws, "random")
        assert got2["game_over"]["winner"] in ("village", "werewolf")
        print("第二局（连开）: 完整结束 ✓")

    print("PASS: 全部通过")
    return 0


sys.exit(asyncio.run(main()))
