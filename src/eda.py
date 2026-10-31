"""Étape 2 — exploration des deux modalités (clinique et image).

Produit les figures `02_*.png` et les tableaux `02_*.csv` dans resultats/.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from PIL import Image
from scipy import stats

from . import config as C
from . import viz
from .viz import plt


def cramers_v(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """V de Cramér (force d'association entre deux variables catégorielles) et p-valeur du χ²."""
    tab = pd.crosstab(x, y)
    chi2, p, _, _ = stats.chi2_contingency(tab)
    n = tab.to_numpy().sum()
    return float(np.sqrt(chi2 / (n * (min(tab.shape) - 1)))), float(p)


def profile_table(df: pd.DataFrame) -> pd.DataFrame:
    """Profil de chaque colonne : type, valeurs manquantes, cardinalité, valeurs fréquentes."""
    rows = []
    for col in ["lesion_id", "image_id", "dx", "dx_type", "age", "sex", "localization"]:
        s = df[col]
        unknown = int((s == "unknown").sum()) if s.dtype == object or str(s.dtype) == "str" else 0
        top = s.value_counts().head(3)
        rows.append({
            "colonne": col, "type": str(s.dtype), "manquants": int(s.isna().sum()),
            "« unknown »": unknown, "valeurs distinctes": int(s.nunique()),
            "plus fréquentes": ", ".join(f"{k} ({v})" for k, v in top.items()),
        })
    return pd.DataFrame(rows)


def run_eda(df: pd.DataFrame) -> dict:
    viz.setup()
    out: dict = {}
    order = C.CLASSES

    # ---- Profil et qualité -------------------------------------------------
    prof = profile_table(df)
    prof.to_csv(C.TAB_DIR / "02_profil_colonnes.csv", index=False)
    out["profil"] = prof
    ages = df.age.dropna()
    out["age_stats"] = ages.describe().round(1).to_dict()
    out["age_zero"] = int((df.age == 0).sum())
    out["age_multiple_5"] = float((ages % 5 == 0).mean())

    # ---- Classes : images et lésions ---------------------------------------
    cls = pd.DataFrame({
        "images": df.dx.value_counts().reindex(order),
        "lesions": df.drop_duplicates("lesion_id").dx.value_counts().reindex(order),
    })
    cls["% images"] = (100 * cls.images / cls.images.sum()).round(1)
    cls["images / lésion"] = (cls.images / cls.lesions).round(2)
    cls.index.name = "dx"
    cls.to_csv(C.TAB_DIR / "02_classes.csv")
    out["classes"] = cls

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), sharey=True)
    for ax, col, title in [(axes[0], "images", "Images par classe"),
                           (axes[1], "lesions", "Lésions distinctes par classe")]:
        vals = cls[col]
        ax.barh(order[::-1], vals[::-1], color=viz.emphasis_colors(order[::-1]), height=0.62)
        for i, v in enumerate(vals[::-1]):
            ax.text(v + vals.max() * 0.01, i, f"{v:,}".replace(",", " "), va="center",
                    fontsize=8, color=viz.INK2)
        ax.set_title(title, loc="left"); ax.grid(axis="y", visible=False)
        ax.set_xlim(0, vals.max() * 1.15)
    fig.suptitle("Déséquilibre des classes : 67 % de nævus, 11 % de mélanomes (en bleu)",
                 x=0.01, ha="left", fontsize=11.5, color=viz.INK)
    fig.tight_layout(); viz.save(fig, "02_classes")

    # ---- Images par lésion ---------------------------------------------------
    per_les = df.groupby("lesion_id").size()
    dist = per_les.value_counts().sort_index()
    out["images_par_lesion"] = dist.to_dict()
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    ax.bar(dist.index.astype(str), dist.values, color=viz.BLUE, width=0.6)
    for x, v in zip(dist.index.astype(str), dist.values):
        ax.text(x, v + 60, str(v), ha="center", fontsize=8, color=viz.INK2)
    ax.set_xlabel("Nombre d'images de la même lésion"); ax.set_ylabel("Lésions")
    ax.set_title("26 % des lésions ont plusieurs images → découpage par lésion", loc="left")
    ax.grid(axis="x", visible=False)
    fig.tight_layout(); viz.save(fig, "02_images_par_lesion")

    # ---- Âge par classe -------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    data = [df.loc[df.dx == c, "age"].dropna() for c in order[::-1]]
    bp = ax.boxplot(data, vert=False, tick_labels=order[::-1], widths=0.55, patch_artist=True,
                    medianprops=dict(color=viz.INK, linewidth=1.5), showfliers=False,
                    whiskerprops=dict(color=viz.MUTED), capprops=dict(color=viz.MUTED))
    for patch, c in zip(bp["boxes"], order[::-1]):
        patch.set(facecolor=viz.BLUE if c == "mel" else viz.NEUTRAL, edgecolor="none", alpha=0.9)
    ax.set_xlabel("Âge (années)")
    ax.set_title("Âge par diagnostic : les nævus touchent des patients plus jeunes", loc="left")
    ax.grid(axis="y", visible=False)
    fig.tight_layout(); viz.save(fig, "02_age_par_classe")
    kw = stats.kruskal(*[d for d in data if len(d)])
    out["kruskal_age"] = (float(kw.statistic), float(kw.pvalue))

    # ---- Sexe et localisation : P(dx | variable) --------------------------------
    for var, fname, title in [
        ("sex", "02_sexe", "Répartition des diagnostics selon le sexe (% de la ligne)"),
        ("localization", "02_localisation",
         "Répartition des diagnostics selon la localisation (% de la ligne)"),
    ]:
        tab = pd.crosstab(df[var], df.dx, normalize="index").reindex(columns=order) * 100
        counts = df[var].value_counts()
        tab = tab.loc[counts.index]
        tab.index = [f"{i} (n={counts[i]})" for i in tab.index]
        tab.round(1).to_csv(C.TAB_DIR / f"{fname}.csv")
        h = 0.32 * len(tab) + 1.2
        fig, ax = plt.subplots(figsize=(7.2, h))
        im = ax.imshow(tab.to_numpy(), cmap=viz.SEQ_BLUE, vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(order)), order); ax.set_yticks(range(len(tab)), tab.index)
        ax.grid(False)
        for i in range(tab.shape[0]):
            for j in range(tab.shape[1]):
                v = tab.iat[i, j]
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if v > 55 else viz.INK2)
        ax.set_title(title, loc="left", fontsize=10.5)
        fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02).outline.set_visible(False)
        fig.tight_layout(); viz.save(fig, fname)

    # ---- Force d'association avec le diagnostic ---------------------------------
    assoc = []
    for var in ["sex", "localization", "dx_type"]:
        v, p = cramers_v(df[var], df.dx)
        assoc.append({"variable": var, "V de Cramér": round(v, 3), "p (χ²)": f"{p:.1e}"})
    age_bins = pd.cut(df.age, [-1, 20, 35, 50, 65, 100]).astype(str)
    v, p = cramers_v(age_bins, df.dx)
    assoc.append({"variable": "age (5 tranches)", "V de Cramér": round(v, 3), "p (χ²)": f"{p:.1e}"})
    assoc = pd.DataFrame(assoc)
    assoc.to_csv(C.TAB_DIR / "02_association_dx.csv", index=False)
    out["association"] = assoc

    # ---- dx_type : la fuite d'information -----------------------------------------
    ct = pd.crosstab(df.dx, df.dx_type).reindex(order)
    ct.to_csv(C.TAB_DIR / "02_dx_type.csv")
    out["dx_type"] = ct

    # ---- Exemples d'images par classe -------------------------------------------
    rng = np.random.default_rng(C.SPLIT_SEED)
    ncol = 6
    fig, axes = plt.subplots(len(order), ncol, figsize=(ncol * 1.35, len(order) * 1.15))
    for i, c in enumerate(order):
        paths = df.loc[df.dx == c, "path"].to_numpy()
        for j, p in enumerate(rng.choice(paths, ncol, replace=False)):
            ax = axes[i, j]
            with Image.open(p) as im:
                ax.imshow(im.resize((150, 112)))
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
            for s in ax.spines.values():
                s.set_visible(False)
            if j == 0:
                ax.set_ylabel(c, rotation=0, ha="right", va="center", fontsize=9, color=viz.INK)
    fig.suptitle("Exemples d'images dermoscopiques par classe (600×450 px d'origine)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); viz.save(fig, "02_exemples_images")

    # ---- Taille et couleur moyenne des images ---------------------------------------
    sizes = {}
    for p in df.path.sample(300, random_state=0):
        with Image.open(p) as im:
            sizes[im.size] = sizes.get(im.size, 0) + 1
    out["tailles_images_echantillon"] = sizes
    return out
