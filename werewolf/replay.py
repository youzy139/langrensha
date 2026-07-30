"""从 game_log.jsonl 生成一个自包含的 HTML 回放页面（加分项）。"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

_VISIBLE_LABEL = {
    "god": "👁 仅上帝",
    "werewolf_only": "🐺 仅狼人可见",
    "seer_only": "🔮 仅预言家可见",
    "witch_only": "🧪 仅女巫可见",
}

_EVENT_TITLES = {
    "game_start": "游戏开始",
    "phase": None,  # 按内容渲染
    "werewolf_channel": "狼人频道",
    "night_kill": "狼人刀人",
    "night_seer": "预言家验人",
    "night_witch": "女巫行动",
    "night_result": "夜晚结算",
    "day_announce": "白天公告",
    "day_speech": "发言",
    "day_vote": "投票",
    "hunter_shot": "猎人开枪",
    "game_end": "游戏结束",
    "llm_call": "LLM 调用",
}


def _esc(x) -> str:
    return html.escape(str(x))


def _render_event(ev: dict) -> str:
    kind = ev.get("event", "")
    r = ev.get("round", "")
    vis = ev.get("visibility")
    badge = f'<span class="vis">{_VISIBLE_LABEL.get(vis, vis)}</span>' if vis else ""

    if kind == "llm_call":  # 完整 prompt/回复太长，默认折叠
        raw = _esc(ev.get("raw_response", ""))[:2000]
        msgs = _esc(json.dumps(ev.get("messages", []), ensure_ascii=False, indent=1))[:6000]
        ok = "ok" if ev.get("success") else "fail"
        return (
            f'<details class="llm {ok}"><summary>LLM #{r} {ev.get("phase","")} '
            f'{_esc(ev.get("player",""))} · {_esc(ev.get("action",""))} · {ok}</summary>'
            f"<h4>Prompt</h4><pre>{msgs}</pre><h4>Response</h4><pre>{raw}</pre></details>"
        )
    title = _EVENT_TITLES.get(kind, kind)
    body = _esc(json.dumps({k: v for k, v in ev.items()
                            if k not in ("ts", "game_id", "event")}, ensure_ascii=False))
    return (f'<div class="ev ev-{kind}"><span class="rd">R{r}</span> '
            f"<b>{_esc(title)}</b>{badge}<pre>{body}</pre></div>")


def _md_to_html(md: str) -> str:
    """极简 Markdown 渲染：标题、加粗、列表、换行。"""
    out = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("### "):
            out.append(f"<h4>{_esc(s[4:])}</h4>")
        elif s.startswith("## "):
            out.append(f"<h3>{_esc(s[3:])}</h3>")
        elif s.startswith("# "):
            out.append(f"<h2>{_esc(s[2:])}</h2>")
        else:
            s = _esc(s)
            s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
            out.append(s if s else "")
    return "<br>\n".join(out)


def generate_replay(log_path: str | Path, review_md: str | None = None) -> Path:
    log_path = Path(log_path)
    events = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    start = next((e for e in events if e.get("event") == "game_start"), {})
    players = start.get("players", [])
    end = next((e for e in reversed(events) if e.get("event") == "game_end"), {})
    winner = {"village": "好人阵营", "werewolf": "狼人阵营"}.get(
        end.get("winner", ""), "未知")

    rows = "".join(
        f'<tr><td>{_esc(p["name"])}</td><td>{_esc(p["role"])}</td>'
        f'<td>{_esc(p.get("model", ""))}</td></tr>'
        for p in players)
    body = "\n".join(_render_event(e) for e in events)
    review_block = (f'<div class="review"><h2>🎙 解说员复盘</h2>{_md_to_html(review_md)}</div>'
                    if review_md else "")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>狼人杀回放 · {html.escape(log_path.name)}</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 900px; margin: 24px auto;
       padding: 0 16px; background: #1a1b26; color: #e0e0e0; }}
h1 {{ color: #bb9af7; }}
table {{ border-collapse: collapse; margin: 12px 0; }}
td, th {{ border: 1px solid #444; padding: 4px 10px; }}
.ev {{ background: #24283b; border-left: 3px solid #7aa2f7; margin: 8px 0;
       padding: 8px 12px; border-radius: 4px; }}
.ev-day_speech {{ border-left-color: #9ece6a; }}
.ev-day_vote {{ border-left-color: #e0af68; }}
.ev-werewolf_channel, .ev-night_kill {{ border-left-color: #f7768e; }}
.ev-game_end {{ border-left-color: #bb9af7; background: #2d2640; }}
.rd {{ color: #7aa2f7; font-weight: bold; margin-right: 6px; }}
.vis {{ font-size: 12px; color: #f7768e; margin-left: 8px; }}
pre {{ white-space: pre-wrap; word-break: break-all; font-size: 13px; margin: 6px 0; }}
details.llm {{ margin: 4px 0 4px 24px; font-size: 13px; }}
details.llm.fail summary {{ color: #f7768e; }}
summary {{ cursor: pointer; }}
.review {{ background: #2d2640; border: 1px solid #bb9af7; border-radius: 6px;
           padding: 12px 18px; margin: 16px 0; line-height: 1.7; }}
.review h2, .review h3, .review h4 {{ color: #bb9af7; margin: 10px 0 4px; }}
</style></head><body>
<h1>🐺 多 Agent 狼人杀回放</h1>
<p>胜者：<b>{_esc(winner)}</b> · 轮数：{end.get("rounds", "?")} · 事件数：{len(events)}</p>
<h2>玩家与身份</h2>
<table><tr><th>玩家</th><th>角色</th><th>模型</th></tr>{rows}</table>
{review_block}
<h2>事件流（LLM 调用折叠展示，点击展开完整 prompt 与回复）</h2>
{body}
</body></html>"""
    out = log_path.with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    return out
