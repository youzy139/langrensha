"""结构化 JSONL 日志 + 可读控制台输出。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class GameLogger:
    """把所有公开/私密事件写入 JSONL，同时把关键公开事件打到终端。"""

    def __init__(self, log_path: str | Path, console: bool = True, mode: str = "w"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.log_path, mode, encoding="utf-8")
        self.console = console
        self.game_id = f"game-{int(time.time() * 1000)}"

    def event(self, event_type: str, **payload: Any) -> None:
        record = {
            "ts": round(time.time(), 3),
            "game_id": self.game_id,
            "event": event_type,
            **payload,
        }
        if self._fp.closed:
            # 对局结束后日志已被 close()，但赛后讨论仍会触发 llm_call 日志。
            # 重新以追加模式打开，避免 "I/O operation on closed file" 干掉赛后发言。
            self._fp = open(self.log_path, "a", encoding="utf-8")
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()

    def print(self, text: str = "") -> None:
        if self.console:
            print(text, flush=True)

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass
