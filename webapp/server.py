"""狼人杀 Web 人机对局服务器（FastAPI + WebSocket）。

- 浏览器打开 / 进入大厅：选局型（6/8 人）、选阵营（可指定"我要当狼"）
- WebSocket /ws 驱动整局：公开信息流 + 私密信息 + 决策问答
- 角色在每局开始时随机洗牌，人类可指定想要的角色
- AI 决策走真实 LLM（需 LLM_BASE_URL/LLM_API_KEY）；WEREWOLF_MOCK=1 可离线演示
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 werewolf 包可导入

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from werewolf.gamemaster import GameMaster
from werewolf.logger import GameLogger
from werewolf.player import PlayerAgent
from werewolf.roles import ROLE_NAMES

CONFIGS = {
    "6p": ROOT / "config.yaml",
    "8p": ROOT / "config_8p_allflash.yaml",
}

app = FastAPI(title="多Agent狼人杀 · 人机对局")


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "index.html")


def assign_human(config: dict, desired_role: str, rng: random.Random) -> dict:
    """每局开始随机洗牌角色；人类可指定角色（如 werewolf），否则随机。"""
    players = [dict(p) for p in config["players"]]
    roles = [p["role"] for p in players]
    human_idx = rng.randrange(len(players))
    if desired_role in roles:  # 指定角色：人类座位拿该角色，其余洗牌
        roles.remove(desired_role)
        players[human_idx]["role"] = desired_role
        others = [i for i in range(len(players)) if i != human_idx]
        rng.shuffle(roles)
        for i, r in zip(others, roles):
            players[i]["role"] = r
    else:  # 完全随机
        rng.shuffle(roles)
        for p, r in zip(players, roles):
            p["role"] = r
    players[human_idx]["human"] = True
    config["players"] = players
    return config


class WebLogger(GameLogger):
    """把上帝的控制台输出（阶段/公告/发言/投票）转发到浏览器。"""

    def __init__(self, log_path, feed_q: asyncio.Queue):
        super().__init__(log_path, console=False)
        self.feed_q = feed_q

    def print(self, text: str = "") -> None:
        if text:
            self.feed_q.put_nowait({"t": "feed", "kind": "public", "text": text})


class WebHumanAgent(PlayerAgent):
    """人类玩家（Web 版）：决策通过 WebSocket 问答完成。"""

    def __init__(self, *args, feed_q: asyncio.Queue, inbox: asyncio.Queue, **kw):
        super().__init__(*args, **kw)
        self._feed = feed_q
        self._inbox = inbox
        # 开局告知身份（仅人类可见）
        self._feed.put_nowait({
            "t": "role", "role": self.role,
            "role_name": ROLE_NAMES[self.role],
            "mates": "、".join(self.mates),
        })

    def note(self, line: str) -> None:
        super().note(line)
        self._feed.put_nowait({"t": "feed", "kind": "private", "text": line})

    async def _ask(self, prompt: str, candidates: list[str] | None = None,
                   allow_abstain: bool = True) -> str:
        await self._feed.put({
            "t": "ask",
            "kind": "choice" if candidates else "text",
            "prompt": prompt,
            "candidates": candidates or [],
            "allow_abstain": allow_abstain,
        })
        ans = await self._inbox.get()
        return str(ans.get("text", "")).strip()

    async def _ask_choice(self, prompt: str, candidates: list[str],
                          allow_abstain: bool = True) -> str | None:
        pool = [c for c in candidates if c != self.name]
        while True:
            raw = await self._ask(prompt, pool, allow_abstain)
            if allow_abstain and raw in ("", "弃权"):
                return None
            choice = self._resolve_choice(raw, pool)
            if choice:
                return choice
            await self._feed.put({"t": "feed", "kind": "private",
                                  "text": f"⚠️ 无效选择「{raw}」，请重新选择"})

    async def speak(self, round_no: int) -> str:
        text = await self._ask(f"轮到你发言（第 {round_no} 轮，≤{self.speech_max_chars} 字）")
        return (text or "（我选择沉默）")[: self.speech_max_chars]

    async def vote(self, candidates: list[str], round_no: int):
        return await self._ask_choice(f"投票放逐（第 {round_no} 轮）", candidates)

    async def werewolf_discuss(self, channel, alive_targets, round_no):
        if channel:
            await self._feed.put({"t": "feed", "kind": "wolf",
                                  "text": "狼人频道：\n" + "\n".join(channel)})
        msg = await self._ask(f"狼人频道发言（第 {round_no} 夜，≤50 字）")
        return (msg or "……")[:50]

    async def werewolf_kill_vote(self, channel, alive_targets, round_no):
        c = await self._ask_choice("今晚刀谁？", alive_targets, allow_abstain=False)
        return c or self.rng.choice(alive_targets)

    async def seer_check(self, candidates, round_no):
        c = await self._ask_choice(f"预言家验人（第 {round_no} 夜）",
                                   candidates, allow_abstain=False)
        return c or self.rng.choice(candidates)

    async def witch_action(self, killed, has_antidote, has_poison,
                           can_self_save, alive_others, round_no):
        save = False
        if has_antidote and killed:
            if killed == self.name and not can_self_save:
                await self._feed.put({"t": "feed", "kind": "private",
                                      "text": "今晚被刀的是你，但首夜之后不能自救"})
            else:
                raw = await self._ask(f"今晚被刀的是 {killed}，用解药救吗？",
                                      ["救", "不救"], allow_abstain=False)
                save = raw == "救"
        poison = None
        if has_poison and not save:
            poison = await self._ask_choice("用毒药毒谁？（回车/弃权 = 不用）",
                                            alive_others)
        return {"save": save, "poison": poison}

    async def hunter_shot(self, candidates, round_no, cause):
        return await self._ask_choice(f"你{cause}，可以开枪带走一人（也可不开枪）",
                                      candidates)


@app.websocket("/ws")
async def game_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:  # 支持"再来一局"
            msg = json.loads(await ws.receive_text())
            if msg.get("t") == "start":
                await _run_game_session(ws, msg)
    except WebSocketDisconnect:
        pass


async def _run_game_session(ws: WebSocket, start_msg: dict) -> None:
    cfg_path = CONFIGS.get(start_msg.get("config", "6p"), CONFIGS["6p"])
    with open(cfg_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    rng = random.Random()
    config = assign_human(config, start_msg.get("role", "random"), rng)

    feed_q: asyncio.Queue = asyncio.Queue()
    inbox: asyncio.Queue = asyncio.Queue()
    logger = WebLogger(ROOT / "game_log_web.jsonl", feed_q)
    gm = GameMaster(config, logger, rng=rng,
                    human_agent_cls=WebHumanAgent,
                    human_kwargs={"feed_q": feed_q, "inbox": inbox})
    human_name = next(p["name"] for p in config["players"] if p.get("human"))
    await ws.send_text(json.dumps(
        {"t": "started", "name": human_name,
         "players": [p["name"] for p in config["players"]]}, ensure_ascii=False))

    async def pump_out():  # 服务端事件 → 浏览器
        while True:
            m = await feed_q.get()
            await ws.send_text(json.dumps(m, ensure_ascii=False))

    async def pump_in():  # 浏览器回答 → 人类 Agent
        while True:
            m = json.loads(await ws.receive_text())
            if m.get("t") == "answer":
                inbox.put_nowait(m)

    game_task = asyncio.create_task(gm.run())
    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        # 等待游戏结束或连接断开（in_task 因 Disconnect 退出），先到者生效
        done, _ = await asyncio.wait({game_task, in_task},
                                     return_when=asyncio.FIRST_COMPLETED)
        if in_task in done and not game_task.done():
            game_task.cancel()  # 客户端断开：立即终止对局，避免空跑 LLM 调用
            try:
                await game_task
            except asyncio.CancelledError:
                pass
            return
        winner = game_task.result()
    finally:
        out_task.cancel()
        in_task.cancel()
        await gm.client.aclose()
        logger.close()
    reveal = "；".join(f"{p.name}={ROLE_NAMES[p.role]}" for p in gm.players.values())
    await ws.send_text(json.dumps(
        {"t": "game_over", "winner": winner, "reveal": reveal},
        ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7100)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
