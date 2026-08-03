# 🐺 多 Agent 狼人杀 · 人机对战平台

> 和 5-7 个 AI 同桌玩一局真正的狼人杀。
> 它们会焊跳预言家、自刀骗药、倒钩卖队友、赛后还会跟你复盘甩锅——
> 底层是一套严格信息隔离的多智能体博弈引擎，支持多模型混编与批量实验。

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20SDK%20%E5%85%BC%E5%AE%B9-orange)
![Async](https://img.shields.io/badge/async-asyncio-green)
![Web](https://img.shields.io/badge/Web-FastAPI%20%2B%20WebSocket-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

<!-- 截图位：在 docs/images/ 下补两张图后取消注释即可
![Web 对局界面](docs/images/web_game.png)
![终局复盘与赛后讨论](docs/images/web_review.png)
-->

## 🎮 玩法：你亲自下场

浏览器打开即玩，不用任何客户端：

- **选局型**：6 人局（2 狼 + 预/女 + 2 民）或 8 人局（3 狼 + 预/女/猎 + 2 民）
- **选身份**：随机，或指定当狼人 / 预言家 / 女巫 / 猎人 / 平民
- **真实对局体验**：
  - 当狼：狼人私密频道和 AI 队友实时商量刀谁、谁焊跳，可以**自刀骗解药**
  - 当神：夜里验人 / 救人毒人 / 临死开枪，白天听 AI 发言抓漏洞
  - 当民：在 AI 的焊跳和对跳里分辨真假预言家
- **全程沉浸设计**：每个 AI 行动前显示"💭 Alice 正在组织发言"动效、右侧栏实时标记出局玩家、关键信息（跳身份/查杀/票型）自动**加粗**
- **终局不散场**：身份揭晓 + AI 解说员复盘（逐轮点评、每人高光/失误/评分）+ **赛后讨论区**——直接向全场 AI 提问，它们会亮出身份、交出自己掌握的私密信息和当时的推理来回应你
- **历史对局**：每一局自动存档，随时回看完整对话与复盘

## 🚀 快速开始

```bash
pip install -r requirements.txt

# 配置 LLM（OpenAI 兼容接口；也可写入项目根目录 .env）
# Windows
set LLM_BASE_URL=https://api.deepseek.com/v1
set LLM_API_KEY=sk-xxx
# Linux/macOS
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_API_KEY=sk-xxx

# 人机对战（推荐）
cd webapp && python server.py --port 7100   # 打开 http://localhost:7100/

# 终端模式
python main.py --human                # 你随机替换一个 AI 上场
python main.py --human Carol          # 指定座位（身份游戏中揭晓）

# 纯 AI 局（观战/实验）
python main.py --replay --review      # 跑一局 + HTML 回放 + AI 解说复盘
WEREWOLF_MOCK=1 python main.py        # Mock 离线测试（无需 API Key）
```

## 🧠 这些 AI 玩家为什么"像人"

AI 不是各自为战的答题机器，而是一套有纪律的博弈系统：

- **严格信息隔离**：GameMaster（上帝）是唯一全知者；每个 PlayerAgent 的私有记忆（身份/验人/夜间行动/狼人频道）与公开记忆物理分离，AI 只能基于"发给自己的信息"行动——伪装和推理都建立在真实的信息不对称上
- **夜间战术 → 白天执行**：狼人频道的协商记录会写入每只狼的私密记忆，夜里说"明天我跳预言家"，白天就必须跳——战术一致性由记忆架构保证
- **角色化策略 prompt**：平民会焊跳挡刀、预言家掌握起跳时机、女巫管理银水毒药、狼人分冲锋/倒钩打法，还有严格的保密纪律（自刀后绝不认领银水）
- **结构化输出 + 多层兜底**：所有决策走 JSON schema（失败带反馈重试），空回复自动加大 token 预算，发言还有免格式兜底通道——**50+ 局真实对局无一局中断**

## 📊 实验：多模型混编对抗（5 组 × 10 局真实对局）

引擎支持每个玩家配置不同模型，于是可以做"能力不对称"实验：

**能力矩阵 · 8 人平衡局（3 狼 + 预/女/猎 + 2 民）狼人胜率：**

| 狼 \ 好人 | flash 好人 | pro 好人 |
|---|---|---|
| **flash 狼** | 60%（6:4） | 70%（7:3） |
| **pro 狼** | 70%（7:3） | 未跑 |

![能力矩阵](docs/images/experiment_matrix.png)

关键发现（详见 [实验报告](docs/EXPERIMENT_REPORT.md)）：

1. **配置效应（±40pp）远大于模型效应（±10-20pp）**：6 人局好人碾压、8 人 3 狼局狼人占优
2. **反直觉：强模型当好人反而压不住狼**——pro 好人抓狼更准（狼存活率降至 30%），但狼队只需把好人犯错"武器化"即可取胜
3. 强模型当狼提升真实：pro 狼存活率 47%，显著高于 flash 狼的 30-37%

批量实验（支持断点续跑，可反复调用直到跑满）：

```bash
python run_experiment.py --config config_pro_wolves_8p.yaml \
    --logdir logs_8p --total 10 --budget 240
```

## 🏗 架构

```
                    ┌─────────────────────────────┐
                    │        GameMaster（上帝）     │
                    │  唯一全知 · 状态机驱动        │
                    │  夜晚→白天→胜负判定           │
                    └───────┬───────────┬─────────┘
                   公开广播  │           │  私密投递
              ┌─────────────┘           └─────────────┐
        ┌─────▼─────┐  ┌─────────┐  ┌─────────┐  ┌───▼─────┐
        │ PlayerAgent│  │PlayerAgent│ │PlayerAgent│ │ 🤖/🧑   │
        │ 狼人 A(pro)│  │ 狼人 B(pro)│ │预言家(flash)│ │ 你(人类) │
        └─────┬─────┘  └────┬────┘  └─────────┘  └─────────┘
              └──────┬──────┘
              狼人私密频道（仅狼人可见）
                     │
        每个 Agent = 角色 System Prompt + 私有记忆 + 公开记忆
        所有决策 = JSON 结构化输出（解析失败带反馈自动重试）
                     │
              全量事件 → game_log.jsonl（含每次调用完整 prompt / 回复 / reasoning）
                     │
        ┌────────────┼────────────┬──────────────┐
        ▼            ▼            ▼              ▼
   Web 人机对局   AI 解说员复盘   批量实验统计   胜率可视化
```

## 项目结构

```
├── main.py                    # 入口：单局/多局 + 回放 + 复盘 + --human 人机局
├── run_experiment.py          # 批量实验：断点续跑 + 胜率统计
├── config.yaml                # 玩家/角色/模型/规则 全配置驱动
├── werewolf/
│   ├── gamemaster.py          # 上帝：状态机 + checkpoint 断点续跑
│   ├── player.py              # PlayerAgent：双层记忆 + 结构化决策
│   ├── roles.py               # 角色 System Prompt（狼/预/女/猎/民）
│   ├── llm.py                 # 异步 LLM 客户端：超时/重试/JSON 解析
│   ├── logger.py              # JSONL 结构化日志 + 控制台输出
│   ├── review.py              # AI 解说员复盘
│   └── replay.py              # HTML 回放页生成
├── webapp/                    # Web 人机对局：FastAPI + WebSocket
│   ├── server.py              # 对局服务器：角色洗牌/思考动效/赛后讨论/历史存档
│   └── index.html             # 单页前端：大厅/对局/终局结算/复盘/讨论区
├── docs/EXPERIMENT_REPORT.md  # 完整实验报告
├── docs/PROJECT_GUIDE.md      # 代码精读指南（学习向）
└── logs*/                     # 各实验组对局日志与统计
```

## 路线图

- [x] 6 人局（2 狼 + 预/女 + 2 民）
- [x] 8 人局 + 猎人
- [x] Web 人机对局（指定身份 / 狼人频道 / 思考动效 / 历史回看 / 赛后讨论）
- [x] 狼人自刀等进阶战术规则
- [x] 多模型混编与批量实验
- [x] AI 解说复盘 / HTML 回放
- [ ] 更大规模样本（50-100 局/组）收窄置信区间
- [ ] Elo 评分体系：模型间循环赛排名
- [ ] 更多角色（守卫/白痴/骑士）与 12 人标准局

## License

MIT
