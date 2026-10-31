"""Étapes 9 et 10 — interprétation, robustesse et sous-groupes.

Usage : python -m src.analyses
Produit les figures 09_* et 10_* et les tableaux associés dans resultats/.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import torch

from . import config as C
from . import viz
from .conformal import Conformal, abstain_rule, set_stats
from .decision import decide, tune_mel_threshold
from .evaluate import MODELS, evaluate_run, load_runs
from .metrics import fast_metrics
from .interpret import context, counterfactual_pmel, film_by_value, gradcam, load_model
from .viz import plt

SEED = 0   # graine utilisée pour les figures qualitatives


# --------------------------------------------------------------------------
# Choix de la méthode conforme sur la VALIDATION (le test n'intervient pas)
# --------------------------------------------------------------------------
def conformal_choice_on_val(runs: dict, df: pd.DataFrame, exp: str = "M5") -> pd.DataFrame:
    """Calibration sur `calib`, mesure sur `val` : couverture globale et couverture mélanome."""
    y = df.y.to_numpy()
    rows = []
    for seed in C.TRAIN_SEEDS:
        if (exp, seed) not in runs:
            continue
        r = runs[(exp, seed)]
        yv, yc = y[r["idx_val"]], y[r["idx_calib"]]
        t, _ = tune_mel_threshold(r["p_val"], yv, C.DEFAULT_COST_RATIO)
        pred = decide(r["p_val"], t)
        for method in ["lac", "aps", "mondrian"]:
            sets = Conformal(method).fit(r["p_calib"], yc).sets(r["p_val"])
            tr = abstain_rule(sets, pred)
            st = set_stats(sets, yv)
            rows.append({"graine": seed, "méthode": method, **st, "taux traité": tr.mean(),
                         "mel manqués en silence (val)": int(((yv == C.MEL) & tr & (pred != C.MEL)).sum())})
    out = pd.DataFrame(rows).groupby("méthode").mean(numeric_only=True).drop(columns="graine")
    out.round(3).to_csv(C.TAB_DIR / "08_choix_conforme_validation.csv")
    return out


def abstention_table(runs: dict, df: pd.DataFrame, method: str, write: bool = True) -> pd.DataFrame:
    """Abstention sur le test avec la méthode retenue : couverture, taux traité, sécurité mélanome."""
    y = df.y.to_numpy()
    rows = []
    for name, exp in MODELS.items():
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            ev = evaluate_run(runs[(exp, seed)], y, conformal=method)
            yt, a = ev["y_test"], ev["abstention"]
            tr, pred = a["traité"], a["pred"]
            mel = yt == C.MEL
            m_all = fast_metrics(yt, pred)
            m_tr = fast_metrics(yt[tr], pred[tr])
            m_cls = fast_metrics(yt, ev["classique"]["pred"])
            st = set_stats(a["sets"], yt)
            rows.append({
                "modèle": name, "graine": seed, "couverture conforme": st["couverture"],
                "couverture conforme mel": st["couverture mel"], "taille moyenne ensemble": st["taille moyenne"],
                "taux traité": tr.mean(), "taux d'abstention": 1 - tr.mean(),
                "F1 macro (traités)": m_tr["F1 macro"], "Exactitude (traités)": float((pred[tr] == yt[tr]).mean()),
                "Sensibilité mel (traités)": m_tr["Sensibilité mel"],
                "Sensibilité mel (tous, sans abstention)": m_all["Sensibilité mel"],
                "Sensibilité mel (tous, argmax)": m_cls["Sensibilité mel"],
                "mélanomes renvoyés au médecin": int((mel & ~tr).sum()),
                "mélanomes manqués en silence": int((mel & tr & (pred != C.MEL)).sum()),
                "mélanomes manqués (argmax, sans abstention)": int((mel & (ev["classique"]["pred"] != C.MEL)).sum()),
                "mélanomes au test": int(mel.sum()),
            })
    tab = pd.DataFrame(rows)
    if write:
        tab.to_csv(C.TAB_DIR / "08_abstention_par_graine.csv", index=False)
        g = tab.drop(columns="graine").groupby("modèle", sort=False)
        summ = g.mean().round(3).astype(str) + " ± " + g.std(ddof=1).round(3).astype(str)
        summ.to_csv(C.TAB_DIR / "08_abstention_resume.csv")
    return tab


MALIGNANT = [C.CLASSES.index(c) for c in ("mel", "bcc", "akiec")]


def triage_table(runs: dict, df: pd.DataFrame, method: str) -> pd.DataFrame:
    """Lecture clinique « malin vs bénin » : mel, bcc et akiec doivent tous être vus par un médecin.

    Un cas est « renvoyé » s'il est prédit malin, ou (avec abstention) si l'IA s'abstient.
    Une fausse alerte mélanome sur un bcc/akiec n'est donc pas une erreur de triage.
    """
    y = df.y.to_numpy()
    rows = []
    for exp in ["M1", "M3", "M4", "M5"]:
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            ev = evaluate_run(runs[(exp, seed)], y, ratios=[C.DEFAULT_COST_RATIO], conformal=method)
            yt = ev["y_test"]
            malin = np.isin(yt, MALIGNANT)
            a = ev["abstention"]
            for dec, referred in [("classique", np.isin(ev["classique"]["pred"], MALIGNANT)),
                                  (R := f"coût R={C.DEFAULT_COST_RATIO}", np.isin(ev[R]["pred"], MALIGNANT)),
                                  ("coût + abstention", np.isin(a["pred"], MALIGNANT) | ~a["traité"])]:
                rows.append({"modèle": exp, "graine": seed, "décision": dec,
                             "sensibilité malin": float(referred[malin].mean()),
                             "spécificité bénin": float((~referred[~malin]).mean()),
                             "malins non renvoyés": int((malin & ~referred).sum()),
                             "part des cas renvoyés": float(referred.mean()), "malins au test": int(malin.sum())})
    tab = pd.DataFrame(rows)
    summ = tab.groupby(["modèle", "décision"], sort=False).mean(numeric_only=True).drop(columns="graine")
    summ.round(3).to_csv(C.TAB_DIR / "08_triage_malin_benin.csv")
    return summ


# --------------------------------------------------------------------------
# Grad-CAM : mélanomes détectés / manqués, fausses alertes
# --------------------------------------------------------------------------
def gradcam_figure(runs: dict, df: pd.DataFrame, enc, clin, bank) -> None:
    y = df.y.to_numpy()
    r5, r1 = runs[("M5", SEED)], runs[("M1", SEED)]
    idx = r5["idx_test"]
    yt = y[idx]
    t5, _ = tune_mel_threshold(r5["p_val"], y[r5["idx_val"]], C.DEFAULT_COST_RATIO)
    pred5 = decide(r5["p_test"], t5)
    pm5, pm1 = r5["p_test"][:, C.MEL], r1["p_test"][:, C.MEL]
    rng = np.random.default_rng(1)
    groups = [
        ("Mélanome détecté par M5", np.flatnonzero((yt == C.MEL) & (pred5 == C.MEL) & (pm1 < 0.5)), 2),
        ("Mélanome détecté par M5", np.flatnonzero((yt == C.MEL) & (pred5 == C.MEL) & (pm1 >= 0.5)), 1),
        ("Mélanome manqué par M5", np.flatnonzero((yt == C.MEL) & (pred5 != C.MEL)), 2),
        ("Nævus : fausse alerte M5", np.flatnonzero((yt == 0) & (pred5 == C.MEL)), 2),
    ]
    chosen = []
    for title, cand, k in groups:
        # une image par lésion pour éviter les doublons
        cand = cand[~pd.Series(df.lesion_id.to_numpy()[idx[cand]]).duplicated().to_numpy()]
        for c in rng.choice(cand, min(k, len(cand)), replace=False):
            chosen.append((title, c))
    m1, m5 = load_model("M1", SEED, enc.n_features), load_model("M5", SEED, enc.n_features)
    rows = np.array([idx[c] for _, c in chosen])
    cam1, cam5 = gradcam(m1, bank, clin, rows, C.MEL), gradcam(m5, bank, clin, rows, C.MEL)
    fig, axes = plt.subplots(len(chosen), 3, figsize=(7.2, 2.35 * len(chosen)))
    for i, (title, c) in enumerate(chosen):
        img = bank[idx[c]]
        meta = df.iloc[idx[c]]
        axes[i, 0].imshow(img)
        sexe = {"male": "homme", "female": "femme"}.get(meta.sex, "sexe inconnu")
        axes[i, 0].set_title(f"{title}\n{meta.age:.0f} ans, {sexe}, {meta.localization}", fontsize=8, loc="left")
        for ax, cam, name, pm in [(axes[i, 1], cam1[i], "M1", pm1[c]), (axes[i, 2], cam5[i], "M5", pm5[c])]:
            ax.imshow(img); ax.imshow(cam, cmap="inferno", alpha=0.45)
            ax.set_title(f"Grad-CAM {name} — p(mel) = {pm:.2f}", fontsize=8, loc="left")
        for ax in axes[i]:
            ax.axis("off")
    fig.suptitle("Grad-CAM (classe mélanome) sur des cas du test, graine 0", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.975)); viz.save(fig, "09_gradcam_melanome")


# --------------------------------------------------------------------------
# FiLM : comment le contexte module la lecture de l'image
# --------------------------------------------------------------------------
def film_figures(df: pd.DataFrame, enc, clin, bank) -> pd.DataFrame:
    model = load_model("M5", SEED, enc.n_features)
    f = film_by_value(model, enc, df, stage=max(model.film_stages))
    g, b, loc = f["gamma"], f["beta"], f["loc"]
    strength = pd.DataFrame({"loc": loc, "|γ| moyen": np.abs(g).mean(1), "|β| moyen": np.abs(b).mean(1)})
    by_loc = strength.groupby("loc").agg(**{"n": ("loc", "size"), "|γ| moyen": ("|γ| moyen", "mean"),
                                           "|β| moyen": ("|β| moyen", "mean")}).sort_values("|γ| moyen")
    by_loc.round(4).to_csv(C.TAB_DIR / "09_film_force_par_localisation.csv")

    # Profil moyen de γ par localisation sur les canaux les plus modulés
    gm = pd.DataFrame(g).groupby(loc).mean()
    top = gm.var(axis=0).sort_values(ascending=False).index[:24]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1, 1.7]})
    axes[0].barh([f"{i} (n={n})" for i, n in zip(by_loc.index, by_loc.n)], by_loc["|γ| moyen"],
                 color=viz.BLUE, height=0.6)
    axes[0].set_xlabel("|γ| moyen (intensité de la modulation)")
    axes[0].set_title("Intensité de la modulation FiLM par localisation", loc="left", fontsize=10)
    axes[0].grid(axis="y", visible=False)
    vmax = np.abs(gm[top].to_numpy()).max()
    order = by_loc.index[::-1]
    im = axes[1].imshow(gm.loc[order, top].to_numpy(), cmap=viz.DIVERGING, vmin=-vmax, vmax=vmax, aspect="auto")
    axes[1].set_yticks(range(len(order)), order); axes[1].set_xticks(range(len(top)), top, fontsize=6.5, rotation=90)
    axes[1].set_xlabel("Canal de l'image (24 canaux dont γ varie le plus selon la localisation)")
    axes[1].set_title("γ moyen par localisation (rouge = canal amplifié, bleu = atténué)", loc="left", fontsize=10)
    axes[1].grid(False)
    fig.colorbar(im, ax=axes[1], fraction=0.025, pad=0.01).outline.set_visible(False)
    fig.tight_layout(); viz.save(fig, "09_film_localisation")
    return by_loc


def counterfactual_figure(df: pd.DataFrame, enc, clin, bank) -> pd.DataFrame:
    """Même image, contexte modifié : p(mélanome) moyen selon l'âge et la localisation."""
    test = np.flatnonzero(df.split.to_numpy() == "test")
    mel_idx = test[df.y.to_numpy()[test] == C.MEL]
    nv_idx = test[df.y.to_numpy()[test] == 0]
    ages = list(range(10, 90, 10))
    locs = ["back", "lower extremity", "upper extremity", "trunk", "abdomen", "face", "chest", "foot",
            "neck", "scalp", "hand", "ear"]
    rows = []
    for exp in ["M5", "M3"]:
        model = load_model(exp, SEED, enc.n_features)
        for label, ix in [("vrais mélanomes", mel_idx), ("vrais nævus", nv_idx)]:
            for col, vals in [("age", ages), ("localization", locs)]:
                t = counterfactual_pmel(model, enc, bank, df, ix, col, vals)
                t["modèle"], t["images"], t["variable"] = exp, label, col
                t = t.rename(columns={col: "valeur"})
                rows.append(t)
        del model; torch.cuda.empty_cache()
    tab = pd.concat(rows)
    tab.to_csv(C.TAB_DIR / "09_contrefactuels.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [1, 1.5]})
    for exp, col in [("M5", viz.MAGENTA), ("M3", viz.AQUA)]:
        for lab, ls in [("vrais mélanomes", "-"), ("vrais nævus", "--")]:
            s = tab[(tab.modèle == exp) & (tab.images == lab) & (tab.variable == "age")]
            axes[0].plot(s.valeur.astype(float), s["p(mel) moyen"], ls, color=col, marker="o", ms=4,
                         label=f"{exp} — {lab}")
            s = tab[(tab.modèle == exp) & (tab.images == lab) & (tab.variable == "localization")]
            off = -0.12 if exp == "M5" else 0.12
            axes[1].plot(np.arange(len(locs)) + off, s["p(mel) moyen"], "o", color=col,
                         mfc=col if lab == "vrais mélanomes" else viz.SURFACE, ms=6, mew=1.5,
                         label=f"{exp} — {lab}")
    axes[0].set_xlabel("Âge imposé (le reste du dossier inchangé)"); axes[0].set_ylabel("p(mélanome) moyen")
    axes[0].set_title("Contrefactuel : effet de l'âge", loc="left", fontsize=10); axes[0].legend(fontsize=7.5)
    axes[1].set_xticks(range(len(locs)), locs, rotation=35, ha="right")
    axes[1].set_title("Contrefactuel : effet de la localisation (● mélanomes, ○ nævus)", loc="left", fontsize=10)
    axes[1].grid(axis="x", visible=False)
    fig.suptitle("Même image, contexte patient modifié : comment la décision change (test, graine 0)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); viz.save(fig, "09_contrefactuels")
    return tab


# --------------------------------------------------------------------------
# SHAP du modèle clinique M2
# --------------------------------------------------------------------------
def shap_figure(enc) -> pd.DataFrame:
    contrib = np.load(C.PRED_DIR / f"M2_s{SEED}_shap_test.npy")      # (n, classes, variables + biais)
    names = enc.feature_names
    mean_abs = np.abs(contrib[:, :, :-1]).mean(0)                     # (classes, variables)
    tab = pd.DataFrame(mean_abs.T, index=names, columns=C.CLASSES)
    tab["total"] = tab.sum(1)
    tab = tab.sort_values("total", ascending=False)
    tab.round(4).to_csv(C.TAB_DIR / "09_shap_M2.csv")
    top = tab.head(10)[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    axes[0].barh(top.index, top["total"], color=viz.ORANGE, height=0.6)
    axes[0].set_title("M2 : importance SHAP (|SHAP| moyen, toutes classes)", loc="left", fontsize=10)
    axes[0].grid(axis="y", visible=False)
    axes[1].barh(top.index, top["mel"], color=viz.BLUE, height=0.6)
    axes[1].set_title("… pour la classe mélanome seulement", loc="left", fontsize=10)
    axes[1].grid(axis="y", visible=False)
    for ax in axes:
        ax.set_xlabel("|SHAP| moyen (log-odds)")
    fig.tight_layout(); viz.save(fig, "09_shap_M2")
    return tab


# --------------------------------------------------------------------------
# Mélanome vs nævus : séparation des probabilités
# --------------------------------------------------------------------------
def mel_nv_figure(runs: dict, df: pd.DataFrame) -> pd.DataFrame:
    y = df.y.to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.3), sharey=True)
    rows = []
    bins = np.linspace(0, 1, 26)
    for ax, exp in zip(axes, ["M1", "M5"]):
        r = runs[(exp, SEED)]
        yt, pm = y[r["idx_test"]], r["p_test"][:, C.MEL]
        t, _ = tune_mel_threshold(r["p_val"], y[r["idx_val"]], C.DEFAULT_COST_RATIO)
        ax.hist(pm[yt == 0], bins=bins, color=viz.NEUTRAL, label="vrais nævus", density=True)
        ax.hist(pm[yt == C.MEL], bins=bins, color=viz.BLUE, alpha=0.75, label="vrais mélanomes", density=True)
        ax.axvline(t, color=viz.INK, lw=1.2); ax.text(t + 0.01, ax.get_ylim()[1] * 0.85, f"seuil R=10 : {t:.2f}",
                                                     fontsize=8, color=viz.INK2)
        ax.set_yscale("log"); ax.set_xlabel("p(mélanome)")
        ax.set_title(f"{exp} : p(mélanome) des nævus et des mélanomes (test)", loc="left", fontsize=10)
        ax.legend()
        for s in C.TRAIN_SEEDS:
            if (exp, s) in runs:
                rr = runs[(exp, s)]
                ytt = y[rr["idx_test"]]
                tt, _ = tune_mel_threshold(rr["p_val"], y[rr["idx_val"]], C.DEFAULT_COST_RATIO)
                for dec, pred in [("classique", rr["p_test"].argmax(1)), ("coût R=10", decide(rr["p_test"], tt))]:
                    rows.append({"modèle": exp, "graine": s, "décision": dec,
                                 "mel → nv": int(((ytt == C.MEL) & (pred == 0)).sum()),
                                 "mel → autre bénin": int(((ytt == C.MEL) & ~np.isin(pred, [0, C.MEL])).sum()),
                                 "nv → mel": int(((ytt == 0) & (pred == C.MEL)).sum()),
                                 "mélanomes": int((ytt == C.MEL).sum()), "nævus": int((ytt == 0).sum())})
    fig.tight_layout(); viz.save(fig, "09_mel_vs_nv")
    tab = pd.DataFrame(rows)
    tab.to_csv(C.TAB_DIR / "09_confusions_mel_nv.csv", index=False)
    return tab


# --------------------------------------------------------------------------
# Bonus : robustesse aux données cliniques manquantes
# --------------------------------------------------------------------------
def missing_clinical_table(runs: dict, df: pd.DataFrame) -> pd.DataFrame:
    y = df.y.to_numpy()
    rows = []
    for exp in ["M1", "M3", "M5", "M5_dropClin"]:
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            r = runs[(exp, seed)]
            for cond, noclin in [("contexte complet", False), ("contexte manquant", True)]:
                if noclin and "p_noclin_test" not in r:
                    continue
                ev = evaluate_run(r, y, ratios=[C.DEFAULT_COST_RATIO], noclin=noclin)
                for dec in ["classique", f"coût R={C.DEFAULT_COST_RATIO}"]:
                    m = fast_metrics(ev["y_test"], ev[dec]["pred"])
                    rows.append({"modèle": exp, "graine": seed, "test": cond, "décision": dec, **m})
    tab = pd.DataFrame(rows)
    tab.to_csv(C.TAB_DIR / "10_bonus_contexte_manquant_par_graine.csv", index=False)
    summ = tab.groupby(["modèle", "test", "décision"], sort=False).agg(["mean", "std"]).drop(columns="graine")
    summ.round(3).to_csv(C.TAB_DIR / "10_bonus_contexte_manquant.csv")
    return tab


# --------------------------------------------------------------------------
# Étape 10 : sous-groupes (type de vérité terrain, sexe, âge)
# --------------------------------------------------------------------------
def subgroup_table(runs: dict, df: pd.DataFrame, exps=("M1", "M5")) -> pd.DataFrame:
    y = df.y.to_numpy()
    rows = []
    for exp in exps:
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            r = runs[(exp, seed)]
            idx = r["idx_test"]
            ev = evaluate_run(r, y, ratios=[C.DEFAULT_COST_RATIO])
            sub = df.iloc[idx]
            groups = {
                "vérité : histologie": sub.dx_type.to_numpy() == "histo",
                "vérité : suivi / consensus / confocal": sub.dx_type.to_numpy() != "histo",
                "sexe : homme": sub.sex.to_numpy() == "male",
                "sexe : femme": sub.sex.to_numpy() == "female",
                "âge < 50": sub.age.to_numpy() < 50,
                "âge ≥ 50": sub.age.to_numpy() >= 50,
            }
            for gname, mask in groups.items():
                for dec in ["classique", f"coût R={C.DEFAULT_COST_RATIO}"]:
                    yt, pred = ev["y_test"][mask], ev[dec]["pred"][mask]
                    nmel = int((yt == C.MEL).sum())
                    rows.append({"modèle": exp, "graine": seed, "sous-groupe": gname, "décision": dec,
                                 "images": int(mask.sum()), "mélanomes": nmel,
                                 "exactitude": float((yt == pred).mean()),
                                 "sensibilité mel": float((pred[yt == C.MEL] == C.MEL).mean()) if nmel else np.nan,
                                 "taux de fausse alerte mel": float((pred[yt != C.MEL] == C.MEL).mean())})
    tab = pd.DataFrame(rows)
    summ = tab.groupby(["sous-groupe", "modèle", "décision"], sort=False).mean(numeric_only=True).drop(columns="graine")
    summ.round(3).to_csv(C.TAB_DIR / "10_sous_groupes.csv")
    return summ


def main() -> None:
    viz.setup()
    df, enc, clin, bank = context()
    bank = np.asarray(bank)
    runs = load_runs(df)
    method = json.loads((C.TAB_DIR / "08_methode_conforme.json").read_text())["méthode"]   # choisi sur la validation
    print("Triage malin / bénin :")
    print(triage_table(runs, df, method).round(3).to_string())
    print(film_figures(df, enc, clin, bank).round(4).to_string())
    print(shap_figure(enc).head(8).round(4).to_string())
    print(mel_nv_figure(runs, df).groupby(["modèle", "décision"]).mean(numeric_only=True)
          .drop(columns="graine").round(1).to_string())
    cf = counterfactual_figure(df, enc, clin, bank)
    print(cf.pivot_table(index=["variable", "valeur"], columns=["modèle", "images"], values="p(mel) moyen")
          .round(3).to_string())
    gradcam_figure(runs, df, enc, clin, bank)
    print(missing_clinical_table(runs, df).groupby(["modèle", "test", "décision"], sort=False)
          .mean(numeric_only=True).drop(columns="graine").round(3).to_string())
    print(subgroup_table(runs, df).round(3).to_string())


if __name__ == "__main__":
    main()
