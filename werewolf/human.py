"""人类玩家接入：让使用者替换任意 AI 玩家，亲自参与对局。

HumanAgent 与 PlayerAgent 接口完全一致，GameMaster 无需感知差异；
区别只在于：决策从"调 LLM"变成"问终端"，私密信息实时打印给人类。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .player import PlayerAgent
from .roles import ROLE_NAMES


class HumanAgent(PlayerAgent):
    """人类玩家：通过终端接收信息、输入决策。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_name = ROLE_NAMES[self.role]
        print("\n" + "=" * 50)
        print(f"🎭 你的身份是【{role_name}】")
        if self.role == "werewolf":
            print(f"🐺 你的狼队友是：{'、'.join(self.mates)}")
        elif self.role == "witch":
            print("🧪 你有解药、毒药各一瓶（同晚限用一瓶，仅首夜可自救）")
        elif self.role == "seer":
            print("🔮 每晚可查验一名玩家是否为狼人")
        elif self.role == "hunter":
            print("🔫 你死亡（非被毒）时可以开枪带走一人")
        print("=" * 50 + "\n", flush=True)

    # ---------- 信息接收：私密信息实时打印（公开信息由上帝统一打印） ----------
    def note(self, line: str) -> None:
        super().note(line)
        print(f"  🔒 [仅你可见] {line}", flush=True)

    def wolf_hear(self, line: str) -> None:
        """队友在狼人频道发言：实时打印（仅狼可见）。"""
        print(f"  🐺 [狼人频道] {line}", flush=True)

    # ---------- 输入工具 ----------
    async def _ask(self, prompt: str) -> str:
        """异步包装阻塞式 input，避免卡住事件循环。"""
        try:
            return (await asyncio.to_thread(input, prompt)).strip()
        except (EOFError, KeyboardInterrupt):
            self._stdin_eof = True  # 标记输入流耗尽，避免必选问题时死循环
            print("\n（输入中断，按弃权/随机处理）")
            return ""

    async def _ask_choice(self, prompt: str, candidates: list[str],
                          allow_abstain: bool = True,
                          allow_self: bool = False) -> Optional[str]:
        pool = [c for c in candidates if allow_self or c != self.name]
        while True:
            raw = await self._ask(prompt)
            if allow_abstain and raw in ("", "弃权", "q"):
                return None
            choice = self._resolve_choice(raw, pool)
            if choice:
                return choice
            if getattr(self, "_stdin_eof", False):
                return None  # 输入流不可用：由调用方随机兜底
            print(f"  ⚠️ 无效输入，请输入：{'、'.join(pool)}"
                  f"{'（或回车弃权）' if allow_abstain else ''}")

    # ---------- 各决策点 ----------
    async def speak(self, round_no: int) -> str:
        print(f"\n💬 轮到你发言（第 {round_no} 轮，不超过 {self.speech_max_chars} 字）")
        text = await self._ask("你的发言> ")
        return (text or "（我选择沉默）")[: self.speech_max_chars]

    async def vote(self, candidates: list[str], round_no: int) -> Optional[str]:
        print(f"\n🗳 投票放逐（第 {round_no} 轮）")
        return await self._ask_choice("你投给谁（回车弃权）> ", candidates)

    async def werewolf_discuss(self, channel: list[str], alive_targets: list[str],
                               round_no: int) -> str:
        print(f"\n🐺 狼人频道（第 {round_no} 夜，只有狼人可见）")
        if channel:
            for line in channel:
                print(f"   {line}")
        msg = await self._ask("你对队友说（≤50 字）> ")
        return (msg or "……")[:50]

    async def werewolf_kill_vote(self, channel: list[str], alive_targets: list[str],
                                 round_no: int) -> str:
        print(f"🔪 今晚刀谁？目标：{'、'.join(alive_targets)}")
        choice = await self._ask_choice("你的刀人票> ", alive_targets,
                                        allow_abstain=False)
        return choice or self.rng.choice(alive_targets)

    async def seer_check(self, candidates: list[str], round_no: int) -> str:
        print(f"\n🔮 预言家验人（第 {round_no} 夜）")
        choice = await self._ask_choice("查验谁> ", candidates, allow_abstain=False)
        return choice or self.rng.choice(candidates)

    async def witch_action(self, killed: Optional[str], has_antidote: bool,
                           has_poison: bool, can_self_save: bool,
                           alive_others: list[str], round_no: int) -> dict:
        print(f"\n🧪 女巫行动（第 {round_no} 夜）今晚被刀的是：{killed or '未知'}")
        save = False
        if has_antidote and killed:
            if killed == self.name and not can_self_save:
                print("   （被刀的是你，但首夜之后不能自救）")
            else:
                raw = await self._ask(f"用解药救 {killed} 吗？(y/N)> ")
                save = raw.lower() in ("y", "yes", "救", "是")
        poison = None
        if has_poison and not save:
            poison = await self._ask_choice(
                f"用毒药毒谁？（目标：{'、'.join(alive_others)}，回车不用）> ",
                alive_others)
        return {"save": save, "poison": poison}

    async def hunter_shot(self, candidates: list[str], round_no: int,
                          cause: str) -> Optional[str]:
        print(f"\n🔫 你{cause}，可以开枪带走一人！存活：{'、'.join(candidates)}")
        return await self._ask_choice("开枪打谁（回车不开枪）> ", candidates)
