"""把引擎的控制台文本翻译成前端可直接渲染的结构化消息。

引擎（GameMaster）为命令行设计，只打印纯文本行；Web 端在这里统一翻译，
前端不必再猜文本格式。旧版存档的迁移也复用同一套规则。
每条消息都保留原文 text 字段，前端遇到不认识的 kind 也能原样显示。
"""

from __future__ import annotations

import re

_PHASE = re.compile(r"^-{3,}\s*第\s*(\d+)\s*轮\s*·\s*(夜晚|白天)\s*-{3,}$")
_SPEECH = re.compile(r"^\[发言\]\s*([^:：\s]+)\s*[:：]\s?(.*)$", re.S)
_VOTE = re.compile(r"^\[投票\]\s*(\S+)\s*→\s*(.+)$")
_NOTICE = re.compile(r"^\[公告\]\s*(.*)$", re.S)
_END = re.compile(r"^={3,}\s*游戏结束[:：](.*?)\s*={3,}$", re.S)
_WOLF = re.compile(r"^🐺 狼人频道 · ([^:：\s（]+)(（你）)?\s*[:：]\s?(.*)$", re.S)


def public_msg(text: str) -> dict:
    """上帝公开输出的一行 → 结构化 feed 消息。"""
    t = text.strip("\n")
    base = {"t": "feed", "text": t}
    if m := _PHASE.match(t):
        return {**base, "kind": "phase", "round": int(m[1]),
                "phase": "night" if m[2] == "夜晚" else "day"}
    if m := _SPEECH.match(t):
        return {**base, "kind": "speech", "speaker": m[1], "text": m[2]}
    if m := _VOTE.match(t):
        target = m[2].strip()
        return {**base, "kind": "vote", "voter": m[1],
                "target": None if target == "弃权" else target}
    if m := _NOTICE.match(t):
        return {**base, "kind": "notice", "text": m[1]}
    if m := _END.match(t):
        return {**base, "kind": "end", "text": m[1].strip()}
    if t.startswith("身份揭晓："):
        return {**base, "kind": "reveal"}
    if t.startswith("🐺 狼人频道回放"):
        return {**base, "kind": "wolf_replay"}
    return {**base, "kind": "system"}


def wolf_msg(speaker: str, text: str) -> dict:
    """狼人频道的一句话（仅狼人可见）。"""
    return {"t": "feed", "kind": "wolf", "speaker": speaker, "text": text}


def legacy_wolf(text: str) -> dict:
    """旧存档里的狼人频道文本 "🐺 狼人频道 · Alice: ……" → 结构化。"""
    m = _WOLF.match(text)
    return wolf_msg(m[1], m[3]) if m else {"t": "feed", "kind": "wolf", "text": text}


def public_events(event_type: str, payload: dict) -> list[dict]:
    """引擎结构化事件 → 公开可见的前端消息（出局标记 / 计票结果）。

    只翻译白天公开的信息：夜里猎人被刀开枪带走的人，等第二天公告时
    随 day_announce 一起公布，不能提前推给前端（会泄露夜间信息）。
    """
    out: list[dict] = []
    if event_type == "day_announce":
        out += [{"t": "dead", "name": n, "cause": "night"} for n in payload.get("deaths") or []]
    elif event_type == "day_vote":
        out.append({"t": "vote_result", "round": payload.get("round"),
                    "votes": payload.get("votes", {}), "tally": payload.get("tally", {}),
                    "exiled": payload.get("exiled")})
        if payload.get("exiled"):
            out.append({"t": "dead", "name": payload["exiled"], "cause": "exile"})
    elif event_type == "hunter_shot" and payload.get("shot") \
            and payload.get("cause") != "被狼人刀死":
        out.append({"t": "dead", "name": payload["shot"], "cause": "shot"})
    return out


# 存档里需要保留的消息类型（回放时按原顺序重放）
RECORDED = {"feed", "role", "dead", "vote_result"}


def game_over_msg(gm, winner: str) -> dict:
    """终局消息：胜者 + 每个人的身份与存活（reveal 文本保留给旧前端/存档）。"""
    from werewolf.roles import ROLE_NAMES
    players = [{"name": p.name, "role": p.role, "role_name": ROLE_NAMES[p.role],
                "alive": p.alive} for p in gm.players.values()]
    return {"t": "game_over", "winner": winner, "rounds": gm.round_no,
            "players": players,
            "reveal": "；".join(f"{p['name']}={p['role_name']}" for p in players)}
