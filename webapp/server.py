"""狼人杀 Web 人机对局服务器（FastAPI + WebSocket）。

- 浏览器打开 / 进入大厅：选局型（6/8 人）、选阵营（可指定"我要当狼"）
- WebSocket /ws 驱动整局：公开信息流 + 私密信息 + 决策问答
- 终局后进入"赛后模式"：LLM 解说复盘 + 全员赛后讨论（AI 亮身份交换信息）
- 每局自动存档到 history/，大厅可随时回看历史对局，无需开新局
- 角色在每局开始时随机洗牌，人类可指定想要的角色
- AI 决策走真实 LLM（需 LLM_BASE_URL/LLM_API_KEY）；WEREWOLF_MOCK=1 可离线演示
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
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
from werewolf.review import generate_review
from werewolf.roles import ROLE_NAMES

CONFIGS = {
    "6p": ROOT / "config.yaml",
    "8p": ROOT / "config_8p_allflash.yaml",
}
HISTORY_DIR = Path(__file__).parent / "history"

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

    def event(self, event_type, **payload):
        super().event(event_type, **payload)
        # 把死亡信息结构化推给前端，右侧玩家栏实时标记"已出局"
        dead: list[str] = []
        if event_type == "day_announce":
            dead = payload.get("deaths") or []
        elif event_type == "day_vote" and payload.get("exiled"):
            dead = [payload["exiled"]]
        elif event_type == "hunter_shot" and payload.get("shot"):
            dead = [payload["shot"]]
        for name in dead:
            self.feed_q.put_nowait({"t": "dead", "name": name})


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

    def note(self, line: str, display: bool = True) -> None:
        super().note(line, display=display)
        if display:
            self._feed.put_nowait({"t": "feed", "kind": "private", "text": line})

    def wolf_hear(self, line: str) -> None:
        """队友在狼人频道发言：实时推到公屏（仅自己是狼时才会有此消息）。"""
        self._feed.put_nowait({"t": "feed", "kind": "wolf",
                               "text": "🐺 狼人频道 · " + line})

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
                          allow_abstain: bool = True,
                          exclude_self: bool = True) -> str | None:
        pool = [c for c in candidates if not (exclude_self and c == self.name)]
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
        # 频道消息已通过 wolf_hear 实时推送，这里不再整段重复展示
        msg = (await self._ask(f"狼人频道发言（第 {round_no} 夜，≤50 字）") or "……")[:50]
        # 自己的发言也回显进频道流（wolf_hear 只推队友的消息）
        self._feed.put_nowait({"t": "feed", "kind": "wolf",
                               "text": f"🐺 狼人频道 · {self.name}（你）: {msg}"})
        return msg

    async def werewolf_kill_vote(self, channel, alive_targets, round_no):
        # 自刀局候选含狼人：可以刀队友甚至刀自己（骗解药/做高身份）
        c = await self._ask_choice(
            "今晚刀谁？（候选里有狼人 = 本局允许自刀，可骗解药/做高身份）",
            alive_targets, allow_abstain=False, exclude_self=False)
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


# ---------- 历史对局存档 ----------
def _save_history(record: dict) -> str:
    HISTORY_DIR.mkdir(exist_ok=True)
    hist_id = time.strftime("%Y%m%d_%H%M%S")
    (HISTORY_DIR / f"{hist_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return hist_id


async def _send_history_list(ws: WebSocket) -> None:
    games = []
    if HISTORY_DIR.exists():
        for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
            try:
                g = json.loads(f.read_text(encoding="utf-8"))
                games.append({
                    "id": f.stem, "ts": g.get("ts", f.stem),
                    "cfg": g.get("cfg", ""), "winner": g.get("winner", ""),
                    "players": g.get("players", []),
                })
            except Exception:
                continue
    await ws.send_text(json.dumps(
        {"t": "history_list", "games": games[:20]}, ensure_ascii=False))


async def _send_history_game(ws: WebSocket, hist_id: str) -> None:
    f = HISTORY_DIR / f"{hist_id}.json"
    if not f.exists():
        await ws.send_text(json.dumps(
            {"t": "feed", "kind": "private", "text": "⚠️ 找不到该历史对局"},
            ensure_ascii=False))
        return
    g = json.loads(f.read_text(encoding="utf-8"))
    await ws.send_text(json.dumps({"t": "history_game", "game": g},
                                  ensure_ascii=False))


# ---------- 赛后讨论 ----------
async def _handle_discuss(ws: WebSocket, gm: GameMaster, human_name: str,
                          question: str) -> None:
    """全场 AI 亮身份，带着各自的私密信息和推理回应人类的提问。"""
    agents = [p for p in gm.players.values() if p.name != human_name]
    # 串行回复而不是 gather 并发：一来避免并发请求触发限流，
    # 二来回复一个接一个出现，更像真人赛后群聊
    for a in agents:
        try:
            r = await a.post_game_chat(question, human_name)
        except Exception as e:
            r = f"（回应失败：{e!r}）"
        await ws.send_text(json.dumps(
            {"t": "discuss_msg", "player": a.name,
             "role_name": ROLE_NAMES[a.role], "text": r},
            ensure_ascii=False))


# ---------- 对局会话 ----------
@app.websocket("/ws")
async def game_ws(ws: WebSocket):
    await ws.accept()
    incoming: asyncio.Queue = asyncio.Queue()

    async def recv_loop():  # 统一接收，分发给大厅/对局/赛后各阶段
        while True:
            incoming.put_nowait(json.loads(await ws.receive_text()))

    recv_task = asyncio.create_task(recv_loop())
    try:
        while True:
            msg = await incoming.get()
            t = msg.get("t")
            if t == "start":
                await _session_loop(ws, msg, incoming)
            elif t == "history":
                await _send_history_list(ws)
            elif t == "load_history":
                await _send_history_game(ws, msg.get("id", ""))
    except WebSocketDisconnect:
        pass
    finally:
        recv_task.cancel()


async def _session_loop(ws: WebSocket, start_msg: dict,
                        incoming: asyncio.Queue) -> None:
    """打完一局 → 赛后模式（复盘/讨论/看历史）→ 收到 start 再开一局。"""
    while True:
        gm, config, human_name, winner, record = await _play_one_game(
            ws, start_msg, incoming)
        try:
            # 赛后复盘解说（日志已落盘；flash reasoning 模型可能要几十秒）
            try:
                md = await generate_review(config, ROOT / "game_log_web.jsonl")
            except Exception as e:  # 复盘失败不影响终局体验
                md = f"（复盘生成失败：{e!r}）"
            record["review"] = md
            record["id"] = _save_history(record)
            await ws.send_text(json.dumps({"t": "review", "md": md},
                                          ensure_ascii=False))
            start_msg = await _post_game_loop(ws, gm, human_name, incoming)
        finally:
            await gm.client.aclose()
            gm.logger.close()  # 日志留到赛后讨论之后才关（讨论仍会写 llm_call 事件）


async def _play_one_game(ws: WebSocket, start_msg: dict,
                         incoming: asyncio.Queue):
    cfg_path = CONFIGS.get(start_msg.get("config", "6p"), CONFIGS["6p"])
    with open(cfg_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    rng = random.Random()
    config = assign_human(config, start_msg.get("role", "random"), rng)

    feed_q: asyncio.Queue = asyncio.Queue()
    inbox: asyncio.Queue = asyncio.Queue()
    record: dict = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "cfg": start_msg.get("config", "6p"), "feed": []}
    logger = WebLogger(ROOT / "game_log_web.jsonl", feed_q)
    gm = GameMaster(config, logger, rng=rng,
                    human_agent_cls=WebHumanAgent,
                    human_kwargs={"feed_q": feed_q, "inbox": inbox})

    # LLM 调用状态 → 前端"正在思考"提示。
    # 注意：夜间动作按人名显示会泄露身份（谁在验人=谁是预言家），只给通用提示。
    night_active = {"n": 0}

    def on_llm_status(player: str, action: str, phase: str, on: bool) -> None:
        if phase.startswith("night"):
            night_active["n"] = max(0, night_active["n"] + (1 if on else -1))
            if night_active["n"] == 1 and on:
                feed_q.put_nowait({"t": "thinking", "on": True,
                                   "label": "🌙 夜晚行动中"})
            elif night_active["n"] == 0 and not on:
                feed_q.put_nowait({"t": "thinking", "on": False, "label": ""})
            return
        label = {
            "day_speech": f"💭 {player} 正在组织发言",
            "day_vote": f"🗳️ {player} 正在思考投票",
            "hunter_shot": f"🔫 {player} 正在考虑开枪",
            "post_game": "💬 大家正在组织语言",
        }.get(phase)
        if label is not None:
            feed_q.put_nowait({"t": "thinking", "on": on,
                               "label": label if on else ""})

    gm.client.on_status = on_llm_status
    human_name = next(p["name"] for p in config["players"] if p.get("human"))
    record["human"] = human_name
    record["players"] = [{"name": p["name"], "role": p["role"],
                          "role_name": ROLE_NAMES[p["role"]]}
                         for p in config["players"]]
    await ws.send_text(json.dumps(
        {"t": "started", "name": human_name,
         "players": [p["name"] for p in config["players"]]}, ensure_ascii=False))

    async def pump_out():  # 服务端事件 → 浏览器，同时录进历史存档
        while True:
            m = await feed_q.get()
            if m.get("t") in ("feed", "role"):
                record["feed"].append(m)
            await ws.send_text(json.dumps(m, ensure_ascii=False))

    async def pump_in():  # 统一入口的消息 → 人类 Agent 的回答队列
        while True:
            m = await incoming.get()
            if m.get("t") == "answer":
                inbox.put_nowait(m)
            # start/history 等消息在游戏进行中忽略

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
            raise WebSocketDisconnect()
        winner = game_task.result()
    finally:
        out_task.cancel()
        in_task.cancel()
        # 注意：这里不关 logger——赛后讨论还要往日志写 llm_call 事件，
        # 提前关闭会让所有赛后发言报 "I/O operation on closed file"
        # （logger 由 _session_loop 在赛后模式结束后统一关闭）
    reveal = "；".join(f"{p.name}={ROLE_NAMES[p.role]}" for p in gm.players.values())
    record["winner"] = winner
    record["reveal"] = reveal
    await ws.send_text(json.dumps(
        {"t": "game_over", "winner": winner, "reveal": reveal},
        ensure_ascii=False))
    return gm, config, human_name, winner, record


async def _post_game_loop(ws: WebSocket, gm: GameMaster, human_name: str,
                          incoming: asyncio.Queue) -> dict:
    """赛后模式：讨论提问 / 查历史，直到人类发起下一局。返回新的 start 消息。"""
    while True:
        m = await incoming.get()
        t = m.get("t")
        if t == "start":
            return m
        if t == "discuss":
            await _handle_discuss(ws, gm, human_name, str(m.get("text", "")))
        elif t == "history":
            await _send_history_list(ws)
        elif t == "load_history":
            await _send_history_game(ws, m.get("id", ""))


def _ensure_port_free(port: int) -> None:
    """启动前清掉占用端口的旧服务器进程。

    否则预览卡片/手动重启会撞上上一个还在跑的旧代码实例，
    表现为"重启了但界面还是旧的"。只杀占用同一端口的进程，不碰别的。
    """
    import socket
    import subprocess

    def in_use() -> bool:
        with socket.socket() as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    if not in_use():
        return
    try:
        out = subprocess.run(["netstat", "-ano"],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if (len(parts) >= 5 and "LISTENING" in line
                    and parts[1].endswith(f":{port}")):
                pid = parts[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(["taskkill", "/PID", pid, "/F"],
                                   capture_output=True)
        for _ in range(25):  # 最多等 5 秒端口释放
            if not in_use():
                break
            time.sleep(0.2)
    except Exception:
        pass  # 清理失败就交给 uvicorn 正常报错


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7100)
    args = ap.parse_args()
    _ensure_port_free(args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
