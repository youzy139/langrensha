"""复盘报告（加分项）：赛后让一个 LLM 当解说员，结合完整事件流和
每个 Agent 的内心 reasoning，分析各玩家的高光与失误操作，输出 Markdown。"""

from __future__ import annotations

import json
from pathlib import Path

from .llm import LLMClient
from .roles import ROLE_NAMES

_REASONING_MAX = 300  # 每条内心戏节选长度，控制 prompt 体积

_COMMENTATOR_PROMPT = (
    "你是一名资深狼人杀解说员，风格犀利但公正。下面给你一局 6 人狼人杀的"
    "完整对局摘要，包含公开事件、夜间行动、以及每个 Agent 的内心思考（【内心】标记）。\n"
    "请输出一份 Markdown 复盘报告，结构如下：\n"
    "## 战局概述（100 字以内）\n"
    "## 逐轮点评（每轮 1-2 句，点出关键转折）\n"
    "## 玩家表现（每个玩家一节：角色、高光操作、失误操作、评分 1-10）\n"
    "## MVP 与最迷惑操作（各一名，说明理由）\n"
    "注意：只有你知道全部真相，点评时要利用夜间行动和内心思考指出"
    "“玩家当时为什么做对/做错”，不要泛泛而谈。"
)


def build_digest(log_path: str | Path) -> str:
    """把 JSONL 日志提炼成解说员可读的紧凑战报。"""
    lines: list[str] = []
    for line in open(log_path, "r", encoding="utf-8"):
        e = json.loads(line)
        t = e.get("event")
        r = e.get("round", "")
        if t == "game_start":
            roles = "；".join(f"{p['name']}={ROLE_NAMES.get(p['role'], p['role'])}"
                              for p in e.get("players", []))
            lines.append(f"【身份底牌】{roles}")
        elif t == "werewolf_channel":
            lines.append(f"[R{r}狼人频道] {e['speaker']}: {e['message']}")
        elif t == "night_kill":
            lines.append(f"[R{r}夜] 狼人投票 {e['votes']} → 刀 {e['target']}")
        elif t == "night_seer":
            lines.append(f"[R{r}夜] 预言家 {e['seer']} 验 {e['checked']} → {e['result']}")
        elif t == "night_witch":
            act = []
            if e.get("saved"):
                act.append("用了解药")
            if e.get("poisoned"):
                act.append(f"毒了 {e['poisoned']}")
            lines.append(f"[R{r}夜] 女巫 {e['witch']}：{'，'.join(act) or '未用药'}")
        elif t == "day_announce":
            deaths = e.get("deaths") or []
            lines.append(f"[R{r}白天公告] {'、'.join(deaths) + ' 死亡' if deaths else '平安夜'}")
        elif t == "day_speech":
            lines.append(f"[R{r}发言] {e['speaker']}: {e['speech']}")
        elif t == "day_vote":
            votes = "，".join(f"{k}→{v or '弃权'}" for k, v in e.get("votes", {}).items())
            lines.append(f"[R{r}投票] {votes} ⇒ 放逐 {e.get('exiled') or '无人（平票）'}")
        elif t == "game_end":
            winner = "好人阵营" if e.get("winner") == "village" else "狼人阵营"
            lines.append(f"【结局】{winner}获胜（{e.get('reason', '')}）")
        elif t == "llm_call" and e.get("success") and e.get("reasoning"):
            reasoning = e["reasoning"][:_REASONING_MAX]
            lines.append(f"  【内心】{e['player']}({e['action']}): {reasoning}")
    return "\n".join(lines)


async def generate_review(config: dict, log_path: str | Path,
                          client: LLMClient | None = None) -> str:
    """生成复盘报告 Markdown。Mock 模式输出基于事实的模板复盘（不调 LLM）。"""
    log_path = Path(log_path)
    digest = build_digest(log_path)
    client = client or LLMClient(config)

    if client.mock:
        return ("# 复盘报告（Mock 模式 · 未调用 LLM）\n\n"
                "以下为对局事实摘要：\n\n```\n" + digest + "\n```")

    model = config.get("llm", {}).get("default_model", "gpt-4o-mini")
    messages = [
        {"role": "system", "content": _COMMENTATOR_PROMPT},
        {"role": "user", "content": f"对局摘要：\n{digest}"},
    ]
    try:
        review_tokens = config.get("llm", {}).get("review_max_tokens", 4000)
        content, _ = await client.chat(model, messages, max_tokens=review_tokens)
    except Exception as e:
        return f"# 复盘报告生成失败\n\nLLM 调用出错：`{e!r}`\n\n对局摘要：\n\n```\n{digest}\n```"
    if not content:
        return ("# 复盘报告生成失败\n\nLLM 返回空内容（可尝试调大 max_tokens）。\n\n"
                "对局摘要：\n\n```\n" + digest + "\n```")
    return content
