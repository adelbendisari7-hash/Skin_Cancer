"""Lance toute la chaîne d'entraînement, en sautant ce qui est déjà fait (reprise possible).

Usage : python -m src.run_all            (≈ 7 min par réseau et par graine sur une RTX 3050)
Chaque entraînement tourne dans un processus séparé pour libérer la mémoire GPU.
"""
from __future__ import annotations

import subprocess
import sys

from . import config as C

NETWORKS = ["M1", "M3", "M5", "M5_sansFiLM", "M5_sansCout", "M5_dropClin"]


def main() -> None:
    subprocess.run([sys.executable, "-m", "src.prepare"], check=True, cwd=C.PROJECT_DIR)
    if not (C.PRED_DIR / "M2_s0.npz").exists():
        subprocess.run([sys.executable, "-m", "src.tabular"], check=True, cwd=C.PROJECT_DIR)
    for exp in NETWORKS:
        for seed in C.TRAIN_SEEDS:
            if (C.PRED_DIR / f"{exp}_s{seed}.npz").exists():
                print(f"déjà fait : {exp} s{seed}")
                continue
            subprocess.run([sys.executable, "-m", "src.train", "--exp", exp, "--seeds", str(seed)],
                           check=True, cwd=C.PROJECT_DIR)
    for step in ["src.results", "src.analyses"]:              # étapes 4 à 10
        subprocess.run([sys.executable, "-m", step], check=True, cwd=C.PROJECT_DIR)


if __name__ == "__main__":
    main()
