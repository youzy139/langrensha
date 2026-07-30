"""读取 logs/stats.json，绘制狼人杀实验胜率统计图。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

setup_plot()

stats = json.loads(Path("logs/stats.json").read_text(encoding="utf-8"))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

# 左图：阵营胜负场次
camp = pd.DataFrame({
    "阵营": ["好人阵营", "狼人阵营"],
    "胜场": [stats["camp_wins"].get("village", 0),
             stats["camp_wins"].get("werewolf", 0)],
})
sns.barplot(data=camp, x="阵营", y="胜场", ax=ax1,
            palette=["#9ece6a", "#f7768e"])
for i, v in enumerate(camp["胜场"]):
    ax1.text(i, v + 0.1, str(v), ha="center", fontweight="bold")
ax1.set_title(f"阵营胜负（共 {stats['completed']} 局 · 平均 {stats['avg_rounds']} 轮）")
ax1.set_ylim(0, max(camp["胜场"]) + 1.5)

# 右图：分角色胜率
role_names = {"werewolf": "狼人", "seer": "预言家", "witch": "女巫", "villager": "平民"}
rs = stats["role_stats"]
roles = pd.DataFrame({
    "角色": [role_names.get(r, r) for r in rs],
    "胜率": [rs[r]["win_rate"] for r in rs],
    "场次": [rs[r]["games"] for r in rs],
})
colors = ["#f7768e" if r == "werewolf" else "#7aa2f7" for r in rs]
sns.barplot(data=roles, x="角色", y="胜率", ax=ax2, palette=colors)
for i, row in roles.iterrows():
    ax2.text(i, row["胜率"] + 0.02, f"{row['胜率']:.0%}\n({row['场次']}场)",
             ha="center", fontsize=9)
ax2.axhline(0.5, ls="--", color="gray", lw=1)
ax2.set_title(f"分角色胜率（狼人平均存活率 {stats['wolf_survival_rate']:.0%}）")
ax2.set_ylim(0, 1.15)
ax2.set_yticklabels([f"{t:.0%}" for t in ax2.get_yticks()])

fig.suptitle("多 Agent 狼人杀实验 · 10 局真实对局（deepseek-v4-flash）",
             fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig("experiment_stats.png", dpi=200, bbox_inches="tight")
print("saved experiment_stats.png")
