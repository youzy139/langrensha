"""三组实验对比：6人局全flash / 6人局pro狼 / 8人平衡局pro狼。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

setup_plot()

GROUPS = [
    ("6人局\n全 flash", json.loads(Path("logs/stats.json").read_text(encoding="utf-8"))),
    ("6人局\npro 狼", json.loads(Path("logs_pro_wolves/stats.json").read_text(encoding="utf-8"))),
    ("8人平衡局\npro 狼", json.loads(Path("logs_8p/stats.json").read_text(encoding="utf-8"))),
]
names = [g[0] for g in GROUPS]
wolf = [g[1]["camp_wins"].get("werewolf", 0) for g in GROUPS]
village = [g[1]["camp_wins"].get("village", 0) for g in GROUPS]
survival = [g[1]["wolf_survival_rate"] for g in GROUPS]
rounds = [g[1]["avg_rounds"] for g in GROUPS]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 5))

# 左图：堆叠胜负
bottom = [0] * len(GROUPS)
for camp, vals, color in [("狼人", wolf, "#f7768e"), ("好人", village, "#9ece6a")]:
    ax1.bar(names, vals, bottom=bottom, label=camp, color=color, width=0.55)
    for i, v in enumerate(vals):
        if v:
            ax1.text(i, bottom[i] + v / 2, f"{camp} {v}", ha="center",
                     va="center", fontsize=10, fontweight="bold")
        bottom[i] += v
ax1.set_ylabel("胜场（每组 10 局）")
ax1.set_title("阵营胜负对比")
ax1.legend(loc="upper left")

# 右图：狼人胜率 + 存活率 + 平均轮数
x = range(len(GROUPS))
wolf_rate = [w / 10 for w in wolf]
bars1 = ax2.bar([i - 0.2 for i in x], wolf_rate, width=0.38,
                color="#f7768e", label="狼人胜率")
bars2 = ax2.bar([i + 0.2 for i in x], survival, width=0.38,
                color="#e0af68", label="狼人存活率")
for bars in (bars1, bars2):
    ax2.bar_label(bars, labels=[f"{v:.0%}" for v in bars.datavalues], fontsize=10)
for i, r in enumerate(rounds):
    ax2.text(i, -0.16, f"平均 {r} 轮", ha="center", fontsize=9, color="gray")
ax2.set_xticks(list(x))
ax2.set_xticklabels(names)
ax2.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax2.set_yticklabels([f"{t:.0%}" for t in ax2.get_yticks()])
ax2.set_ylim(0, 1.0)
ax2.set_title("狼人方关键指标")
ax2.legend()

fig.suptitle("三组实验对比：模型能力与配置平衡如何影响狼人胜率（狼=pro，其余=flash，各 10 局）",
             fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig("experiment_compare_3groups.png", dpi=200, bbox_inches="tight")
print("saved experiment_compare_3groups.png")
