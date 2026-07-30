"""批量实验：连跑 N 局并统计胜率（支持断点续跑）。

用法：
  python run_experiment.py --total 10 --budget 270
    # 在 budget 秒内尽量多跑，已完成的对局自动跳过，可反复调用直到跑满
  python run_experiment.py --total 10 --stats-only   # 只汇总统计
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import yaml

from werewolf.gamemaster import GameMaster
from werewolf.logger import GameLogger

LOG_DIR = Path("logs")  # 可通过 --logdir 覆盖


def set_log_dir(p: str) -> None:
    global LOG_DIR
    LOG_DIR = Path(p)


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if '"game_end"' in line:
                    return True
    except Exception:
        pass
    return False


async def run_one(config: dict, log_path: Path, seed: int) -> str:
    """跑一局；若存在断点存档则续跑（日志追加），完成后删除存档。"""
    ckpt_path = log_path.with_suffix(".checkpoint.json")
    resume_stage = None
    state = None
    if ckpt_path.exists():
        try:
            state = json.loads(ckpt_path.read_text(encoding="utf-8"))
            resume_stage = state.get("stage")
        except Exception:
            state = None
    # 续跑时追加日志而不是覆盖
    logger = GameLogger(log_path, console=False,
                        mode="a" if state is not None else "w")
    gm = GameMaster(config, logger, rng=random.Random(seed),
                    checkpoint_path=str(ckpt_path))
    try:
        if state is not None:
            gm.set_state(state)
            print(f"       （从第 {state['round_no']} 轮 {resume_stage} 断点续跑）", flush=True)
        winner = await gm.run(resume_stage=resume_stage)
        ckpt_path.unlink(missing_ok=True)  # 完成后清除存档
        return winner
    finally:
        await gm.client.aclose()
        logger.close()


def collect_stats(total: int) -> dict:
    games = []
    for i in range(1, total + 1):
        path = LOG_DIR / f"game_{i}.jsonl"
        if not is_complete(path):
            continue
        start = end = None
        votes_by_round = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                e = json.loads(line)
                if e["event"] == "game_start":
                    start = e
                elif e["event"] == "game_end":
                    end = e
                elif e["event"] == "llm_call" and not e.get("success"):
                    votes_by_round += 1
        if start and end:
            games.append({"start": start, "end": end,
                          "llm_failures": votes_by_round})

    camp_wins = defaultdict(int)
    role_games = defaultdict(int)
    role_wins = defaultdict(int)
    wolf_alive_total = wolf_total = 0
    rounds = []
    llm_failures = 0

    for g in games:
        winner = g["end"]["winner"]
        camp_wins[winner] += 1
        rounds.append(g["end"].get("rounds", 0))
        llm_failures += g["llm_failures"]
        roles = {p["name"]: p["role"] for p in g["start"]["players"]}
        for name, info in g["end"]["players"].items():
            role = info["role"]
            role_games[role] += 1
            won = (winner == "werewolf") == (role == "werewolf")
            if won:
                role_wins[role] += 1
            if role == "werewolf":
                wolf_total += 1
                if info["alive"]:
                    wolf_alive_total += 1

    return {
        "completed": len(games),
        "camp_wins": dict(camp_wins),
        "avg_rounds": round(sum(rounds) / len(rounds), 2) if rounds else 0,
        "role_stats": {r: {"games": role_games[r], "wins": role_wins[r],
                           "win_rate": round(role_wins[r] / role_games[r], 3)}
                       for r in sorted(role_games)},
        "wolf_survival_rate": round(wolf_alive_total / wolf_total, 3) if wolf_total else 0,
        "llm_failed_attempts": llm_failures,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--total", type=int, default=10)
    ap.add_argument("--budget", type=float, default=270,
                    help="本次调用的时间预算（秒），超时前不再开新局")
    ap.add_argument("--seed-base", type=int, default=1000)
    ap.add_argument("--logdir", default="logs", help="对局日志目录（分组实验用）")
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    set_log_dir(args.logdir)
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    LOG_DIR.mkdir(exist_ok=True)

    if not args.stats_only:
        t0 = time.time()
        for i in range(1, args.total + 1):
            path = LOG_DIR / f"game_{i}.jsonl"
            if is_complete(path):
                print(f"[skip] game_{i} 已完成", flush=True)
                continue
            if time.time() - t0 > args.budget:
                print(f"[budget] 时间预算用尽，剩余对局下次再跑", flush=True)
                break
            print(f"[run ] game_{i} ...", flush=True)
            winner = asyncio.run(run_one(config, path, args.seed_base + i))
            print(f"[done] game_{i} → {winner}（耗时 {time.time()-t0:.0f}s）", flush=True)

    stats = collect_stats(args.total)
    out = LOG_DIR / "stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)
    print(f"统计已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
