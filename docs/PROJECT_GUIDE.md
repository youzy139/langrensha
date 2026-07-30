# 项目精读指南：把多智能体狼人杀吃透

> 这份文档的目标：读完之后你能从零复述整个系统的设计，讲清每个决策的
> "为什么"，并且能动手扩展。建议对照代码边读边跑（`WEREWOLF_MOCK=1 python main.py`
> 可以离线跑，随时打断点看变量）。

---

## 1. 推荐阅读顺序

```
config.yaml → main.py → werewolf/gamemaster.py（骨架）
           → werewolf/player.py（核心）
           → werewolf/llm.py（可靠性）
           → werewolf/roles.py（prompt）
           → logger.py / review.py / replay.py（外围）
           → run_experiment.py（实验方法论）
```

先跑一局 Mock 模式看控制台输出，把"夜晚→白天"的节奏建立起来，再读代码。

---

## 2. 一局游戏的数据流（先建立全局图景）

```
main.py
  └─ asyncio.run(run_game(config, ...))
       └─ GameMaster.run()                      # 状态机主循环
            ├─ night_phase()                    # 每个夜晚
            │    ├─ 狼人: werewolf_discuss()    # 私密频道，串行（有依赖）
            │    ├─ 狼人: werewolf_kill_vote()  # 并行（讨论已结束）
            │    ├─ 预言家: seer_check()        # 与狼人行动并行（无依赖）
            │    └─ 女巫: witch_action()        # 必须等刀人结果，最后
            │    → 结算死亡（猎人被刀可开枪，被毒不能）
            │    → checkpoint("after_night")
            ├─ check_winner()                   # 屠边判定
            ├─ day_phase()                      # 每个白天
            │    ├─ 广播死讯（所有存活玩家 hear()）
            │    ├─ 轮流发言 speak()            # 串行（后面的人能听到前面的）
            │    └─ 投票 vote()                 # 并行（同时秘密投票）
            │    → 放逐（平票则无人出局；猎被放逐可开枪）
            │    → checkpoint("after_day")
            └─ check_winner()
```

每个决策点都是一次 `LLMClient.chat_json()` 调用，产生一条 `llm_call` 日志。
**抓住这条主线，所有代码都是围绕它展开的。**

---

## 3. 逐模块精读

### 3.1 `werewolf/llm.py` — 可靠性核心（约 150 行，最值得细读）

这个文件解决一个问题：**怎么让不稳定的 LLM 输出变成程序可用的结构化数据**。

**`extract_json()`**：模型经常不乖乖只输出 JSON（会加解释、加 markdown 围栏）。
策略是三层兜底：先找 ```json 围栏 → 再找全文第一个 `{...}` → `json.loads` 失败就放弃。
不要试图"修"坏 JSON，直接重试更可靠。

**`chat_json()` 的重试设计**（重点）：

```python
for attempt in range(self.max_retries + 1):
    last_raw, last_reasoning = await self.chat(model, msgs)
    data = extract_json(last_raw)
    if data 合法: return data
    msgs.append(assistant: 错误回复)   # ← 关键：把错误回复塞回对话
    msgs.append(user: "格式不正确，请只输出 JSON...")  # ← 让模型自我修正
```

为什么不直接重发同样的 prompt？因为 temperature > 0 时重发可能得到同样格式的错误；
**把错误展示给模型并明确指出来，修正成功率显著更高**。这是处理 LLM 结构化输出的
通用模式（self-correction loop）。

**为什么 `max_retries=0` 关掉 SDK 内部重试？**
OpenAI SDK 默认自己重试 2 次（带指数退避）。如果两层重试都开着，一次失败 =
外层 3 次 × 内层 3 次 = 9 次请求 + 双重退避等待。重试策略只能有一层 owner。

**reasoning 模型的坑**：deepseek-v4-flash 是推理模型，思考会消耗 `max_tokens`
预算。预算不够时 `content` 返回空字符串（不是报错！），`extract_json` 拿到空串失败。
这就是为什么 `chat()` 返回 `(content, reasoning)` 二元组，以及为什么 config 里
`max_tokens: 1500` 而不是直觉上的 400。**教训：推理模型的输出预算 = 思考 + 正文。**

### 3.2 `werewolf/player.py` — Agent 抽象（核心设计点）

**双层记忆是这个项目最重要的设计**：

```python
self.public_log: list[str]      # hear() 写入：上帝广播，所有玩家一样的内容
self.private_notes: list[str]   # note() 写入：只有自己可见
self.system_prompt              # 角色 + 目标 + 策略
```

每次决策时 `_context_messages()` 把三者拼成 prompt。注意**信息隔离不是靠
模型自觉，而是靠架构**：公共频道里根本没有私密信息，模型想泄露也拿不到。
这是多智能体系统安全设计的范本——"不可得的信息不可能泄露"。

**每个决策方法（speak/vote/seer_check/witch_action/hunter_shot）都是同一个模式**：

1. 拼 instruction（当前任务 + 合法选项列表）
2. `chat_json(required_keys=[...])` 拿结构化结果
3. `_resolve_choice()` 把模型输出**模糊匹配**到合法候选人
   （模型可能输出 "Alice（她可疑）" 这种带解释的，直接 `==` 会匹配失败）
4. 全部失败 → 随机合法值兜底，**游戏永不停摆**

读 `witch_action()` 时注意：约束（同晚限一瓶药、首夜后才能自救）是在
**代码层强制执行**的，不是只靠 prompt 告诉模型。"prompt 是建议，代码是法律"。

### 3.3 `werewolf/gamemaster.py` — 状态机与上帝视角

**为什么 GameMaster 是唯一全知者？** 如果让玩家 Agent 自己驱动游戏，
真相会散落在各处，无法裁决。集中式上帝 = 单一事实来源（single source of truth）。

**并行化的依赖分析**（面试高频考点）：哪些能并行，完全由数据依赖决定——

| 环节 | 串行/并行 | 原因 |
|---|---|---|
| 狼人讨论 | 串行 | 后面的狼要看前面的频道消息 |
| 狼人刀人投票 | 并行 | 讨论已结束，互相独立 |
| 预言家验人 | 与狼人并行 | 不依赖刀人结果 |
| 女巫行动 | 串行最后 | **依赖**刀人结果 |
| 白天发言 | 串行 | 后面的人要听前面的发言 |
| 白天投票 | 并行 | 同时秘密投票（还顺带更符合真实规则） |

**屠边判定 `check_winner()`**：狼全灭 → 好人胜；神职全灭 **或** 平民全灭 → 狼胜。
每个死亡事件后都要检查（夜晚结算后、白天放逐后、猎人开枪后——开枪走
`_hunter_shot()` 统一入口，所以回到主循环的检查点自然覆盖）。

**checkpoint 设计**：

- 快照内容：轮次、阶段标记、女巫药剂、**每个玩家的完整双层记忆**、当夜死讯
- 只在阶段边界保存（`after_night` / `after_day`），不支持阶段内恢复
- 恢复时 `set_state()` 重建记忆，`run(resume_stage="after_night")` 从白天补跑
- 当夜死讯（`_night_deaths`）必须进快照——这是踩过的坑：白天公告要广播
  死讯，快照漏了它，恢复后会错报"平安夜"

### 3.4 `werewolf/roles.py` — Prompt 工程

注意三个层次：

1. **共同规则**（`_BASE`）：所有角色共享，改一处全局生效
2. **角色目标 + 策略指引**：不只是"你是狼人"，而是给出策略（"被查杀可以反跳"），
   否则模型会打得很保守（实验里 flash 狼被查杀后普遍"装死"，复盘被解说员狂喷）
3. **纪律约束**："只能基于发给你的信息行动"——防止模型编造不存在的信息
   （LLM 很爱幻觉"我记得某人说过..."）

### 3.5 外围三件套

- **`logger.py`**：JSONL 每行一个事件，`visibility` 字段标记可见范围
  （`werewolf_only` / `seer_only` / `god`）——回放页靠它做视角过滤
- **`replay.py`**：纯函数（JSONL → HTML），无状态。LLM 调用默认折叠，
  因为完整 prompt 很长
- **`review.py`**：解说员的输入不是原始日志，而是 `build_digest()` 提炼的
  紧凑战报（reasoning 每条截 300 字）。**长上下文任务先蒸馏再喂模型**，
  既省钱又防止重点被淹没

### 3.6 `run_experiment.py` — 实验方法论

三个设计值得学：

1. **断点续跑**：`is_complete()` 检查日志里有没有 `game_end`，可反复调用
   直到跑满——长实验被中断是常态，不是意外
2. **数据质检**：逐局统计 LLM 调用失败率，100% 失败的局是"随机兜底局"，
   不能算模型能力——**剔除并重跑**（实际发生过 2 局）
3. **独立 logdir + seed-base**：每组实验完全隔离，结果可复现

---

## 4. 踩坑记录（每个都是真实发生的）

| 坑 | 现象 | 解法 | 通用教训 |
|---|---|---|---|
| SDK 双重重试 | 断网时一局要 7 分钟 | `max_retries=0` 关掉 SDK 重试 | 重试只能有一层 owner |
| reasoning 模型空回复 | 26/59 次解析失败 | max_tokens 提到 1500 + 记录 reasoning | 推理模型预算 = 思考 + 正文 |
| checkpoint 漏死讯 | 恢复后错报"平安夜" | `_night_deaths` 进快照 | 快照清单要覆盖"恢复后第一个动作"的输入 |
| 续跑日志截断 | 恢复后丢掉前段日志 | logger 加 `mode="a"`，先判续跑再开文件 | "先打开再判断"是危险顺序 |
| API 全面故障 | 2 局 100% 随机兜底 | 失败率质检 + 剔除重跑 | 实验数据必须做有效性质检 |
| 单次命令时限 300s | 长对局跑不完 | 断点续跑分批推进 | 把长任务设计成可断点续跑 |

---

## 5. 自测题（能答上来就是真懂了）

1. 为什么信息隔离要在架构层做，而不是在 prompt 里写"不要泄露身份"？
2. `chat_json` 重试时为什么要把错误回复 append 进 messages，而不是重发原 prompt？
3. 女巫行动为什么不能和狼人刀人并行？预言家验人为什么可以？
4. 如果要在阶段**内部**（比如白天发言到一半）支持断点恢复，快照需要加什么？
   （提示：发言是串行的，恢复点之后的发言不能重复广播）
5. 为什么 `_resolve_choice` 需要模糊匹配？给出一个会失败的例子。
6. "pro 好人抓狼更准（狼存活率更低）却赢不了"的机制是什么？（答案在
   `logs_8p_pro_village/game_2.review.md`）
7. 如果让你加"守卫"角色（每晚守护一人免刀），要改哪几个文件？女巫的
   `killed` 结算逻辑要不要动？

---

## 6. 动手练习（按难度排序）

1. **入门**：给 6 人局加"遗言"环节（夜晚死亡玩家白天公告前说一句话）。
   只需改 `gamemaster.py` 的 `day_phase` + `player.py` 加一个方法。
2. **进阶**：实现守卫角色。注意它与女巫解药的交互（同守同救会奶穿——
   标准规则里被守又被救的玩家反而会死，这是一个经典规则坑）。
3. **高级**：给 `run_experiment.py` 加 Elo 评分：任意两个模型配置对打
   若干局，按胜负更新 Elo，输出模型排行榜。
4. **研究向**：修改 `player.py` 让狼人发言时能选择"自爆"（直接结束白天
   进入夜晚），观察 pro 狼会不会学会这个高级战术。

---

## 7. 一句话总结这个项目的精髓

> **用架构保证正确性（信息隔离、代码强约束），用重试和兜底消化 LLM 的
> 不稳定性，用 checkpoint 消化基础设施的不稳定性，用实验质检消化数据的
> 不稳定性。** 这四层防御思想可以平移到任何 LLM 应用。
