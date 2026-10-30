"""Web 对局存档：单人与多人房间共用。

每局一个目录 data/web/<对局ID>/：
- events.jsonl  引擎完整日志（含 prompt/回复/reasoning，复盘读它）
- record.json   前端回放用的精简记录（对话流 + 身份 + 复盘），局终写入

只有 events.jsonl 没有 record.json 的目录是中途断开的对局，列表里不显示。
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from werewolf.paths import data_dir

_ID = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
LIST_LIMIT = 30


def web_dir() -> Path:
    return data_dir("web")  # Mock 模式下自动落到 data/mock/web


def new_game() -> tuple[str, Path]:
    """为新对局分配 ID 和目录，返回 (id, events.jsonl 路径)。"""
    gid = time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)
    d = web_dir() / gid
    d.mkdir(parents=True, exist_ok=True)
    return gid, d / "events.jsonl"


def save_record(gid: str, record: dict) -> None:
    record["id"] = gid
    (web_dir() / gid / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


def _summary(gid: str, g: dict) -> dict:
    human = g.get("human") or ""
    me = next((p for p in g.get("players", []) if p["name"] == human), {})
    return {"id": gid, "ts": g.get("ts", gid), "cfg": g.get("cfg", ""),
            "winner": g.get("winner", ""), "rounds": g.get("rounds"),
            "mode": "room" if g.get("room") else "single",
            "human": human, "human_role": me.get("role", ""),
            "human_role_name": me.get("role_name", "")}


def list_games() -> list[dict]:
    games = []
    for d in sorted(web_dir().iterdir(), reverse=True):
        f = d / "record.json"
        if not f.is_file():
            continue
        try:
            games.append(_summary(d.name, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError):
            continue
        if len(games) >= LIST_LIMIT:
            break
    return games


def load_game(gid: str) -> dict | None:
    if not _ID.match(gid or ""):  # 拒绝 ../ 之类的路径
        return None
    f = web_dir() / gid / "record.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text(encoding="utf-8"))
