"""GameMaster（上帝）：唯一掌握全量真相，驱动游戏状态机。

夜晚（狼人协商刀人 → 预言家验人 → 女巫用药）→
白天（公布死讯 → 轮流发言 → 投票放逐）→ 胜负判定。
屠边规则：狼人杀光全部神职或全部平民即胜。
"""

from __future__ import annotations

import asyncio
import random
from collections import Counter
from typing import Optional

from .llm import LLMClient
from .logger import GameLogger
from .player import PlayerAgent
from .roles import CIVILIAN_ROLES, GOD_ROLES, ROLE_NAMES


class GameMaster:
    def __init__(self, config: dict, logger: GameLogger,
                 rng: Optional[random.Random] = None,
                 checkpoint_path: Optional[str] = None,
                 human_agent_cls=None, human_kwargs: Optional[dict] = None):
        self.config = config
        game_cfg = config.get("game", {})
        self.max_rounds = game_cfg.get("max_rounds", 5)
        self.wolf_discuss_rounds = game_cfg.get("werewolf_discuss_rounds", 1)
        self.logger = logger
        self.rng = rng or random.Random()
        self.client = LLMClient(config, logger)
        self.round_no = 0
        self.players: dict[str, PlayerAgent] = {}
        self.witch_antidote = True
        self.witch_poison = True
        self.winner: Optional[str] = None
        self.checkpoint_path = checkpoint_path
        self.human_agent_cls = human_agent_cls      # Web 端可注入自定义人类 Agent
        self.human_kwargs = human_kwargs or {}
        self._build_players()

    # ---------- 断点存档 ----------
    def get_state(self, stage: str) -> dict:
        """阶段边界的完整记忆快照（公开/私有记忆 + 药剂 + 存活）。"""
        return {
            "round_no": self.round_no,
            "stage": stage,  # after_night / after_day
            "witch_antidote": self.witch_antidote,
            "witch_poison": self.witch_poison,
            "night_deaths": getattr(self, "_night_deaths", []),
            "players": {n: {"alive": p.alive, "public_log": p.public_log,
                            "private_notes": p.private_notes}
                        for n, p in self.players.items()},
        }

    def set_state(self, state: dict) -> None:
        self.round_no = state["round_no"]
        self.witch_antidote = state["witch_antidote"]
        self.witch_poison = state["witch_poison"]
        self._night_deaths = list(state.get("night_deaths", []))
        for n, s in state["players"].items():
            p = self.players[n]
            p.alive = s["alive"]
            p.public_log = list(s["public_log"])
            p.private_notes = list(s["private_notes"])

    def _save_checkpoint(self, stage: str) -> None:
        if self.checkpoint_path:
            import json as _json
            from pathlib import Path as _Path
            _Path(self.checkpoint_path).write_text(
                _json.dumps(self.get_state(stage), ensure_ascii=False),
                encoding="utf-8")

    # ---------- 初始化 ----------
    def _build_players(self) -> None:
        names = [p["name"] for p in self.config["players"]]
        wolves = [p["name"] for p in self.config["players"] if p["role"] == "werewolf"]
        speech_max = self.config.get("game", {}).get("speech_max_chars", 200)
        default_model = self.config.get("llm", {}).get("default_model", "gpt-4o-mini")
        for p in self.config["players"]:
            role = p["role"]
            mates = [w for w in wolves if w != p["name"]] if role == "werewolf" else []
            agent_cls = PlayerAgent
            extra = {}
            if p.get("human"):
                if self.human_agent_cls is not None:
                    agent_cls = self.human_agent_cls
                    extra = self.human_kwargs
                else:
                    from .human import HumanAgent  # 延迟导入，纯 AI 局无感
                    agent_cls = HumanAgent
            agent = agent_cls(
                name=p["name"], role=role,
                model=p.get("model") or default_model,
                all_players=names, mates=mates,
                client=self.client, speech_max_chars=speech_max, rng=self.rng,
                **extra,
            )
            self.players[p["name"]] = agent
        self.logger.event(
            "game_start",
            players=[{"name": p.name, "role": p.role, "model": p.model}
                     for p in self.players.values()],
            config=self.config,
        )
        # 有人类玩家时不能打印座位身份，否则剧透
        has_human = any(p.get("human") for p in self.config["players"])
        if has_human:
            self.logger.print("===== 游戏开始（人机混合局，身份已单独告知玩家）=====")
        else:
            seat = "；".join(f"{p.name}（{ROLE_NAMES[p.role]}）"
                             for p in self.players.values())
            self.logger.print(f"===== 游戏开始 | 座位（仅上帝可见）：{seat} =====")

    # ---------- 工具 ----------
    def alive(self) -> list[PlayerAgent]:
        return [p for p in self.players.values() if p.alive]

    def alive_names(self) -> list[str]:
        return [p.name for p in self.alive()]

    def broadcast(self, line: str) -> None:
        for p in self.alive():
            p.hear(line)

    def check_winner(self) -> Optional[str]:
        alive = self.alive()
        wolves = [p for p in alive if p.role == "werewolf"]
        gods = [p for p in alive if p.role in GOD_ROLES]
        civilians = [p for p in alive if p.role in CIVILIAN_ROLES]
        if not wolves:
            return "village"
        if not gods or not civilians:
            return "werewolf"
        return None

    def _finish(self, winner: str, reason: str) -> str:
        self.winner = winner
        label = "好人阵营（村民）" if winner == "village" else "狼人阵营"
        summary = {p.name: {"role": p.role, "alive": p.alive} for p in self.players.values()}
        self.logger.event("game_end", winner=winner, reason=reason, players=summary,
                          rounds=self.round_no)
        self.logger.print(f"\n===== 游戏结束：{label}获胜（{reason}）=====")
        reveal = "；".join(f"{n}={ROLE_NAMES[s['role']]}{'存活' if s['alive'] else '出局'}"
                           for n, s in summary.items())
        self.logger.print(f"身份揭晓：{reveal}")
        return winner

    # ---------- 夜晚 ----------
    async def night_phase(self) -> None:
        self.round_no += 1
        r = self.round_no
        self.logger.print(f"\n----- 第 {r} 轮 · 夜晚 -----")
        self.logger.event("phase", round=r, phase="night_start")
        deaths: list[str] = []

        async def seer_turn() -> None:
            """预言家验人（与狼人行动无依赖，并行执行）。"""
            seer = next((p for p in self.alive() if p.role == "seer"), None)
            if seer:
                candidates = [n for n in self.alive_names() if n != seer.name]
                if candidates:
                    checked = await seer.seer_check(candidates, r)
                    is_wolf = self.players[checked].role == "werewolf"
                    result = "狼人" if is_wolf else "好人"
                    seer.note(f"第{r}轮夜晚：你查验了 {checked}，他是【{result}】。")
                    self.logger.event("night_seer", round=r, seer=seer.name,
                                      checked=checked, result=result,
                                      visibility="seer_only")

        seer_task = asyncio.create_task(seer_turn())

        # 1. 狼人协商 + 刀人
        wolves = [p for p in self.alive() if p.role == "werewolf"]
        targets = [p.name for p in self.alive() if p.role != "werewolf"]
        killed: Optional[str] = None
        if wolves and targets:
            channel: list[str] = []
            for _ in range(self.wolf_discuss_rounds):
                for w in wolves:
                    msg = await w.werewolf_discuss(channel, targets, r)
                    line = f"{w.name}: {msg}"
                    channel.append(line)
                    self.logger.event("werewolf_channel", round=r, speaker=w.name,
                                      message=msg, visibility="werewolf_only")
            # 讨论结束后刀人投票并行（讨论有依赖保持串行）
            votes = await asyncio.gather(
                *[w.werewolf_kill_vote(channel, targets, r) for w in wolves])
            tally = Counter(votes)
            top = tally.most_common()
            best = top[0][1]
            tied = [t for t, c in top if c == best]
            killed = self.rng.choice(tied)
            self.logger.event("night_kill", round=r, votes=votes, target=killed,
                              visibility="god")
            for w in wolves:
                w.note(f"第{r}轮夜晚：你们决定刀 {killed}。")

        # 2. 等待并行的预言家验人完成
        await seer_task

        # 3. 女巫用药
        witch = next((p for p in self.alive() if p.role == "witch"), None)
        poisoned: Optional[str] = None
        saved = False
        if witch and (self.witch_antidote or self.witch_poison):
            others = [n for n in self.alive_names() if n != witch.name]
            action = await witch.witch_action(
                killed=killed, has_antidote=self.witch_antidote,
                has_poison=self.witch_poison,
                can_self_save=(r == 1), alive_others=others, round_no=r,
            )
            if action["save"] and killed:
                saved = True
                self.witch_antidote = False
            if action["poison"]:
                poisoned = action["poison"]
                self.witch_poison = False
            witch.note(
                f"第{r}轮夜晚：被刀的是 {killed}；"
                f"你{'使用了解药' if saved else '未用解药'}，"
                f"{'毒了 ' + poisoned if poisoned else '未用毒药'}。"
            )
            self.logger.event("night_witch", round=r, witch=witch.name, saved=saved,
                              poisoned=poisoned, visibility="witch_only")

        # 4. 结算死亡（猎人被刀可开枪，被毒不能开枪）
        if killed and not saved:
            deaths.append(killed)
        if poisoned:
            deaths.append(poisoned)
        for name in deaths:
            self.players[name].alive = False
        for name in list(deaths):  # 猎人开枪可能追加死亡
            p = self.players[name]
            if p.role == "hunter" and name != poisoned:
                shot = await self._hunter_shot(p, r, "被狼人刀死")
                if shot:
                    deaths.append(shot)
        self._night_deaths = deaths
        self.logger.event("night_result", round=r, deaths=deaths, visibility="god")

    async def _hunter_shot(self, hunter: PlayerAgent, r: int, cause: str) -> Optional[str]:
        """猎人开枪，返回被带走的人（未开枪返回 None）。"""
        candidates = [n for n in self.alive_names() if n != hunter.name]
        shot = await hunter.hunter_shot(candidates, r, cause)
        if shot:
            self.players[shot].alive = False
            self.logger.event("hunter_shot", round=r, hunter=hunter.name,
                              cause=cause, shot=shot, visibility="god")
        else:
            self.logger.event("hunter_shot", round=r, hunter=hunter.name,
                              cause=cause, shot=None, visibility="god")
        return shot

    # ---------- 白天 ----------
    async def day_phase(self) -> None:
        r = self.round_no
        self.logger.print(f"\n----- 第 {r} 轮 · 白天 -----")
        self.logger.event("phase", round=r, phase="day_start")

        # 1. 公布死讯
        deaths = getattr(self, "_night_deaths", [])
        if deaths:
            announce = f"第{r}轮夜晚，{('、'.join(deaths))} 死亡。"
        else:
            announce = f"第{r}轮夜晚是平安夜，无人死亡。"
        self.broadcast(announce)
        self.logger.print(f"[公告] {announce}")
        self.logger.event("day_announce", round=r, deaths=deaths)
        if self.check_winner():
            return

        # 2. 轮流发言
        for p in self.alive():
            speech = await p.speak(r)
            line = f"第{r}轮白天发言 {p.name}: {speech}"
            self.broadcast(line)
            self.logger.print(f"[发言] {p.name}: {speech}")
            self.logger.event("day_speech", round=r, speaker=p.name, speech=speech)

        # 3. 投票放逐（同时秘密投票，并行加速；发言有依赖保持串行）
        names = self.alive_names()
        cast = await asyncio.gather(*[p.vote(names, r) for p in self.alive()])
        votes: dict[str, Optional[str]] = {}
        for p, vote in zip(self.alive(), cast):
            votes[p.name] = vote
            vline = f"第{r}轮投票 {p.name} → {vote or '弃权'}"
            self.broadcast(vline)
            self.logger.print(f"[投票] {p.name} → {vote or '弃权'}")
        tally = Counter(v for v in votes.values() if v)
        exiled: Optional[str] = None
        if tally:
            top = tally.most_common()
            best = top[0][1]
            tied = [t for t, c in top if c == best]
            if len(tied) == 1:
                exiled = tied[0]
        self.logger.event("day_vote", round=r, votes=votes,
                          tally=dict(tally), exiled=exiled)
        if exiled:
            self.players[exiled].alive = False
            line = f"投票结果：{exiled} 被放逐出局。"
            ex_p = self.players[exiled]
            if ex_p.role == "hunter":  # 被放逐的猎人可以开枪
                shot = await self._hunter_shot(ex_p, r, "被投票放逐")
                if shot:
                    line += f"猎人 {exiled} 开枪带走了 {shot}。"
                else:
                    line += f"猎人 {exiled} 放弃开枪。"
        else:
            line = "投票结果：平票，本轮无人被放逐。"
        self.broadcast(line)
        self.logger.print(f"[公告] {line}")

    # ---------- 主循环 ----------
    async def run(self, resume_stage: Optional[str] = None) -> str:
        # 断点续跑：从 after_night 恢复时先补当天白天阶段
        if resume_stage == "after_night":
            winner = self.check_winner()
            if winner:
                return self._finish(winner, "夜晚结算后达成屠边/屠狼条件")
            await self.day_phase()
            self._save_checkpoint("after_day")
            winner = self.check_winner()
            if winner:
                return self._finish(winner, "白天放逐后达成屠边/屠狼条件")
        while self.round_no < self.max_rounds:
            await self.night_phase()
            self._save_checkpoint("after_night")
            winner = self.check_winner()
            if winner:
                return self._finish(winner, "夜晚结算后达成屠边/屠狼条件")
            await self.day_phase()
            self._save_checkpoint("after_day")
            winner = self.check_winner()
            if winner:
                return self._finish(winner, "白天放逐后达成屠边/屠狼条件")
        # 达到最大轮数，按存活人数裁定
        wolves = sum(1 for p in self.alive() if p.role == "werewolf")
        others = len(self.alive()) - wolves
        winner = "werewolf" if wolves >= others else "village"
        return self._finish(winner, f"达到最大轮数 {self.max_rounds}，按存活人数裁定")
