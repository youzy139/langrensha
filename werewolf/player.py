"""PlayerAgent：每个玩家一个实例。

- 私有记忆（private_notes）：只有自己可见（身份、验人结果、夜间行动）。
- 公开记忆（public_log）：所有玩家共享的发言、投票、死讯——由 GameMaster 统一广播。
- 所有决策走 chat_json 结构化输出；解析失败自动重试；重试耗尽后随机兜底，保证不卡死。
"""

from __future__ import annotations

import random
from typing import Optional

from .llm import LLMClient
from .roles import ROLE_NAMES, ROLE_PROMPTS


def _format_public(public_log: list[str]) -> str:
    if not public_log:
        return "（暂无公开信息）"
    return "\n".join(public_log)


def _format_private(private_notes: list[str]) -> str:
    if not private_notes:
        return "（暂无私密信息）"
    return "\n".join(private_notes)


class PlayerAgent:
    def __init__(self, name: str, role: str, model: str, all_players: list[str],
                 mates: list[str], client: LLMClient, speech_max_chars: int = 200,
                 rng: Optional[random.Random] = None):
        self.name = name
        self.role = role
        self.model = model
        self.client = client
        self.mates = mates  # 狼队友（非狼为空列表）
        self.speech_max_chars = speech_max_chars
        self.rng = rng or random.Random()
        self.public_log: list[str] = []
        self.private_notes: list[str] = []
        self.alive = True
        self.system_prompt = ROLE_PROMPTS[role].format(
            name=name,
            n_players=len(all_players),
            players="、".join(all_players),
            mates="、".join(mates) if mates else "（无）",
        )

    # ---------- 记忆 ----------
    def hear(self, line: str) -> None:
        """接收 GameMaster 广播的公开信息。"""
        self.public_log.append(line)

    def note(self, line: str) -> None:
        """写入私密信息。"""
        self.private_notes.append(line)

    def _context_messages(self, instruction: str) -> list[dict]:
        user = (
            f"【公开信息】\n{_format_public(self.public_log)}\n\n"
            f"【你的私密信息】\n{_format_private(self.private_notes)}\n\n"
            f"【当前任务】\n{instruction}"
        )
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user},
        ]

    # ---------- 白天发言 ----------
    async def speak(self, round_no: int) -> str:
        instruction = (
            f"现在是第 {round_no} 轮白天，轮到你发言。"
            f"请发表一段不超过 {self.speech_max_chars} 字的发言。"
            "发言要求：结合目前所有公开信息给出实质内容——你怀疑谁、依据哪条发言/投票/死讯、"
            "你的投票倾向；如果你决定亮身份或跳身份（含战术性跳假身份），"
            "把身份信息和查验/经历讲完整。禁止只说「我是好人过」这类划水发言。"
            '只输出 JSON：{"speech": "你的发言内容"}'
        )
        async def mock():
            return {"speech": self.rng.choice([
                "我没什么信息，先听大家发言。",
                "我觉得昨晚的死亡很可疑，大家分析一下谁在带节奏。",
                "我怀疑有人跳假身份，投票别乱跟。",
                "我是好人，过。",
            ])}
        data, _ = await self.client.chat_json(
            player=self.name, action="speak", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["speech"], mock_fn=mock,
            round_no=round_no, phase="day_speech",
        )
        speech = (data or {}).get("speech")
        if not speech:
            # 兜底通道：JSON 全部失败时，让模型直接说人话（不要任何格式），
            # 避免「思考过载」破坏游戏体验
            try:
                raw, _ = await self.client.chat(
                    self.model,
                    self._context_messages(
                        f"现在是第 {round_no} 轮白天，轮到你发言。"
                        f"直接用一两句话发言（不超过 {self.speech_max_chars} 字），"
                        "不要输出 JSON、不要解释、不要前缀。"),
                    max_tokens=self.client.max_tokens * 2,
                )
                speech = raw.strip().strip('"') or None
            except Exception:
                speech = None
        return str(speech or "（思考过载，发言略过）")[: self.speech_max_chars]

    # ---------- 投票放逐 ----------
    async def vote(self, candidates: list[str], round_no: int) -> Optional[str]:
        cand = "、".join(candidates)
        instruction = (
            f"现在是第 {round_no} 轮白天投票环节。存活玩家：{cand}。"
            "请投出你认为最可能是狼人的一名玩家（不能投自己，可以投“弃权”）。"
            '只输出 JSON：{"vote": "玩家代号或弃权"}'
        )
        async def mock():
            pool = [c for c in candidates if c != self.name]
            return {"vote": self.rng.choice(pool) if pool else "弃权"}
        data, _ = await self.client.chat_json(
            player=self.name, action="vote", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["vote"], mock_fn=mock,
            round_no=round_no, phase="day_vote",
        )
        return self._resolve_choice((data or {}).get("vote"), candidates)

    # ---------- 狼人夜间协商与刀人 ----------
    async def werewolf_discuss(self, channel: list[str], alive_targets: list[str],
                               round_no: int) -> str:
        history = "\n".join(channel) if channel else "（频道暂无消息）"
        instruction = (
            f"现在是第 {round_no} 轮夜晚，狼人频道聊天记录：\n{history}\n"
            f"可刀目标（非狼人存活玩家）：{'、'.join(alive_targets)}。"
            "请对队友说一句简短的战术建议（不超过 50 字，此频道只有狼人可见）。"
            '只输出 JSON：{"message": "你想说的话"}'
        )
        async def mock():
            return {"message": f"建议刀 {self.rng.choice(alive_targets)}。"}
        data, _ = await self.client.chat_json(
            player=self.name, action="werewolf_discuss", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["message"], mock_fn=mock,
            round_no=round_no, phase="night_wolf_discuss",
        )
        return str((data or {}).get("message") or "……")[:50]

    async def werewolf_kill_vote(self, channel: list[str], alive_targets: list[str],
                                 round_no: int) -> str:
        history = "\n".join(channel) if channel else "（频道暂无消息）"
        instruction = (
            f"狼人频道讨论记录：\n{history}\n"
            f"请投票选择今晚的刀人目标：{'、'.join(alive_targets)}。"
            '只输出 JSON：{"kill": "玩家代号"}'
        )
        async def mock():
            return {"kill": self.rng.choice(alive_targets)}
        data, _ = await self.client.chat_json(
            player=self.name, action="werewolf_kill", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["kill"], mock_fn=mock,
            round_no=round_no, phase="night_wolf_kill",
        )
        choice = self._resolve_choice((data or {}).get("kill"), alive_targets)
        return choice or self.rng.choice(alive_targets)

    # ---------- 预言家验人 ----------
    async def seer_check(self, candidates: list[str], round_no: int) -> str:
        instruction = (
            f"现在是第 {round_no} 轮夜晚，请选择一个玩家查验身份："
            f"{'、'.join(candidates)}。"
            '只输出 JSON：{"check": "玩家代号"}'
        )
        async def mock():
            return {"check": self.rng.choice(candidates)}
        data, _ = await self.client.chat_json(
            player=self.name, action="seer_check", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["check"], mock_fn=mock,
            round_no=round_no, phase="night_seer",
        )
        choice = self._resolve_choice((data or {}).get("check"), candidates)
        return choice or self.rng.choice(candidates)

    # ---------- 女巫用药 ----------
    async def witch_action(self, killed: Optional[str], has_antidote: bool,
                           has_poison: bool, can_self_save: bool,
                           alive_others: list[str], round_no: int) -> dict:
        save_hint = "（你被刀了，第一晚可以自救）" if killed == self.name and can_self_save else ""
        instruction = (
            f"现在是第 {round_no} 轮夜晚。"
            f"今晚被狼人刀的玩家是：{killed or '（信息缺失）'}{save_hint}。\n"
            f"你还有解药：{'有' if has_antidote else '无'}；毒药：{'有' if has_poison else '无'}。"
            "同一晚只能用一瓶药。\n"
            f"可用毒药的目标：{'、'.join(alive_others)}。\n"
            '只输出 JSON：{"save": true或false, "poison": "玩家代号或null"}'
        )
        async def mock():
            poison = None
            if has_poison and alive_others and self.rng.random() < 0.25:
                poison = self.rng.choice(alive_others)
            save = bool(has_antidote and killed == self.name and can_self_save)
            if poison:
                save = False
            return {"save": save, "poison": poison}
        data, _ = await self.client.chat_json(
            player=self.name, action="witch_action", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["save", "poison"], mock_fn=mock,
            round_no=round_no, phase="night_witch",
        )
        data = data or {}
        save = bool(data.get("save")) and has_antidote
        poison = None
        if has_poison and not save:
            poison = self._resolve_choice(data.get("poison"), alive_others)
        if not can_self_save and killed == self.name:
            save = False  # 首夜之后不能自救
        return {"save": save, "poison": poison}

    # ---------- 猎人开枪 ----------
    async def hunter_shot(self, candidates: list[str], round_no: int,
                          cause: str) -> Optional[str]:
        """死亡时开枪。cause：'被狼人刀死' 或 '被投票放逐'。"""
        if not candidates:
            return None
        instruction = (
            f"你{cause}，现在可以开枪带走一名存活玩家：{'、'.join(candidates)}。"
            "带走你最有把握的狼人；如果完全没有把握，也可以选择不开枪。"
            '只输出 JSON：{"shoot": "玩家代号或null"}'
        )
        async def mock():
            if self.rng.random() < 0.6:
                return {"shoot": self.rng.choice(candidates)}
            return {"shoot": None}
        data, _ = await self.client.chat_json(
            player=self.name, action="hunter_shot", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["shoot"], mock_fn=mock,
            round_no=round_no, phase="hunter_shot",
        )
        return self._resolve_choice((data or {}).get("shoot"), candidates)

    # ---------- 赛后复盘交流 ----------
    async def post_game_chat(self, question: str, asker: str) -> str:
        """游戏结束后，带着全部私密信息回应复盘提问。"""
        instruction = (
            f"游戏已经结束，所有身份已经公开。现在是赛后复盘交流时间，"
            f"{asker} 对大家说：「{question}」。\n"
            "请坦诚回应：公开你当时掌握的私密信息（身份、夜间行动、验人结果等）、"
            "你当时的推理过程、以及你为什么那样操作。就像真实玩家赛后聊天一样，"
            "可以自嘲、可以解释、可以甩锅，不超过 120 字。"
            '只输出 JSON：{"reply": "你的回应"}'
        )
        async def mock():
            secret = self.private_notes[-1] if self.private_notes else "没有特殊信息"
            return {"reply": f"我是{self.name}（{ROLE_NAMES[self.role]}）。"
                             f"我这局的私密信息：{secret}。当时主要跟着局势走，"
                             f"打得不好多包涵。"}
        data, _ = await self.client.chat_json(
            player=self.name, action="post_game_chat", model=self.model,
            messages=self._context_messages(instruction),
            required_keys=["reply"], mock_fn=mock,
            round_no=0, phase="post_game",
        )
        return str((data or {}).get("reply") or "（无话可说）")[:150]

    # ---------- 工具 ----------
    def _resolve_choice(self, raw, candidates: list[str]) -> Optional[str]:
        """把模型输出模糊匹配到合法候选人。"""
        if raw is None:
            return None
        text = str(raw).strip()
        if text in ("弃权", "abstain", "null", "None", ""):
            return None
        for c in candidates:
            if text == c:
                return c
        for c in candidates:  # 模糊包含
            if c in text or text in c:
                return c
        return None
