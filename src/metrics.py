"""Mesures de performance et intervalles de confiance par bootstrap au niveau lésion.

L'exactitude seule est trompeuse (67 % de nævus) : on rapporte surtout le F1 macro,
l'exactitude équilibrée, l'AUC un-contre-tous, la sensibilité/spécificité mélanome et le
coût attendu sous la matrice de coût clinique.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score

from . import config as C


def cost_matrix(ratio: float = C.DEFAULT_COST_RATIO) -> np.ndarray:
    """Matrice de coût M[vrai, prédit].

    Correct = 0 ; toute erreur = 1 (dont la fausse alerte mélanome) ;
    mélanome manqué (vrai mel, prédit autre chose) = `ratio`.
    """
    m = 1.0 - np.eye(C.N_CLASSES)
    m[C.MEL, :] = ratio
    m[C.MEL, C.MEL] = 0.0
    return m


def expected_cost(y: np.ndarray, pred: np.ndarray, ratio: float = C.DEFAULT_COST_RATIO) -> float:
    """Coût moyen par cas."""
    return float(cost_matrix(ratio)[y, pred].mean())


def mel_sens_spec(y: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    """Sensibilité et spécificité du diagnostic « mélanome » contre tout le reste."""
    pos, alarm = y == C.MEL, pred == C.MEL
    sens = float(alarm[pos].mean()) if pos.any() else np.nan
    spec = float((~alarm[~pos]).mean()) if (~pos).any() else np.nan
    return sens, spec


def fast_metrics(y: np.ndarray, pred: np.ndarray, ratio: float = C.DEFAULT_COST_RATIO) -> dict:
    """Métriques à seuil depuis la matrice de confusion (rapide : utilisée aussi dans le bootstrap).

    F1 macro sur les classes présentes (vraies ou prédites), comme sklearn par défaut : sur un
    sous-ensemble (cas traités après abstention), une classe absente ne compte pas comme un zéro.
    """
    k = C.N_CLASSES
    cm = np.bincount(y * k + pred, minlength=k * k).reshape(k, k).astype(float)
    tp, support, predicted = np.diag(cm), cm.sum(1), cm.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rec = np.where(support > 0, tp / support, np.nan)
        prec = np.where(predicted > 0, tp / predicted, 0.0)
        f1 = np.where(prec + np.nan_to_num(rec) > 0, 2 * prec * rec / (prec + rec), 0.0)
    present = support > 0
    seen = present | (predicted > 0)
    neg = cm.sum() - support[C.MEL]
    return {
        "F1 macro": float(f1[seen].mean()),
        "Exactitude équilibrée": float(np.nanmean(rec[present])),
        "Sensibilité mel": float(rec[C.MEL]),
        "Spécificité mel": float((neg - (predicted[C.MEL] - tp[C.MEL])) / neg) if neg else np.nan,
        "Coût attendu": float((cm * cost_matrix(ratio)).sum() / cm.sum()),
    }


def classification_metrics(y: np.ndarray, pred: np.ndarray, prob: np.ndarray | None = None,
                           ratio: float = C.DEFAULT_COST_RATIO) -> dict:
    out = fast_metrics(y, pred, ratio)
    out["Exactitude"] = float(accuracy_score(y, pred))
    if prob is not None:
        out["AUC OvR macro"] = float(roc_auc_score(y, prob, multi_class="ovr", average="macro",
                                                   labels=list(range(C.N_CLASSES))))
        out["AUC mel"] = float(roc_auc_score(y == C.MEL, prob[:, C.MEL]))
    return out


def confusion(y: np.ndarray, pred: np.ndarray, normalize: str | None = None) -> np.ndarray:
    return confusion_matrix(y, pred, labels=list(range(C.N_CLASSES)), normalize=normalize)


# --------------------------------------------------------------------------
# Bootstrap par lésion
# --------------------------------------------------------------------------
def lesion_bootstrap_indices(lesion_ids: np.ndarray, n_boot: int = C.N_BOOTSTRAP,
                             seed: int = 0) -> list[np.ndarray]:
    """Rééchantillonne les LÉSIONS (avec remise) et renvoie les indices d'images associés.

    Les images d'une même lésion sont corrélées : rééchantillonner les images
    séparément sous-estimerait la variance. Les IC sont calculés dans evaluate.bootstrap_compare.
    """
    rng = np.random.default_rng(seed)
    uniq, inv = np.unique(lesion_ids, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        out.append(np.concatenate([members[k] for k in pick]))
    return out
