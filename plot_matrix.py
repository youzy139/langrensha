"""能力矩阵总图：8 人平衡局 狼模型 × 好人模型 → 狼人胜率。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

import matplotlib.pyplot as plt
import numpy as np

setup_plot()

# 矩阵：行=狼模型，列=好人模型；值为狼人胜率（各 10 局）
matrix = [
    [0.60, 0.70],   # flash 狼
    [0.70, None],   # pro 狼（pro/pro 未跑）
]
rows = ["flash 狼", "pro 狼"]
cols = ["flash 好人", "pro 好人"]
notes = [["狼 6:4", "狼 7:3"], ["狼 7:3", "未跑\n（省钱）"]]
survival = [["存活 37%", "存活 30%"], ["存活 47%", ""]]

fig, ax = plt.subplots(figsize=(7.5, 5.2))
vals = np.array([[0.60, 0.70], [0.70, np.nan]])
im = ax.imshow(vals, cmap="RdYlGn_r", vmin=0.2, vmax=0.8, aspect="auto")

for i in range(2):
    for j in range(2):
        if matrix[i][j] is None:
            ax.text(j, i, notes[i][j], ha="center", va="center",
                    fontsize=12, color="gray")
        else:
            ax.text(j, i - 0.12, f"{matrix[i][j]:.0%}", ha="center",
                    va="center", fontsize=22, fontweight="bold", color="white")
            ax.text(j, i + 0.18, f"{notes[i][j]} · {survival[i][j]}",
                    ha="center", va="center", fontsize=10, color="white")

ax.set_xticks([0, 1], cols, fontsize=12)
ax.set_yticks([0, 1], rows, fontsize=12)
ax.set_title("能力矩阵：8 人平衡局狼人胜率（各 10 局）\n"
             "颜色越红狼人越强，越绿好人越强", fontsize=12, fontweight="bold")
cbar = fig.colorbar(im, ax=ax, shrink=0.8)
cbar.set_label("狼人胜率")
fig.tight_layout()
fig.savefig("experiment_matrix.png", dpi=200, bbox_inches="tight")
print("saved experiment_matrix.png")
