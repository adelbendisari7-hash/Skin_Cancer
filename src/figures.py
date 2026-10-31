"""Figures des étapes 4 à 8 (comparaison, coût, abstention), au style commun de viz.py."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import viz
from .conformal import Conformal, abstain_rule
from .decision import W_GRID, decide, tune_mel_threshold
from .evaluate import MODELS, evaluate_run
from .metrics import confusion, fast_metrics
from .viz import plt

def color_of(model: str) -> str:
    """Couleur fixe d'un modèle, à partir de son identifiant ou de son nom affiché."""
    return viz.MODEL_COLORS.get(MODELS.get(model, model), viz.BLUE)


def pipeline_diagram(method: str) -> None:
    """Schéma du modèle proposé M5 (de l'entrée à la décision prudente)."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    fig, ax = plt.subplots(figsize=(12, 4.1))
    ax.set_xlim(0, 12); ax.set_ylim(0, 4.1); ax.axis("off")

    def box(x, y, w, h, title, sub="", fill="#eef4fc", edge=viz.BLUE):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc=fill, ec=edge, lw=1.3))
        ax.text(x + w / 2, y + h / 2 + (0.16 if sub else 0), title, ha="center", va="center",
                fontsize=9.5, color=viz.INK, fontweight="bold")
        if sub:
            ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center", fontsize=7.8, color=viz.INK2)

    def arrow(x0, y0, x1, y1, text=""):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=11,
                                     color=viz.MUTED, lw=1.2))
        if text:
            ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.13, text, ha="center", fontsize=7.5, color=viz.INK2)

    box(0.1, 2.55, 1.6, 0.95, "Image", "dermoscopie 224 px")
    box(0.1, 0.55, 1.6, 0.95, "Contexte", "âge, sexe, localisation")
    box(2.2, 2.55, 2.0, 0.95, "EfficientNet-B0", "pré-entraîné ImageNet")
    box(2.2, 0.55, 2.0, 0.95, "MLP clinique", "20 → 64 → 64")
    box(4.75, 1.55, 2.0, 1.25, "FiLM", "h ← (1+γ) ⊙ h + β", fill="#fbeef3", edge=viz.MAGENTA)
    box(7.25, 1.6, 1.45, 1.15, "Tête", "p(classe)")
    box(9.1, 2.55, 2.8, 0.95, "Décision au coût", "mel si p(mel) ≥ t*  (t* réglé sur val., R=10)",
        fill="#fff6e5", edge=viz.YELLOW)
    label = {"mondrian": "LAC par classe (Mondrian)", "lac": "LAC", "aps": "APS"}[method]
    box(9.1, 0.55, 2.8, 0.95, "Ensemble conforme", f"{label}, α = {C.ALPHA:g}".replace(".", ","),
        fill="#e9f7f1", edge=viz.AQUA)
    arrow(1.7, 3.02, 2.2, 3.02); arrow(1.7, 1.02, 2.2, 1.02)
    arrow(4.2, 3.02, 4.9, 2.62); arrow(4.2, 1.02, 4.9, 1.7)
    ax.text(4.75, 3.05, "h : 1 280 canaux", ha="left", fontsize=7.5, color=viz.INK2)
    ax.text(4.75, 1.0, "γ, β : 2 × 1 280", ha="left", fontsize=7.5, color=viz.INK2)
    arrow(6.75, 2.17, 7.25, 2.17); arrow(8.7, 2.35, 9.1, 2.95); arrow(8.7, 2.0, 9.1, 1.1)
    ax.text(6.0, 0.18, "Perte d'entraînement pondérée (classes rares, mélanome ×2)", ha="center",
            fontsize=8, color=viz.INK2, style="italic")
    ax.text(10.5, 3.78, "IA traite le cas si l'ensemble = {décision au coût} ;\nsinon → renvoi au médecin",
            ha="center", fontsize=8.3, color=viz.INK)
    fig.tight_layout(); viz.save(fig, "06_schema_M5")


def learning_curves(exps: list[str]) -> None:
    """F1 macro de validation par époque (une couleur par modèle, un trait par graine)."""
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    for exp in exps:
        hs = [pd.read_csv(f).set_index("époque")["F1 macro val"]
              for s in C.TRAIN_SEEDS if (f := C.PRED_DIR / f"{exp}_s{s}_history.csv").exists()]
        if not hs:
            continue
        h = pd.concat(hs, axis=1)          # une colonne par graine (NaN après l'arrêt anticipé)
        col = color_of(exp)
        ax.fill_between(h.index, h.min(axis=1), h.max(axis=1), color=col, alpha=0.12, lw=0)
        ax.plot(h.index, h.mean(axis=1), color=col, lw=2, label=exp)
    ax.set_xlabel("Époque"); ax.set_ylabel("F1 macro (validation)")
    ax.set_title("Apprentissage : F1 macro de validation (moyenne et min–max sur 3 graines)", loc="left")
    ax.legend(ncol=3, loc="lower right")
    fig.tight_layout(); viz.save(fig, "04_courbes_apprentissage")


def m4_weight_curves(runs: dict) -> None:
    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    for seed in C.TRAIN_SEEDS:
        if ("M4", seed) in runs:
            r = runs[("M4", seed)]
            ax.plot(W_GRID, r["w_curve"], color=viz.YELLOW, lw=1.6, alpha=0.9)
            ax.plot([r["w"]], [r["w_curve"][list(W_GRID).index(r["w"])]], "o", color=viz.YELLOW,
                    ms=8, mec=viz.SURFACE, mew=2)
    ax.set_xlabel("Poids de l'image w   (p = w·p_image + (1−w)·p_clinique)")
    ax.set_ylabel("F1 macro (validation)")
    ax.set_title("M4 : choix du poids de fusion sur la validation (● = retenu)", loc="left")
    fig.tight_layout(); viz.save(fig, "06_M4_poids")


def comparison_dots(tab: pd.DataFrame, models: list[str], fname: str, title: str) -> None:
    """Moyenne ± écart-type sur 3 graines : décision classique (○) et au coût (●)."""
    metrics = ["F1 macro", "Exactitude équilibrée", "Sensibilité mel", "Coût attendu"]
    tab = tab[tab.modèle.isin(models)]
    fig, axes = plt.subplots(1, 4, figsize=(12, 0.42 * len(models) + 1.3), sharey=True)
    ypos = {m: i for i, m in enumerate(models[::-1])}
    for ax, met in zip(axes, metrics):
        for dec, marker, off in [("classique", "o", 0.14), (f"coût R={C.DEFAULT_COST_RATIO}", "o", -0.14)]:
            g = tab[tab.décision == dec].groupby("modèle")[met]
            mean, std = g.mean(), g.std(ddof=1)
            for m in models:
                if m not in mean:
                    continue
                col = color_of(m)
                filled = dec != "classique"
                ax.errorbar(mean[m], ypos[m] + off, xerr=std[m], fmt=marker, ms=6.5, color=col,
                            mfc=col if filled else viz.SURFACE, mew=1.6, ecolor=viz.MUTED, elinewidth=1, capsize=0)
        ax.set_title(met + (" (↓ mieux)" if met == "Coût attendu" else ""), loc="left", fontsize=10)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(list(ypos.values()), list(ypos.keys()))
    axes[0].plot([], [], "o", color=viz.MUTED, mfc=viz.SURFACE, label="décision classique (argmax)")
    axes[0].plot([], [], "o", color=viz.MUTED, label=f"décision au coût (R={C.DEFAULT_COST_RATIO})")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(title, x=0.01, ha="left", fontsize=11.5)
    fig.tight_layout(rect=(0, 0.06, 1, 1)); viz.save(fig, fname)


def confusion_pair(runs: dict, df: pd.DataFrame, a: tuple, b: tuple) -> dict:
    """Matrices de confusion (somme des 3 graines, normalisées par ligne) pour deux (exp, décision)."""
    y = df.y.to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    out = {}
    for ax, (exp, dec, label) in zip(axes, [a, b]):
        cm = np.zeros((C.N_CLASSES, C.N_CLASSES))
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) in runs:
                ev = evaluate_run(runs[(exp, seed)], y, ratios=[C.DEFAULT_COST_RATIO])
                cm += confusion(ev["y_test"], ev[dec]["pred"])
        out[label] = cm
        cmn = cm / cm.sum(1, keepdims=True)
        ax.imshow(cmn, cmap=viz.SEQ_BLUE, vmin=0, vmax=1)
        for i in range(C.N_CLASSES):
            for j in range(C.N_CLASSES):
                ax.text(j, i, f"{100 * cmn[i, j]:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if cmn[i, j] > 0.55 else viz.INK2,
                        fontweight="bold" if (i == C.MEL or j == C.MEL) and i != j and cmn[i, j] > 0.05 else None)
        ax.set_xticks(range(C.N_CLASSES), C.CLASSES); ax.set_yticks(range(C.N_CLASSES), C.CLASSES)
        ax.set_xlabel("Prédit"); ax.set_ylabel("Vrai"); ax.grid(False)
        ax.set_title(label, loc="left", fontsize=10.5)
    fig.suptitle("Matrices de confusion sur le test (% de chaque vraie classe, 3 graines cumulées)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); viz.save(fig, "08_matrices_confusion")
    return out


def cost_sensitivity(runs: dict, df: pd.DataFrame, exps: list[str]) -> pd.DataFrame:
    """Sensibilité au rapport de coût R : seuil, sensibilité/spécificité mélanome, coût attendu."""
    y = df.y.to_numpy()
    rows = []
    for exp in exps:
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            r = runs[(exp, seed)]
            yv, yt = y[r["idx_val"]], y[r["idx_test"]]
            for R in C.COST_RATIOS:
                t, _ = tune_mel_threshold(r["p_val"], yv, R)
                m = fast_metrics(yt, decide(r["p_test"], t), R)
                m0 = fast_metrics(yt, r["p_test"].argmax(1), R)
                rows.append({"modèle": exp, "graine": seed, "R": R, "seuil": t,
                             "Sensibilité mel": m["Sensibilité mel"], "Spécificité mel": m["Spécificité mel"],
                             "Coût attendu": m["Coût attendu"], "Coût attendu (argmax)": m0["Coût attendu"],
                             "F1 macro": m["F1 macro"]})
    tab = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.2))
    for k, exp in enumerate(exps):
        g = tab[tab.modèle == exp].groupby("R").mean(numeric_only=True)
        col = color_of(exp)
        for ax, met in zip(axes, ["Sensibilité mel", "Spécificité mel", "Coût attendu"]):
            ax.plot(g.index, g[met], "o-", color=col, ms=6, label=exp)
    for ax, met in zip(axes, ["Sensibilité mel", "Spécificité mel", "Coût attendu (↓)"]):
        ax.set_title(met, loc="left", fontsize=10); ax.set_xticks(C.COST_RATIOS)
        ax.set_xlabel("R = coût mélanome manqué / fausse alerte")
    axes[0].legend()
    fig.suptitle("Sensibilité des résultats au rapport de coût (seuil réglé sur la validation, moyenne 3 graines)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); viz.save(fig, "08_sensibilite_cout")
    return tab


def risk_coverage(runs: dict, df: pd.DataFrame, exps: list[str], method: str = "lac") -> pd.DataFrame:
    """Courbe risque-couverture : on fait varier α (conforme) ; référence = confiance max (softmax)."""
    y = df.y.to_numpy()
    # Au-delà de α = 0,2 les ensembles deviennent vides ou contredisent la décision au coût :
    # le taux de cas traités redescend (régime sans intérêt clinique).
    alphas = [0.05, 0.075, 0.1, 0.125, 0.15, 0.175, 0.2]
    rows = []
    for exp in exps:
        for seed in C.TRAIN_SEEDS:
            if (exp, seed) not in runs:
                continue
            r = runs[(exp, seed)]
            yv, yc, yt = (y[r[f"idx_{s}"]] for s in ["val", "calib", "test"])
            t, _ = tune_mel_threshold(r["p_val"], yv, C.DEFAULT_COST_RATIO)
            pred = decide(r["p_test"], t)
            mel = yt == C.MEL
            for a in alphas:
                cf = Conformal(method, a).fit(r["p_calib"], yc)
                tr = abstain_rule(cf.sets(r["p_test"]), pred)
                err = float((pred[tr] != yt[tr]).mean()) if tr.any() else np.nan
                rows.append({"modèle": exp, "graine": seed, "méthode": f"conforme {method.upper()}", "alpha": a,
                             "couverture": float(tr.mean()), "risque (erreur traités)": err,
                             "mel manqués en silence": int((mel & tr & (pred != C.MEL)).sum()),
                             "sensibilité mel traités": float((pred[tr & mel] == C.MEL).mean()) if (tr & mel).any() else np.nan})
            # Référence : on traite les cas les plus confiants (max softmax)
            conf = r["p_test"].max(1)
            order = np.argsort(-conf)
            for cov in np.linspace(0.1, 1.0, 19):
                n = int(round(cov * len(yt)))
                tr = np.zeros(len(yt), bool); tr[order[:n]] = True
                rows.append({"modèle": exp, "graine": seed, "méthode": "confiance max", "alpha": np.nan,
                             "couverture": cov, "risque (erreur traités)": float((pred[tr] != yt[tr]).mean()),
                             "mel manqués en silence": int((mel & tr & (pred != C.MEL)).sum()),
                             "sensibilité mel traités": float((pred[tr & mel] == C.MEL).mean()) if (tr & mel).any() else np.nan})
    tab = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for k, exp in enumerate(exps):
        col = color_of(exp)
        sub = tab[tab.modèle == exp]
        conf = sub[sub.méthode.str.startswith("conforme")].groupby("alpha").mean(numeric_only=True)
        conf = conf[conf["couverture"] > 0].sort_values("couverture")   # α trop petit : tout est renvoyé
        base = sub[sub.méthode == "confiance max"].groupby("couverture").mean(numeric_only=True)
        for ax, met in [(axes[0], "risque (erreur traités)"), (axes[1], "mel manqués en silence")]:
            ax.plot(conf["couverture"], conf[met], "o-", color=col, ms=5, label=f"{exp} conforme (α variable)")
            ax.plot(base.index, base[met], "-", color=col, lw=1.2, alpha=0.55, label=f"{exp} confiance max")
        if exp == exps[-1]:
            for a, row in conf.iterrows():
                if a in (0.05, 0.1, 0.2):
                    axes[0].annotate(f"α={a:g}", (row["couverture"], row["risque (erreur traités)"]),
                                     textcoords="offset points", xytext=(4, -11), fontsize=7.5, color=viz.INK2)
    axes[0].set_xlabel("Couverture (part des cas traités par l'IA)"); axes[0].set_ylabel("Erreur sur les cas traités")
    axes[0].set_title("Risque-couverture", loc="left"); axes[0].legend(fontsize=7.5)
    axes[1].set_xlabel("Couverture"); axes[1].set_ylabel("Mélanomes du test classés bénins sans renvoi")
    axes[1].set_title("Mélanomes manqués « en silence » (moyenne 3 graines)", loc="left"); axes[1].legend(fontsize=7.5)
    fig.tight_layout(); viz.save(fig, "08_risque_couverture")
    return tab
