"""Règles de décision réglées sur la VALIDATION (jamais sur le test).

- `late_fusion_weight` : poids w de M4 = w·p(image) + (1−w)·p(clinique).
- `tune_mel_threshold` : seuil t sur p(mélanome) minimisant le coût attendu, pour un
  rapport de coût R (mélanome manqué = R fois une fausse alerte).
- `decide`             : « mélanome » si p(mel) ≥ t, sinon la classe non-mélanome la plus probable.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score

from . import config as C
from .metrics import expected_cost

T_GRID = np.round(np.arange(0.01, 0.991, 0.01), 2)
W_GRID = np.round(np.arange(0.0, 1.001, 0.05), 2)


def decide(p: np.ndarray, t: float) -> np.ndarray:
    others = p.copy()
    others[:, C.MEL] = -1.0
    pred = others.argmax(1)
    pred[p[:, C.MEL] >= t] = C.MEL
    return pred


def tune_mel_threshold(p_val: np.ndarray, y_val: np.ndarray,
                       ratio: float = C.DEFAULT_COST_RATIO) -> tuple[float, np.ndarray]:
    """Seuil de coût minimal sur la validation (à égalité : le plus haut, donc le moins d'alertes)."""
    costs = np.array([expected_cost(y_val, decide(p_val, t), ratio) for t in T_GRID])
    best = np.flatnonzero(costs <= costs.min() + 1e-12).max()
    return float(T_GRID[best]), costs


def late_fusion_weight(p_img_val: np.ndarray, p_clin_val: np.ndarray, y_val: np.ndarray) -> tuple[float, np.ndarray]:
    """Poids de l'image dans la moyenne pondérée, choisi par F1 macro de validation."""
    labels = list(range(C.N_CLASSES))
    scores = np.array([f1_score(y_val, (w * p_img_val + (1 - w) * p_clin_val).argmax(1),
                                average="macro", labels=labels, zero_division=0) for w in W_GRID])
    best = np.flatnonzero(scores >= scores.max() - 1e-12).max()   # à égalité : plus de poids à l'image
    return float(W_GRID[best]), scores
