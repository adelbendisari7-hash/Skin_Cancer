"""Étape 3 — prétraitement : découpage par lésion, encodage clinique, cache d'images.

Usage : python -m src.prepare
Vérifie aussi l'absence de fuite (aucune lésion partagée entre deux jeux).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import viz
from .data import ClinicalEncoder, build_image_cache, get_split
from .viz import plt

SPLITS = ["train", "val", "calib", "test"]


def check_split(df: pd.DataFrame) -> pd.DataFrame:
    """Contrôles du découpage ; lève une erreur si une lésion est dans deux jeux."""
    per_lesion = df.groupby("lesion_id").split.nunique()
    assert (per_lesion == 1).all(), "fuite : une lésion apparaît dans plusieurs jeux"
    assert set(df.split) == set(SPLITS)
    tab = pd.crosstab(df.dx, df.split).reindex(index=C.CLASSES, columns=SPLITS)
    les = pd.crosstab(df.drop_duplicates("lesion_id").dx,
                      df.drop_duplicates("lesion_id").split).reindex(index=C.CLASSES, columns=SPLITS)
    out = pd.concat({"images": tab, "lésions": les}, axis=1)
    out.loc["total"] = out.sum()
    return out


def main() -> None:
    viz.setup()
    df = get_split()
    summary = check_split(df)
    summary.to_csv(C.TAB_DIR / "03_decoupage.csv")
    print(summary.to_string())
    frac_les = df.drop_duplicates("lesion_id").split.value_counts(normalize=True).reindex(SPLITS)
    frac_img = df.split.value_counts(normalize=True).reindex(SPLITS)
    print("\nFraction des lésions :", frac_les.round(3).to_dict())
    print("Fraction des images  :", frac_img.round(3).to_dict())

    # Proportion de chaque classe dans chaque jeu (doit être quasi identique : stratification)
    prop = pd.crosstab(df.dx, df.split, normalize="columns").reindex(index=C.CLASSES, columns=SPLITS)
    print("\nProportion de classes par jeu (%) :\n", (100 * prop).round(1).to_string())
    assert (prop.max(axis=1) - prop.min(axis=1)).max() < 0.03, "stratification déséquilibrée"

    # Encodeur clinique ajusté sur le train seulement
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    X = enc.transform(df)
    print(f"\nVariables cliniques encodées : {enc.n_features} → {enc.feature_names}")
    print(f"Médiane d'âge (train) = {enc.age_median}, moyenne = {enc.age_mean:.1f}, écart-type = {enc.age_std:.1f}")
    tr = X[df.split.to_numpy() == "train"]
    print("Contrôle normalisation train : moyenne âge %.3f, écart-type %.3f" % (tr[:, 0].mean(), tr[:, 0].std()))
    assert not np.isnan(X).any()

    # Cache des images 224×224
    bank = build_image_cache(df)
    print(f"\nCache images : {bank.shape}, {bank.dtype}, {bank.nbytes / 1e9:.2f} Go")
    assert bank.shape == (len(df), C.IMG_SIZE, C.IMG_SIZE, 3)

    # Figure : composition des jeux (lésions par classe), petites séries côte à côte
    fig, axes = plt.subplots(1, 4, figsize=(11, 2.8), sharey=True)
    les = summary["lésions"].drop("total")
    for ax, s in zip(axes, SPLITS):
        ax.barh(C.CLASSES[::-1], les[s][::-1], color=viz.emphasis_colors(C.CLASSES[::-1]), height=0.6)
        for i, v in enumerate(les[s][::-1]):
            ax.text(v + les[s].max() * 0.02, i, str(v), va="center", fontsize=7.5, color=viz.INK2)
        ax.set_title(f"{s} ({summary.loc['total', ('lésions', s)]} lésions)", loc="left", fontsize=10)
        ax.set_xlim(0, les[s].max() * 1.25); ax.grid(axis="y", visible=False)
    fig.suptitle("Découpage par lésion stratifié 70/10/10/10 — lésions par classe (mélanome en bleu)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); viz.save(fig, "03_decoupage")

    # Exemple d'augmentation (contrôle visuel)
    import torch
    from .data import gpu_augment, to_device_batch
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    g = torch.Generator(device=dev).manual_seed(0)
    i0 = int(np.flatnonzero(df.dx.to_numpy() == "mel")[0])
    x = to_device_batch(bank, np.array([i0] * 6), dev)
    xa = gpu_augment(x, g)
    fig, axes = plt.subplots(1, 7, figsize=(11, 1.9))
    for ax, im, t in zip(axes, [x[0]] + list(xa), ["original 224 px"] + [f"augmentée {k}" for k in range(1, 7)]):
        ax.imshow(im.permute(1, 2, 0).cpu().numpy()); ax.set_title(t, fontsize=8, loc="left")
        ax.axis("off")
    fig.tight_layout(); viz.save(fig, "03_augmentations")
    print("OK : découpage, encodage et cache vérifiés.")


if __name__ == "__main__":
    main()
