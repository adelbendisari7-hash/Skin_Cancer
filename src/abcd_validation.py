"""Proposition 11 — validation des critères ABCD automatiques sur HAM10000.

Les seuils (asymétrie de forme / de couleur, bord abrupt, part minimale d'une couleur) sont choisis
sur le jeu de VALIDATION (meilleure AUC mélanome contre nævus de chaque score) ; les performances sont
mesurées ensuite sur le jeu de TEST. Résultats : resultats/tableaux/11_abcd_*.csv, figure 11_abcd_*.png,
et le fichier de seuils de l'application (application/backend/dermia/engine/seuils_abcd.json).

Usage : python -m src.abcd_validation
"""
from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.metrics import roc_auc_score

from . import config as C
from . import viz
from .data import get_split
from .viz import plt

APP = C.PROJECT_DIR / "application" / "backend"
sys.path.insert(0, str(APP))
from dermia.engine import abcd  # noqa: E402


def _mesures_brutes(chemin: str) -> dict:
    m = abcd.mesurer(Image.open(chemin))
    if m["A"] is None:
        return {"ok": False}
    return {"ok": True, "fiable": m["fiable"], "forme": m["A"]["indice_forme"], "couleur": m["A"]["ecart_couleur"],
            "intensites": m["B"]["intensites"], "fractions": m["C"]["fractions"],
            "irregularite": m["B"]["irregularite"], "surface": m["surface_relative"]}


def calculer(df: pd.DataFrame) -> list[dict]:
    with ProcessPoolExecutor(max_workers=6) as ex:
        return list(ex.map(_mesures_brutes, df.path.astype(str), chunksize=16))


def scores(mes: list[dict], s: dict) -> pd.DataFrame:
    rows = []
    for m in mes:
        if not m["ok"]:
            rows.append({"A": np.nan, "B": np.nan, "C": np.nan, "irregularite": np.nan})
            continue
        a = sum(f > s["forme"] or c > s["couleur"] for f, c in zip(m["forme"], m["couleur"]))
        b = sum(v > s["abrupt"] for v in m["intensites"])
        c = max(sum(f >= s["part_couleur"] for f in m["fractions"].values()), 1)
        rows.append({"A": a, "B": b, "C": c, "irregularite": m["irregularite"]})
    return pd.DataFrame(rows)


def auc_mel_nv(y: np.ndarray, x: np.ndarray) -> float:
    sel = np.isin(y, [0, C.MEL]) & ~np.isnan(x)
    return float(roc_auc_score(y[sel] == C.MEL, x[sel]))


def main() -> None:
    viz.setup()
    df = get_split()
    val, test = df[df.split == "val"].reset_index(drop=True), df[df.split == "test"].reset_index(drop=True)
    print("mesures validation…"); mv = calculer(val)
    print("mesures test…"); mt = calculer(test)
    yv, yt = val.y.to_numpy(), test.y.to_numpy()

    # ---- choix des seuils sur la validation
    base = dict(abcd.SEUILS_DEFAUT)
    grille_a = list(itertools.product([0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3], [4, 6, 8, 10, 12, 15, 20]))
    best_a = max(grille_a, key=lambda fc: auc_mel_nv(yv, scores(mv, {**base, "forme": fc[0], "couleur": fc[1]}).A.to_numpy(float)))
    best_b = max([0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0],
                 key=lambda t: auc_mel_nv(yv, scores(mv, {**base, "abrupt": t}).B.to_numpy(float)))
    best_c = max([0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.1],
                 key=lambda t: auc_mel_nv(yv, scores(mv, {**base, "part_couleur": t}).C.to_numpy(float)))
    choisis = {"forme": best_a[0], "couleur": float(best_a[1]), "abrupt": best_b, "part_couleur": best_c}
    print("seuils choisis sur la validation :", choisis)

    # ---- mesure sur le test (une fois)
    st = scores(mt, choisis)
    st["dx"] = test.dx.to_numpy()
    lignes = []
    for crit in ["A", "B", "C", "irregularite"]:
        x = st[crit].to_numpy(float)
        ok = ~np.isnan(x)
        lignes.append({"critère": crit, "AUC mélanome vs nævus": round(auc_mel_nv(yt, x), 3),
                       "AUC mélanome vs reste": round(float(roc_auc_score(yt[ok] == C.MEL, x[ok])), 3),
                       "moyenne mélanome": round(float(np.nanmean(x[yt == C.MEL])), 2),
                       "moyenne nævus": round(float(np.nanmean(x[yt == 0])), 2)})
    perf = pd.DataFrame(lignes)
    echec = float(np.mean([not m["ok"] for m in mt]))
    peu_fiable = float(np.mean([m["ok"] and not m["fiable"] for m in mt]))
    perf.to_csv(C.TAB_DIR / "11_abcd_performances_test.csv", index=False)
    st.groupby("dx")[["A", "B", "C", "irregularite"]].mean().round(2).reindex(C.CLASSES).to_csv(C.TAB_DIR / "11_abcd_moyennes_par_classe.csv")
    print(perf.to_string(index=False))
    print(f"segmentation impossible : {100 * echec:.1f} % ; lésion coupée par le cadre : {100 * peu_fiable:.1f} %")

    sortie = {**choisis, "_source": "choisis sur la validation HAM10000 (src/abcd_validation.py)",
              "_test": {"auc_mel_nv": {r["critère"]: r["AUC mélanome vs nævus"] for r in lignes},
                        "segmentation_impossible": round(echec, 4), "lesion_coupee": round(peu_fiable, 4),
                        "n_images": len(test)}}
    (APP / "dermia" / "engine" / "seuils_abcd.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- planche de contrôle visuel des segmentations (test)
    rng = np.random.default_rng(0)
    choix = np.concatenate([rng.choice(np.flatnonzero(yt == C.MEL), 8, replace=False),
                            rng.choice(np.flatnonzero(yt == 0), 8, replace=False)])
    fig, axes = plt.subplots(4, 4, figsize=(12, 9.6))
    for ax, i in zip(axes.ravel(), choix):
        im = Image.open(test.path[i])
        m = abcd.mesurer(im)
        import io
        ax.imshow(Image.open(io.BytesIO(abcd.superposition_png(im, m, 400))))
        ax.set_title(f"{test.dx[i]} : A={m['A']['score'] if m['A'] else '–'} B={m['B']['score'] if m['B'] else '–'} "
                     f"C={m['C']['score'] if m['C'] else '–'}", fontsize=9, loc="left")
        ax.axis("off")
    fig.suptitle("Segmentation automatique et axes principaux (test HAM10000 : 8 mélanomes, 8 nævus)", x=0.01, ha="left")
    fig.tight_layout(); viz.save(fig, "11_abcd_segmentations")


if __name__ == "__main__":
    main()
