"""多人房间模式：RoomManager / Room / HumanConnection / RoomHumanAgent。

设计要点（详见 docs/MULTIPLAYER_DESIGN.md）：
- 房间与对局解耦：打完一局回大厅，可直接开下一局。
- 引擎零改动：GameMaster / PlayerAgent 完全不感知"多人"，
  人类只是持有各自 HumanConnection 的 PlayerAgent 子类。
- 公屏消息由 Room 扇出到所有人类连接；私密/狼人频道只投递本人。
- 人类决策超时（默认 75s，WEREWOLF_ASK_TIMEOUT 可调）→ AFK，
  由 AI 拿着该座位的记忆托管代打，游戏永不断流。
- Phase 1 范围：断线 = AFK 到底（对局中重连是 Phase 2）。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import secrets
import string
import time
from pathlib import Path
from typing import Optional

import yaml
from fastapi import WebSocket, WebSocketDisconnect

from werewolf.gamemaster import GameMaster
from werewolf.logger import GameLogger
from werewolf.player import PlayerAgent
from werewolf.review import generate_review
from werewolf.roles import ROLE_NAMES

import archive
from feedfmt import RECORDED, game_over_msg, public_events, public_msg, wolf_msg

ROOT = Path(__file__).resolve().parent.parent

import os
ASK_TIMEOUT = float(os.environ.get("WEREWOLF_ASK_TIMEOUT", "75"))


class AFK(Exception):
    """人类决策超时：切换到 AI 托管。"""


class HumanConnection:
    """一个人类玩家的连接状态（WS 断线后座位仍保留，AI 托管）。"""

    def __init__(self, room: "Room", nickname: str):
        self.room = room
        self.nickname = nickname or "玩家"
        self.token = secrets.token_hex(8)
        self.seat: Optional[str] = None   # 开局时分配座位名（Alice…）
        self.feed_q: asyncio.Queue = asyncio.Queue()
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.afk = False
        self.connected = True

    def feed(self, m: dict) -> None:
        self.feed_q.put_nowait(m)


class RoomLogger(GameLogger):
    """上帝的公开输出 → Room 总线扇出到所有人类客户端（并录入历史存档）。"""

    def __init__(self, log_path, room: "Room"):
        super().__init__(log_path, console=False)
        self.room = room

    def print(self, text: str = "") -> None:
        if text:
            self.room.broadcast(public_msg(text), record=True)

    def event(self, event_type, **payload):
        super().event(event_type, **payload)
        for m in public_events(event_type, payload):
            self.room.broadcast(m, record=True)


class RoomHumanAgent(PlayerAgent):
    """房间版人类玩家：问答走自己的连接，超时/挂机自动 AI 托管。"""

    def __init__(self, *args, room: "Room", **kw):
        super().__init__(*args, **kw)
        self._room = room
        self._conn = room.conn_by_seat(self.name)
        self._conn.feed({
            "t": "role", "role": self.role,
            "role_name": ROLE_NAMES[self.role],
            "mates": "、".join(self.mates),
        })

    # ---------- 通道 ----------
    def note(self, line: str, display: bool = True) -> None:
        super().note(line, display=display)
        if display:
            self._conn.feed({"t": "feed", "kind": "private", "text": line})

    def wolf_hear(self, line: str) -> None:
        speaker, _, msg = line.partition(": ")
        self._conn.feed(wolf_msg(speaker, msg))

    async def _ask(self, prompt: str, candidates: list[str] | None = None,
                   allow_abstain: bool = True, action: str = "") -> str:
        if self._conn.afk:
            raise AFK()
        self._drain_inbox()  # 丢弃迟到的陈旧回答，防止串到下一个问题
        self._conn.feed({
            "t": "ask",
            "kind": "choice" if candidates else "text",
            "action": action,
            "timeout": ASK_TIMEOUT,
            "prompt": prompt,
            "candidates": candidates or [],
            "allow_abstain": allow_abstain,
        })
        try:
            ans = await asyncio.wait_for(self._conn.inbox.get(), ASK_TIMEOUT)
        except asyncio.TimeoutError:
            self._conn.afk = True
            self._room.broadcast({"t": "player_afk", "name": self.name,
                                  "afk": True})
            self._room.broadcast(
                {"t": "feed", "kind": "system",
                 "text": f"⏳ {self.name} 超时未响应，接下来由 AI 托管"},
                record=True)
            raise AFK()
        return str(ans.get("text", "")).strip()

    def _drain_inbox(self) -> None:
        while True:
            try:
                self._conn.inbox.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _ask_choice(self, prompt, candidates, allow_abstain=True,
                          exclude_self=True, action=""):
        pool = [c for c in candidates if not (exclude_self and c == self.name)]
        while True:
            raw = await self._ask(prompt, pool, allow_abstain, action)
            if allow_abstain and raw in ("", "弃权"):
                return None
            choice = self._resolve_choice(raw, pool)
            if choice:
                return choice
            self._conn.feed({"t": "feed", "kind": "private",
                             "text": f"⚠️ 无效选择「{raw}」，请重新选择"})

    # ---------- 决策（超时一律回退到 AI 基类实现 = AI 拿着人类记忆代打） ----------
    async def speak(self, round_no: int) -> str:
        try:
            text = await self._ask(
                f"轮到你发言（第 {round_no} 轮，≤{self.speech_max_chars} 字）",
                action="speak")
            return (text or "（我选择沉默）")[: self.speech_max_chars]
        except AFK:
            return await super().speak(round_no)

    async def vote(self, candidates, round_no):
        try:
            return await self._ask_choice(f"投票放逐（第 {round_no} 轮）", candidates,
                                          action="vote")
        except AFK:
            return await super().vote(candidates, round_no)

    async def werewolf_discuss(self, channel, alive_targets, round_no):
        try:
            msg = (await self._ask(f"狼人频道发言（第 {round_no} 夜，≤50 字）",
                                   action="wolf_chat") or "……")[:50]
            self._conn.feed(wolf_msg(self.name, msg))
            return msg
        except AFK:
            return await super().werewolf_discuss(channel, alive_targets, round_no)

    async def werewolf_kill_vote(self, channel, alive_targets, round_no):
        try:
            c = await self._ask_choice(
                "今晚刀谁？（候选里有狼人 = 本局允许自刀，可骗解药/做高身份）",
                alive_targets, allow_abstain=False, exclude_self=False,
                action="kill")
            return c or self.rng.choice(alive_targets)
        except AFK:
            return await super().werewolf_kill_vote(channel, alive_targets, round_no)

    async def seer_check(self, candidates, round_no):
        try:
            c = await self._ask_choice(f"预言家验人（第 {round_no} 夜）",
                                       candidates, allow_abstain=False,
                                       action="check")
            return c or self.rng.choice(candidates)
        except AFK:
            return await super().seer_check(candidates, round_no)

    async def witch_action(self, killed, has_antidote, has_poison,
                           can_self_save, alive_others, round_no):
        try:
            if self._conn.afk:
                raise AFK()
            save = False
            if has_antidote and killed:
                if killed == self.name and not can_self_save:
                    self._conn.feed({"t": "feed", "kind": "private",
                                     "text": "今晚被刀的是你，但首夜之后不能自救"})
                else:
                    raw = await self._ask(f"今晚被刀的是 {killed}，用解药救吗？",
                                          ["救", "不救"], allow_abstain=False,
                                          action="save")
                    save = raw == "救"
            poison = None
            if has_poison and not save:
                poison = await self._ask_choice("用毒药毒谁？（弃权 = 不用）",
                                                alive_others, action="poison")
            return {"save": save, "poison": poison}
        except AFK:
            return await super().witch_action(killed, has_antidote, has_poison,
                                              can_self_save, alive_others, round_no)

    async def hunter_shot(self, candidates, round_no, cause):
        try:
            return await self._ask_choice(
                f"你{cause}，可以开枪带走一人（也可不开枪）", candidates,
                action="shoot")
        except AFK:
            return await super().hunter_shot(candidates, round_no, cause)


def assign_humans(config: dict, human_count: int, rng: random.Random) -> dict:
    """前 human_count 个座位给人类（按进房顺序），角色照常随机洗牌。"""
    players = [dict(p) for p in config["players"]]
    roles = [p["role"] for p in players]
    rng.shuffle(roles)
    for p, r in zip(players, roles):
        p["role"] = r
    for i in range(human_count):
        players[i]["human"] = True
    config["players"] = players
    return config


class Room:
    """一个房间的生命周期容器：LOBBY → PLAYING → ENDED → （再开）→ …"""

    def __init__(self, manager: "RoomManager", code: str):
        self.manager = manager
        self.code = code
        self.conns: list[HumanConnection] = []
        self.host: Optional[HumanConnection] = None
        self.state = "LOBBY"  # LOBBY / PLAYING / ENDED
        self.config_key = "6p"
        self.gm: Optional[GameMaster] = None
        self.record: Optional[dict] = None
        self.last_config: Optional[dict] = None
        self._game_lock = asyncio.Lock()

    # ---------- 成员 ----------
    def add(self, nickname: str) -> HumanConnection:
        conn = HumanConnection(self, nickname)
        self.conns.append(conn)
        if self.host is None:
            self.host = conn
        return conn

    def remove(self, conn: HumanConnection) -> None:
        if conn in self.conns:
            self.conns.remove(conn)
        if self.host is conn:
            self.host = next((c for c in self.conns if c.connected), None)
        if not self.conns:
            self.manager.rooms.pop(self.code, None)

    def conn_by_seat(self, seat: str) -> HumanConnection:
        return next(c for c in self.conns if c.seat == seat)

    def on_disconnect(self, conn: HumanConnection) -> None:
        conn.connected = False
        if self.state == "PLAYING":
            # Phase 1：断线 = AFK 到底，AI 托管打完本局
            conn.afk = True
            self.broadcast({"t": "player_afk", "name": conn.seat, "afk": True})
            self.broadcast({"t": "feed", "kind": "system",
                            "text": f"🔌 {conn.nickname}（{conn.seat}）掉线，AI 托管中"},
                           record=True)
        else:
            self.remove(conn)
            self.broadcast_state()

    # ---------- 广播 ----------
    def broadcast(self, m: dict, record: bool = False,
                  exclude: Optional[HumanConnection] = None) -> None:
        for c in self.conns:
            if c is not exclude and c.connected:
                c.feed(m)
        if record and self.record is not None and m.get("t") in RECORDED:
            self.record["feed"].append(m)

    def broadcast_state(self) -> None:
        if not self.conns:
            return
        seats = 8 if self.config_key == "8p" else 6
        self.broadcast({
            "t": "room_state", "room": self.code, "state": self.state,
            "config": self.config_key,
            "players": [{"nick": c.nickname,
                         "host": c is self.host} for c in self.conns],
            "ai_fill": max(0, seats - len(self.conns)),
        })

    # ---------- 消息路由（连接收包 → 房间） ----------
    async def handle_client_msg(self, conn: HumanConnection, m: dict) -> None:
        t = m.get("t")
        if conn.afk and t in ("answer", "discuss"):  # 人回来了，解除托管
            conn.afk = False
            self.broadcast({"t": "player_afk",
                            "name": conn.seat or conn.nickname, "afk": False})
        if t == "answer":
            conn.inbox.put_nowait(m)
        elif t == "discuss" and self.state == "ENDED":
            await self._discuss(conn, str(m.get("text", "")).strip())
        elif t == "set_config" and conn is self.host and self.state == "LOBBY":
            key = str(m.get("config", "6p"))
            if key in self.manager.configs:
                self.config_key = key
                self.broadcast_state()
        elif t == "room_start" and conn is self.host \
                and self.state in ("LOBBY", "ENDED"):
            asyncio.create_task(self._run_game_guarded())
        elif t == "history":
            await self.manager.send_history_list(conn)
        elif t == "load_history":
            await self.manager.send_history_game(conn, m.get("id", ""))

    # ---------- 对局 ----------
    async def _run_game_guarded(self) -> None:
        async with self._game_lock:
            if self.state == "PLAYING":
                return
            await self._run_game()

    async def _run_game(self) -> None:
        self.state = "PLAYING"
        cfg_path = self.manager.configs[self.config_key]
        with open(cfg_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self.last_config = config
        rng = random.Random()
        config = assign_humans(config, len(self.conns), rng)

        # 座位分配：按进房顺序坐前 N 个座位
        humans = [p for p in config["players"] if p.get("human")]
        for conn, p in zip(self.conns, humans):
            conn.seat = p["name"]
            conn.afk = False
        nicknames = {c.seat: c.nickname for c in self.conns}

        self.record = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "cfg": self.config_key, "feed": [],
                       "room": self.code}
        self.game_id, log_path = archive.new_game()
        logger = RoomLogger(log_path, self)
        self.gm = GameMaster(config, logger, rng=rng,
                             human_agent_cls=RoomHumanAgent,
                             human_kwargs={"room": self})

        # LLM 状态 → 所有客户端的"正在思考"提示（夜间不给具名，防泄身份）
        night_active = {"n": 0}

        def on_llm_status(player: str, action: str, phase: str, on: bool) -> None:
            if phase.startswith("night"):
                night_active["n"] = max(0, night_active["n"] + (1 if on else -1))
                if night_active["n"] == 1 and on:
                    self.broadcast({"t": "thinking", "on": True,
                                    "label": "🌙 夜晚行动中"})
                elif night_active["n"] == 0 and not on:
                    self.broadcast({"t": "thinking", "on": False, "label": ""})
                return
            label = {
                "day_speech": f"💭 {player} 正在组织发言",
                "day_vote": f"🗳️ {player} 正在思考投票",
                "hunter_shot": f"🔫 {player} 正在考虑开枪",
                "post_game": "💬 大家正在组织语言",
            }.get(phase)
            if label is not None:
                self.broadcast({"t": "thinking", "on": on,
                                "label": label if on else "",
                                "player": player if on else "", "phase": phase})

        self.gm.client.on_status = on_llm_status
        all_names = [p["name"] for p in config["players"]]
        self.record["players"] = [{"name": p["name"], "role": p["role"],
                                   "role_name": ROLE_NAMES[p["role"]]}
                                  for p in config["players"]]
        self.record["humans"] = {c.seat: c.nickname for c in self.conns}
        for conn in self.conns:
            conn.feed({"t": "started", "name": conn.seat, "players": all_names,
                       "nicknames": nicknames})
        self.broadcast_state()

        winner = await self.gm.run()

        over = game_over_msg(self.gm, winner)
        self.record.update(winner=winner, reveal=over["reveal"],
                           rounds=self.gm.round_no, final=over["players"])
        self.broadcast(over)

        # 赛后复盘（一份生成，全场共享）
        try:
            md = await generate_review(config, log_path)
        except Exception as e:
            md = f"（复盘生成失败：{e!r}）"
        self.record["review"] = md
        archive.save_record(self.game_id, self.record)
        self.broadcast({"t": "review", "md": md})
        self.state = "ENDED"
        await self.gm.client.aclose()
        self.gm.logger.close()
        self.broadcast_state()

    # ---------- 赛后群聊 ----------
    async def _discuss(self, conn: HumanConnection, question: str) -> None:
        if not question or self.gm is None:
            return
        asker = conn.seat or conn.nickname
        # 人类的发言先广播给全场（含自己，客户端统一渲染）
        self.broadcast({"t": "discuss_msg",
                        "player": f"{asker}（{conn.nickname}）",
                        "role_name": ROLE_NAMES[self.gm.players[asker].role]
                        if asker in self.gm.players else "人类",
                        "text": question})
        ai_agents = [p for p in self.gm.players.values()
                     if p.name not in {c.seat for c in self.conns}]
        q = question.lower()
        word = lambda n: re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", q)
        targets = [a for a in ai_agents if word(a.name.lower())]
        if not targets:
            human_hit = any(word((c.seat or "").lower()) or
                            (c.nickname and c.nickname in question)
                            for c in self.conns)
            targets = [] if human_hit else ai_agents  # 只点名人类 → AI 不抢话
        for a in targets:
            try:
                r = await a.post_game_chat(question, asker)
            except Exception as e:
                r = f"（回应失败：{e!r}）"
            self.broadcast({"t": "discuss_msg", "player": a.name,
                            "role_name": ROLE_NAMES[a.role], "text": r})


class RoomManager:
    """全局房间注册表 + WS 连接入口。"""

    def __init__(self, configs: dict):
        self.rooms: dict[str, Room] = {}
        self.configs = configs

    # ---------- 房间码 ----------
    def _new_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choices(alphabet, k=4))
            if code not in self.rooms:
                return code

    # ---------- WS 入口 ----------
    async def handle_entry(self, ws: WebSocket, m: dict) -> None:
        t = m.get("t")
        room: Optional[Room] = None
        conn: Optional[HumanConnection] = None
        if t == "create_room":
            room = Room(self, self._new_code())
            self.rooms[room.code] = room
            conn = room.add(str(m.get("nickname") or "玩家"))
        elif t == "join_room":
            room = self.rooms.get(str(m.get("room") or "").upper())
            if room is None:
                await self._err(ws, "房间不存在，检查房间码")
                return
            if room.state != "LOBBY":
                await self._err(ws, "该房间对局进行中，等他们打完这局再来")
                return
            seats = 8 if room.config_key == "8p" else 6
            if len(room.conns) >= seats:
                await self._err(ws, "房间满了")
                return
            conn = room.add(str(m.get("nickname") or "玩家"))
        elif t == "rejoin":
            room = self.rooms.get(str(m.get("room") or "").upper())
            conn = next((c for c in (room.conns if room else [])
                         if c.token == m.get("token")), None)
            if conn is None:
                await self._err(ws, "重连失败：房间或凭据已失效")
                return
            if room.state == "PLAYING":
                await self._err(ws, "对局中暂不支持重连（下个版本安排），本局 AI 会帮你打完")
                return
            conn.connected = True
        else:
            await self._err(ws, "未知的房间操作")
            return

        await ws.send_text(json.dumps(
            {"t": "joined", "room": room.code, "token": conn.token,
             "nickname": conn.nickname, "host": conn is room.host},
            ensure_ascii=False))
        room.broadcast_state()
        await self._connection_loop(ws, room, conn)

    async def _err(self, ws: WebSocket, text: str) -> None:
        await ws.send_text(json.dumps({"t": "room_error", "text": text},
                                      ensure_ascii=False))

    async def _connection_loop(self, ws: WebSocket, room: Room,
                               conn: HumanConnection) -> None:
        async def pump_out():
            while True:
                m = await conn.feed_q.get()
                await ws.send_text(json.dumps(m, ensure_ascii=False))

        out_task = asyncio.create_task(pump_out())
        try:
            while True:
                m = json.loads(await ws.receive_text())
                await room.handle_client_msg(conn, m)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            out_task.cancel()
            room.on_disconnect(conn)

    # ---------- 历史存档（与单人模式共用 archive.py） ----------
    async def send_history_list(self, conn: HumanConnection) -> None:
        conn.feed({"t": "history_list", "games": archive.list_games()})

    async def send_history_game(self, conn: HumanConnection, hist_id: str) -> None:
        g = archive.load_game(hist_id)
        if g is None:
            conn.feed({"t": "toast", "text": "找不到该历史对局"})
            return
        conn.feed({"t": "history_game", "game": g})
