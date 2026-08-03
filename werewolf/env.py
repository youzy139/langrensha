"""项目根目录 .env 加载器。

把 KEY=VALUE 写入进程环境（不覆盖已存在的变量），
让 `python main.py`、webapp/server.py 在任何启动方式下都能拿到 LLM 配置，
无需手动 export / setx。.env 已加入 .gitignore，不会入库。
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_file = _ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env()  # 模块导入即生效
