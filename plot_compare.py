"""对比两组实验：全 flash（基准）vs pro狼+flash好人（能力不对称）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

setup_plot()

base = json.loads(Path("logs/stats.json").read_text(encoding="utf-8"))
pro = json.loads(Path("logs_pro_wolves/stats.json").read_text(encoding="utf-8"))

groups = ["全 flash（基准）", "pro 狼 vs flash 好人"]
wolf_wins = [base["camp_wins"].get("werewolf", 0), pro["camp_wins"].get("werewolf", 0)]
village_wins = [base["camp_wins"].get("village", 0), pro["camp_wins"].get("village", 0)]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.8))

# 左图：两组实验狼人胜率对比（堆叠条形）
df = pd.DataFrame({
    "实验组": groups * 2,
    "胜场": wolf_wins + village_wins,
    "阵营": ["狼人"] * 2 + ["好人"] * 2,
})
bottom = [0, 0]
for camp, color in [("狼人", "#f7768e"), ("好人", "#9ece6a")]:
    vals = [df[(df["实验组"] == g) & (df["阵营"] == camp)]["胜场"].iloc[0] for g in groups]
    ax1.bar(groups, vals, bottom=bottom, label=camp, color=color, width=0.5)
    for i, v in enumerate(vals):
        if v:
            ax1.text(i, bottom[i] + v / 2, f"{camp}\n{v} 局", ha="center",
                     va="center", fontsize=10, fontweight="bold")
        bottom[i] += v
ax1.set_ylabel("胜场（共 10 局 / 组）")
ax1.set_title("阵营胜负对比")
ax1.legend()

# 右图：狼人方指标对比
metrics = pd.DataFrame({
    "指标": ["狼人胜率", "狼人胜率", "狼人存活率", "狼人存活率"],
    "实验组": groups * 2,
    "数值": [base["camp_wins"].get("werewolf", 0) / base["completed"],
             pro["camp_wins"].get("werewolf", 0) / pro["completed"],
             base["wolf_survival_rate"], pro["wolf_survival_rate"]],
})
sns.barplot(data=metrics, x="指标", y="数值", hue="实验组", ax=ax2,
            palette=["#7aa2f7", "#e0af68"])
for c in ax2.containers:
    ax2.bar_label(c, labels=[f"{v:.0%}" for v in c.datavalues], fontsize=10)
ax2.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax2.set_yticklabels([f"{t:.0%}" for t in ax2.get_yticks()])
ax2.set_ylim(0, 1.0)
ax2.set_title("狼人方关键指标")
ax2.legend(fontsize=9, loc="upper right")

fig.suptitle("能力不对称实验：强模型当狼能否翻盘？（狼：deepseek-v4-pro，好人：deepseek-v4-flash）",
             fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig("experiment_compare.png", dpi=200, bbox_inches="tight")
print("saved experiment_compare.png")
