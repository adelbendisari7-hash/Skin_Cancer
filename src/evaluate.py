"""Étapes 6 à 8 — assembler les prédictions, appliquer les règles de décision, comparer.

Pour chaque modèle et chaque graine :
  1. probabilités sur validation / calibration / test ;
  2. décision « classique » (classe la plus probable) et décision « au coût »
     (seuil mélanome réglé sur la validation pour R = 5, 10, 20) ;
  3. abstention conforme réglée sur la calibration ;
  4. métriques sur le test, puis moyenne ± écart-type sur les 3 graines ;
  5. IC 95 % par bootstrap apparié au niveau lésion pour les comparaisons clés.

Les tableaux et figures sont produits par src.results (étapes 4 à 8).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from . import config as C
from .conformal import Conformal, abstain_rule, set_stats
from .decision import decide, late_fusion_weight, tune_mel_threshold
from .metrics import classification_metrics, fast_metrics, lesion_bootstrap_indices

# Nom affiché → identifiant d'expérience (M4 est construit à partir de M1 et M2)
MODELS = {
    "M1 image": "M1",
    "M2 clinique": "M2",
    "M3 concaténation": "M3",
    "M4 fusion tardive": "M4",
    "M5 FiLM + coût (proposé)": "M5",
    "M5 sans FiLM (concat + coût)": "M5_sansFiLM",
    "M5 sans coût (FiLM + CE)": "M5_sansCout",
    "M5 + dropout clinique (bonus)": "M5_dropClin",
}
SPLITS = ["val", "calib", "test"]


# --------------------------------------------------------------------------
# Chargement des prédictions
# --------------------------------------------------------------------------
def _load(exp: str, seed: int, df: pd.DataFrame) -> dict | None:
    f = C.PRED_DIR / f"{exp}_s{seed}.npz"
    if not f.exists():
        return None
    d = np.load(f)
    split = df.split.to_numpy()[d["idx"]]
    out = {}
    for s in SPLITS:
        m = split == s
        out[f"p_{s}"] = d["p"][m]
        out[f"idx_{s}"] = d["idx"][m]
        if "p_noclin" in d.files:
            out[f"p_noclin_{s}"] = d["p_noclin"][m]
    return out


def load_runs(df: pd.DataFrame) -> dict[tuple[str, int], dict]:
    """Toutes les prédictions disponibles, M4 compris (poids choisi sur la validation)."""
    runs = {}
    for exp in set(MODELS.values()) - {"M4"}:
        for seed in C.TRAIN_SEEDS:
            r = _load(exp, seed, df)
            if r is not None:
                runs[(exp, seed)] = r
    y = df.y.to_numpy()
    for seed in C.TRAIN_SEEDS:
        if ("M1", seed) in runs and ("M2", seed) in runs:
            a, b = runs[("M1", seed)], runs[("M2", seed)]
            assert all((a[f"idx_{s}"] == b[f"idx_{s}"]).all() for s in SPLITS)
            w, curve = late_fusion_weight(a["p_val"], b["p_val"], y[a["idx_val"]])
            m4 = {f"idx_{s}": a[f"idx_{s}"] for s in SPLITS}
            m4.update({f"p_{s}": w * a[f"p_{s}"] + (1 - w) * b[f"p_{s}"] for s in SPLITS})
            m4["w"], m4["w_curve"] = w, curve
            runs[("M4", seed)] = m4
    return runs


# --------------------------------------------------------------------------
# Évaluation d'un run
# --------------------------------------------------------------------------
def evaluate_run(r: dict, y: np.ndarray, ratios=C.COST_RATIOS, alpha: float = C.ALPHA,
                 conformal: str = "lac", noclin: bool = False) -> dict:
    """Décisions et métriques test d'un run. `noclin` : utiliser les prédictions sans contexte."""
    key = "p_noclin_" if noclin else "p_"
    yv, yc, yt = (y[r[f"idx_{s}"]] for s in SPLITS)
    pv, pc, pt = (r[f"{key}{s}"] for s in SPLITS)
    out = {"classique": {"pred": pt.argmax(1)}}
    for R in ratios:
        t, _ = tune_mel_threshold(pv, yv, R)
        out[f"coût R={R}"] = {"pred": decide(pt, t), "seuil": t}
    # Abstention : ensemble conforme (calibration) + décision au coût R par défaut
    cf = Conformal(conformal, alpha).fit(pc, yc)
    sets = cf.sets(pt)
    pred_cost = out[f"coût R={C.DEFAULT_COST_RATIO}"]["pred"]
    treated = abstain_rule(sets, pred_cost)
    out["abstention"] = {"pred": pred_cost, "traité": treated, "sets": sets, "q": cf.q}
    out["p_test"], out["y_test"] = pt, yt
    return out


def metrics_table(runs: dict, df: pd.DataFrame, noclin: bool = False) -> pd.DataFrame:
    """Une ligne par (modèle, graine, décision) avec toutes les métriques test."""
    y = df.y.to_numpy()
    rows = []
    for name, exp in MODELS.items():
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs or (noclin and "p_noclin_test" not in runs[(exp, seed)]):
                continue
            ev = evaluate_run(runs[(exp, seed)], y, noclin=noclin)
            pt, yt = ev["p_test"], ev["y_test"]
            for dec in ["classique", f"coût R={C.DEFAULT_COST_RATIO}"]:
                m = classification_metrics(yt, ev[dec]["pred"], pt)
                rows.append({"modèle": name, "graine": seed, "décision": dec, **m,
                             "seuil mel": ev[dec].get("seuil", np.nan)})
            # Avec abstention : métriques sur les cas traités + sécurité globale
            a = ev["abstention"]
            tr = a["traité"]
            m = classification_metrics(yt[tr], a["pred"][tr], None)
            mel = yt == C.MEL
            rows.append({"modèle": name, "graine": seed, "décision": "coût + abstention", **m,
                         "Taux traité": float(tr.mean()),
                         "Mélanomes manqués en silence": int((mel & tr & (a["pred"] != C.MEL)).sum()),
                         "Mélanomes au test": int(mel.sum()),
                         **{f"conformal {k}": v for k, v in set_stats(a["sets"], yt).items()}})
    return pd.DataFrame(rows)


def summarize(tab: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Moyenne ± écart-type sur les graines."""
    g = tab.groupby(["modèle", "décision"], sort=False)[cols]
    mean, std = g.mean(), g.std(ddof=1)
    out = mean.copy().astype(object)
    for c in cols:
        out[c] = [f"{m:.3f} ± {s:.3f}" if np.isfinite(s) else f"{m:.3f}" for m, s in zip(mean[c], std[c])]
    out["n graines"] = g.size()
    return out.reset_index()


# --------------------------------------------------------------------------
# Bootstrap apparié (moyenne sur les graines dans chaque rééchantillon)
# --------------------------------------------------------------------------
def auc_mel(y: np.ndarray, p_mel: np.ndarray) -> float:
    """AUC mélanome-contre-reste par les rangs (Mann-Whitney), indépendante de tout seuil."""
    pos = y == C.MEL
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    r = rankdata(p_mel)
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def bootstrap_compare(runs: dict, df: pd.DataFrame, pairs: list[tuple], n_boot: int = C.N_BOOTSTRAP,
                      metrics=("F1 macro", "Exactitude équilibrée", "Sensibilité mel", "Coût attendu",
                               "AUC mel")) -> pd.DataFrame:
    y = df.y.to_numpy()
    lesion = df.lesion_id.to_numpy()
    cache = {}

    def preds(exp, dec):
        if (exp, dec) not in cache:
            lst = []
            for seed in C.TRAIN_SEEDS:
                if (exp, seed) in runs:
                    ev = evaluate_run(runs[(exp, seed)], y, ratios=[C.DEFAULT_COST_RATIO])
                    lst.append((ev[dec]["pred"], ev["p_test"][:, C.MEL]))
            cache[(exp, dec)] = lst
        return cache[(exp, dec)]

    any_run = next(iter(runs.values()))
    idx_test = any_run["idx_test"]
    yt = y[idx_test]
    boots = lesion_bootstrap_indices(lesion[idx_test], n_boot, seed=123)
    rows = []
    for (ea, da), (eb, db) in pairs:
        pa, pb = preds(ea, da), preds(eb, db)
        if not pa or not pb:
            continue

        def avg(plist, ix):
            ms = [{**fast_metrics(yt[ix], p[ix]), "AUC mel": auc_mel(yt[ix], pm[ix])} for p, pm in plist]
            return {k: np.mean([m[k] for m in ms]) for k in metrics}

        full_a, full_b = avg(pa, np.arange(len(yt))), avg(pb, np.arange(len(yt)))
        diffs = {k: [] for k in metrics}
        for ix in boots:
            ma, mb = avg(pa, ix), avg(pb, ix)
            for k in metrics:
                diffs[k].append(ma[k] - mb[k])
        for k in metrics:
            d = np.array(diffs[k])
            lo, hi = np.percentile(d, [2.5, 97.5])
            better = d < 0 if k == "Coût attendu" else d > 0
            rows.append({"comparaison": f"{ea} [{da}] − {eb} [{db}]", "métrique": k,
                         "A": round(full_a[k], 4), "B": round(full_b[k], 4),
                         "différence": round(full_a[k] - full_b[k], 4),
                         "IC95 %": f"[{lo:+.3f} ; {hi:+.3f}]",
                         "significatif": bool(lo > 0 or hi < 0), "P(A meilleur)": round(float(better.mean()), 3)})
    return pd.DataFrame(rows)
