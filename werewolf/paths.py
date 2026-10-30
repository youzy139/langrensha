"""运行产物的统一存放位置：所有对局数据都在项目根的 data/ 下，按来源归类。

data/
├── web/<对局ID>/        Web 对局：record.json（前端回放）+ events.jsonl（引擎完整日志）
├── cli/                 main.py 命令行对局：日志 / HTML 回放 / 复盘
├── experiments/<组>/    run_experiment.py 批量实验（只有 stats.json 入库）
└── mock/                WEREWOLF_MOCK=1 的离线测试产物，结构同上，可整个删掉

Mock 模式自动写进 data/mock/，测试跑多少遍都不会混进真实对局记录。
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def is_mock() -> bool:
    return os.environ.get("WEREWOLF_MOCK", "") == "1"


def data_dir(kind: str) -> Path:
    """返回 data/<kind>（Mock 模式下为 data/mock/<kind>），不存在则创建。"""
    base = DATA_DIR / "mock" if is_mock() else DATA_DIR
    d = base / kind
    d.mkdir(parents=True, exist_ok=True)
    return d
