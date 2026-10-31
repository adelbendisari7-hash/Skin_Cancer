"""Prédiction conforme « split » et abstention (renvoi au médecin).

Le jeu de CALIBRATION (lésions jamais vues à l'entraînement ni à la validation) sert à
fixer un seuil q̂ tel que l'ensemble de prédiction contienne la vraie classe avec une
probabilité ≥ 1 − α (garantie sans hypothèse sur le modèle, si calibration et test sont
échangeables) [Vovk 2005 ; Angelopoulos & Bates 2021].

Scores de non-conformité :
- LAC  [Sadinle et al. 2019] : s = 1 − p_y ; ensembles les plus petits en moyenne.
- APS  [Romano et al. 2020]  : masse des classes plus probables que y + u·p_y, u ~ U(0,1)
                               (version randomisée canonique, graine fixe → reproductible).
- LAC conditionnel par classe (« Mondrian ») : un seuil par classe, couverture garantie
  pour CHAQUE classe, en particulier le mélanome.

Règle d'abstention : l'IA ne décide seule que si l'ensemble est un singleton ET qu'il
coïncide avec la décision au coût ; sinon le cas est renvoyé au médecin.
"""
from __future__ import annotations

import numpy as np

from . import config as C


def _quantile(scores: np.ndarray, alpha: float) -> float:
    """Quantile conforme : k-ième plus petit score avec k = ⌈(n+1)(1−α)⌉."""
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return float(np.inf) if k > n else float(np.sort(scores)[k - 1])


def _aps_cum(p: np.ndarray) -> np.ndarray:
    """Pour chaque classe k : somme des probabilités des classes j avec p_j ≥ p_k."""
    order = np.argsort(-p, axis=1)
    cum_sorted = np.cumsum(np.take_along_axis(p, order, axis=1), axis=1)
    cum = np.empty_like(p)
    np.put_along_axis(cum, order, cum_sorted, axis=1)
    return cum


class Conformal:
    def __init__(self, method: str = "lac", alpha: float = C.ALPHA, seed: int = 0):
        assert method in ("lac", "aps", "mondrian")
        self.method, self.alpha, self.seed = method, alpha, seed

    def _scores_all(self, p: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        if self.method == "aps":
            u = rng.random((len(p), 1))
            return _aps_cum(p) - p + u * p        # masse strictement au-dessus + u·p_k
        return 1.0 - p

    def fit(self, p_cal: np.ndarray, y_cal: np.ndarray) -> "Conformal":
        rng = np.random.default_rng(self.seed)
        s = self._scores_all(p_cal, rng)[np.arange(len(y_cal)), y_cal]
        if self.method == "mondrian":
            self.q = np.array([_quantile(s[y_cal == k], self.alpha) for k in range(C.N_CLASSES)])
        else:
            self.q = _quantile(s, self.alpha)
        return self

    def sets(self, p: np.ndarray) -> np.ndarray:
        """Matrice booléenne (n, classes) : la classe k est-elle dans l'ensemble ?"""
        s = self._scores_all(p, np.random.default_rng(self.seed + 1))
        q = self.q[None, :] if self.method == "mondrian" else self.q
        return s <= q


def abstain_rule(sets: np.ndarray, pred_cost: np.ndarray) -> np.ndarray:
    """True = cas traité automatiquement ; False = renvoyé au médecin."""
    single = sets.sum(1) == 1
    return single & sets[np.arange(len(pred_cost)), pred_cost]


def set_stats(sets: np.ndarray, y: np.ndarray) -> dict:
    cover = sets[np.arange(len(y)), y]
    out = {"couverture": float(cover.mean()), "taille moyenne": float(sets.sum(1).mean()),
           "singletons": float((sets.sum(1) == 1).mean()), "vides": float((sets.sum(1) == 0).mean())}
    mel = y == C.MEL
    out["couverture mel"] = float(cover[mel].mean()) if mel.any() else np.nan
    return out
