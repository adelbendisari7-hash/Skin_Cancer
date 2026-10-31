"""Étape 5 — M2 : modèle clinique seul (âge, sexe, localisation).

XGBoost (modèle retenu) comparé à une forêt aléatoire. Les hyperparamètres ET le nombre
d'arbres sont choisis par validation croisée à 5 plis **sur le train**, groupée par lésion
(StratifiedGroupKFold) et sur la log-loss. Le jeu de validation reste donc intact : il sert
ensuite, sans biais, à choisir le poids de la fusion tardive M4 (étape 6).
Les valeurs SHAP viennent de TreeSHAP intégré à XGBoost, sur exactement le modèle évalué.

Usage : python -m src.tabular
"""
from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, log_loss
from sklearn.model_selection import StratifiedGroupKFold

from . import config as C
from .data import ClinicalEncoder, get_split

LABELS = list(range(C.N_CLASSES))


def _data():
    df = get_split()
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    X, y = enc.transform(df), df.y.to_numpy().copy()
    groups = df.lesion_id.to_numpy()
    idx = {s: np.flatnonzero(df.split.to_numpy() == s) for s in ["train", "val", "calib", "test"]}
    return df, enc, X, y, groups, idx


def _xgb(seed, max_depth, min_child_weight, n_estimators, early_stopping=None):
    return xgb.XGBClassifier(
        objective="multi:softprob", num_class=C.N_CLASSES, n_estimators=n_estimators,
        learning_rate=0.03, max_depth=max_depth, min_child_weight=min_child_weight,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, tree_method="hist",
        eval_metric="mlogloss", early_stopping_rounds=early_stopping, random_state=seed, n_jobs=8)


def _rf(seed, min_samples_leaf):
    return RandomForestClassifier(n_estimators=500, min_samples_leaf=min_samples_leaf, random_state=seed, n_jobs=8)


def tune(seed: int = 0) -> tuple[dict, pd.DataFrame]:
    """Grille évaluée par validation croisée groupée (5 plis) à l'intérieur du train."""
    df, enc, X, y, groups, idx = _data()
    tr = idx["train"]
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed).split(X[tr], y[tr], groups[tr]))
    rows = []
    for md, mcw in itertools.product([2, 3, 4, 6], [1, 5, 20]):
        losses, f1s, iters = [], [], []
        for a, b in folds:
            m = _xgb(seed, md, mcw, 2000, early_stopping=100)
            m.fit(X[tr[a]], y[tr[a]], eval_set=[(X[tr[b]], y[tr[b]])], verbose=False)
            p = m.predict_proba(X[tr[b]])
            losses.append(log_loss(y[tr[b]], p, labels=LABELS))
            f1s.append(f1_score(y[tr[b]], p.argmax(1), average="macro", labels=LABELS, zero_division=0))
            iters.append(m.best_iteration + 1)
        rows.append({"modèle": "XGBoost", "params": json.dumps({"max_depth": md, "min_child_weight": mcw,
                                                                "n_estimators": int(np.median(iters))}),
                     "log-loss CV": np.mean(losses), "F1 macro CV": np.mean(f1s)})
    for leaf in [1, 5, 20, 50]:
        losses, f1s = [], []
        for a, b in folds:
            p = _rf(seed, leaf).fit(X[tr[a]], y[tr[a]]).predict_proba(X[tr[b]])
            losses.append(log_loss(y[tr[b]], p, labels=LABELS))
            f1s.append(f1_score(y[tr[b]], p.argmax(1), average="macro", labels=LABELS, zero_division=0))
        rows.append({"modèle": "Forêt aléatoire", "params": json.dumps({"min_samples_leaf": leaf}),
                     "log-loss CV": np.mean(losses), "F1 macro CV": np.mean(f1s)})
    grid = pd.DataFrame(rows).sort_values("log-loss CV")
    best = grid.iloc[0]
    return {"modèle": best["modèle"], **json.loads(best["params"])}, grid


def run() -> None:
    best, grid = tune(seed=0)
    grid.round(4).to_csv(C.TAB_DIR / "05_M2_grille_validation_croisee.csv", index=False)
    print(grid.round(4).to_string(index=False))
    print("Retenu :", best)
    df, enc, X, y, groups, idx = _data()
    eval_idx = np.concatenate([idx["val"], idx["calib"], idx["test"]])
    tr = idx["train"]
    for seed in C.TRAIN_SEEDS:
        if best["modèle"] == "XGBoost":
            m = _xgb(seed, best["max_depth"], best["min_child_weight"], best["n_estimators"]).fit(X[tr], y[tr])
            # SHAP (TreeSHAP exact) sur le test, avec exactement les arbres du modèle évalué
            contrib = m.get_booster().predict(xgb.DMatrix(X[idx["test"]]), pred_contribs=True)
            np.save(C.PRED_DIR / f"M2_s{seed}_shap_test.npy", contrib)
        else:
            m = _rf(seed, best["min_samples_leaf"]).fit(X[tr], y[tr])
        np.savez_compressed(C.PRED_DIR / f"M2_s{seed}.npz", idx=eval_idx, p=m.predict_proba(X[eval_idx]))
        p_val = m.predict_proba(X[idx["val"]])
        meta = {"exp": "M2", "seed": seed, **best, "features": enc.feature_names,
                "log-loss val": float(log_loss(y[idx["val"]], p_val, labels=LABELS)),
                "F1 macro val": float(f1_score(y[idx["val"]], p_val.argmax(1), average="macro", labels=LABELS,
                                               zero_division=0))}
        (C.PRED_DIR / f"M2_s{seed}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"M2 s{seed}: log-loss val = {meta['log-loss val']:.4f}, F1 macro val = {meta['F1 macro val']:.4f}")
    # Importances de la forêt aléatoire (comparaison avec SHAP, étape 9)
    rf = _rf(0, 20).fit(X[tr], y[tr])
    pd.Series(rf.feature_importances_, index=enc.feature_names).sort_values(ascending=False).round(4) \
        .to_csv(C.TAB_DIR / "05_M2_importances_RF.csv", header=["importance (impureté)"])


if __name__ == "__main__":
    run()
