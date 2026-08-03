"""异步 LLM 客户端：OpenAI 兼容接口 + 超时 + 重试 + JSON 结构化解析。

- base_url / api_key 从环境变量读取（变量名可在 config.yaml 中配置）。
- 每个玩家可用不同 model。
- chat_json() 要求模型输出 JSON，解析失败自动带反馈重试；
  全部重试失败返回 None，由调用方做兜底（保证游戏不卡死）。
- 环境变量 WEREWOLF_MOCK=1 时走 Mock 模式（离线测试用）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Awaitable, Callable, Optional

from . import env as _env  # noqa: F401  # 导入即加载项目根目录 .env

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> Optional[dict]:
    """从模型输出中提取第一个 JSON 对象。"""
    if not text:
        return None
    # 优先剥离 markdown 代码围栏
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    for chunk in (candidate, text):
        if not chunk:
            continue
        m = _JSON_BLOCK_RE.search(chunk)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


class LLMClient:
    def __init__(self, config: dict, logger=None):
        llm_cfg = config.get("llm", {})
        self.base_url = os.environ.get(llm_cfg.get("base_url_env", "LLM_BASE_URL"), "")
        self.api_key = os.environ.get(llm_cfg.get("api_key_env", "LLM_API_KEY"), "")
        self.temperature = llm_cfg.get("temperature", 0.8)
        self.max_tokens = llm_cfg.get("max_tokens", 600)
        self.timeout = llm_cfg.get("timeout_seconds", 60)
        self.max_retries = llm_cfg.get("max_retries", 2)
        self.logger = logger
        self.mock = os.environ.get("WEREWOLF_MOCK", "") == "1"
        # 状态回调：fn(player, action, phase, on)，用于前端"正在思考"提示
        self.on_status: Optional[Callable[[str, str, str, bool], None]] = None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # 延迟导入，Mock 模式无需依赖

            # 重试由 chat_json 自己控制，关闭 SDK 内部重试避免双重退避
            self._client = AsyncOpenAI(base_url=self.base_url or None,
                                       api_key=self.api_key or "EMPTY",
                                       max_retries=0, timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        """显式关闭底层 httpx 连接池，避免事件循环关闭后的 GC 告警。"""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None

    async def chat(self, model: str, messages: list[dict],
                   max_tokens: Optional[int] = None) -> tuple[str, str]:
        """返回 (content, reasoning)。reasoning 模型可能把预算耗在思考上，
        导致 content 为空——调用方据此重试。"""
        client = self._get_client()
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            ),
            timeout=self.timeout,
        )
        msg = resp.choices[0].message
        return msg.content or "", getattr(msg, "reasoning_content", None) or ""

    async def chat_json(
        self,
        *,
        player: str,
        action: str,
        model: str,
        messages: list[dict],
        required_keys: list[str],
        mock_fn: Optional[Callable[[], Awaitable[dict]]] = None,
        round_no: int = 0,
        phase: str = "",
    ) -> tuple[Optional[dict], str]:
        """请求一次结构化输出。返回 (解析后的 dict 或 None, 原始文本)。

        Mock 模式直接调用 mock_fn()。真实模式解析失败自动重试，
        重试时把错误反馈追加进 messages，让模型自我修正。
        """
        self._emit_status(player, action, phase, True)
        try:
            return await self._chat_json_inner(
                player=player, action=action, model=model, messages=messages,
                required_keys=required_keys, mock_fn=mock_fn,
                round_no=round_no, phase=phase,
            )
        finally:
            self._emit_status(player, action, phase, False)

    def _emit_status(self, player: str, action: str, phase: str, on: bool) -> None:
        cb = self.on_status
        if cb:
            try:
                cb(player, action, phase, on)
            except Exception:
                pass

    async def _chat_json_inner(
        self,
        *,
        player: str,
        action: str,
        model: str,
        messages: list[dict],
        required_keys: list[str],
        mock_fn: Optional[Callable[[], Awaitable[dict]]] = None,
        round_no: int = 0,
        phase: str = "",
    ) -> tuple[Optional[dict], str]:
        if self.mock:
            data = await mock_fn() if mock_fn else {}
            raw = json.dumps(data, ensure_ascii=False)
            self._log_call(player, action, model, messages, raw, data, True, round_no, phase)
            return data, raw

        msgs = [dict(m) for m in messages]
        last_raw = ""
        last_reasoning = ""
        for attempt in range(self.max_retries + 1):
            try:
                # 空 content 多半是 reasoning 模型把预算耗在思考上：重试时加大 max_tokens
                grow = self.max_tokens * 2 if (attempt > 0 and not last_raw) else None
                last_raw, last_reasoning = await self.chat(model, msgs, max_tokens=grow)
            except Exception as e:  # 超时 / 网络 / API 错误
                self._log_call(player, action, model, msgs, f"ERROR: {e!r}", None,
                               False, round_no, phase, attempt)
                continue
            data = extract_json(last_raw)
            if data is not None and all(k in data for k in required_keys):
                self._log_call(player, action, model, msgs, last_raw, data,
                               True, round_no, phase, attempt,
                               reasoning=last_reasoning)
                return data, last_raw
            # 解析失败：把反馈追加进对话，让模型修正格式
            # 空 content 多半是 reasoning 模型把 token 预算耗在了思考上
            hint = ("你的回复格式不正确。"
                    if last_raw else
                    "你的回复为空（可能是思考过长导致正文被截断）。请直接、简短地")
            msgs.append({"role": "assistant", "content": last_raw or "（空回复）"})
            msgs.append({
                "role": "user",
                "content": (
                    f"{hint}只输出一个合法的 JSON 对象，"
                    f"必须包含字段：{required_keys}，不要输出任何其他文字。"
                ),
            })
            self._log_call(player, action, model, msgs, last_raw, data,
                           False, round_no, phase, attempt, reasoning=last_reasoning)
        return None, last_raw

    def _log_call(self, player, action, model, messages, raw, parsed,
                  success, round_no, phase, attempt=0, reasoning=""):
        if self.logger:
            self.logger.event(
                "llm_call",
                round=round_no, phase=phase, player=player, action=action,
                model=model, attempt=attempt, success=success,
                messages=messages, raw_response=raw, parsed=parsed,
                reasoning=reasoning,
            )
