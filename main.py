"""多 Agent 狼人杀入口：python main.py 一键跑完一局。

用法：
  python main.py                     # 跑一局（需要 LLM_BASE_URL / LLM_API_KEY 环境变量）
  python main.py --games 3           # 连跑 3 局
  WEREWOLF_MOCK=1 python main.py     # Mock 模式离线测试（无需 API Key）
  python main.py --replay            # 结束后生成 HTML 回放页
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path

import yaml

from werewolf.gamemaster import GameMaster
from werewolf.logger import GameLogger
from werewolf.replay import generate_replay
from werewolf.review import generate_review


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_game(config: dict, game_index: int, log_path: Path,
                   seed: int | None) -> str:
    logger = GameLogger(log_path)
    rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
    gm = GameMaster(config, logger, rng=rng)
    try:
        winner = await gm.run()
        return winner
    finally:
        await gm.client.aclose()
        logger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="多 Agent 狼人杀")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--games", type=int, default=1, help="连跑局数")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    parser.add_argument("--replay", action="store_true", help="结束后生成 HTML 回放页")
    parser.add_argument("--review", action="store_true",
                        help="结束后让 LLM 解说员生成复盘报告（Markdown + 嵌入回放页）")
    args = parser.parse_args()

    config = load_config(args.config)
    results = []
    for i in range(1, args.games + 1):
        log_path = Path(f"game_log_{i}.jsonl") if args.games > 1 else Path("game_log.jsonl")
        print(f"\n########## 第 {i}/{args.games} 局 ##########")
        seed = (args.seed + i - 1) if args.seed is not None else None
        winner = asyncio.run(run_game(config, i, log_path, seed))
        results.append((i, winner, str(log_path)))
        print(f"第 {i} 局日志：{log_path}")
        review_md = None
        if args.review:
            print("解说员复盘中……")
            review_md = asyncio.run(generate_review(config, log_path))
            md_path = log_path.with_suffix(".review.md")
            md_path.write_text(review_md, encoding="utf-8")
            print(f"第 {i} 局复盘：{md_path}")
        if args.replay:
            html = generate_replay(log_path, review_md=review_md)
            print(f"第 {i} 局回放：{html}")

    if args.games > 1:
        wolves = sum(1 for _, w, _ in results if w == "werewolf")
        print(f"\n===== {args.games} 局汇总：狼人胜 {wolves}，好人胜 {args.games - wolves} =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
