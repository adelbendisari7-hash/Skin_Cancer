"""Version 3 : HAM10000 + BCN20000 (recherche, non commercial), selon application/docs/plan_v3.md.

- `charger_v3`  : réunit les deux bases avec les mêmes 7 classes et une localisation en zones communes.
- `get_split_v3` : découpage HAM inchangé ; BCN20000 découpé par lésion, stratifié (graine 42).
- `zone_utile`  : carré inscrit dans le cercle du dermoscope quand les coins sont noirs (même règle pour les deux bases).
- `cache_v3`    : images 288 px écrites directement sur disque et lues à la demande (mmap) : 6,7 Go hors mémoire vive.
Les dossiers HAM10000 et BCN20000 ne sont jamais modifiés.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from . import config as C
from .data import get_split, split_by_lesion

BCN_DIR = Path(os.environ.get("BCN_DIR", C.PROJECT_DIR.parent / "BCN20000"))
SPLIT_V3_CSV = C.RESULTS_DIR / "split_v3.csv"

ZONES_HAM = {"back": "tronc", "trunk": "tronc", "abdomen": "tronc", "chest": "tronc",
             "face": "tete_cou", "scalp": "tete_cou", "neck": "tete_cou", "ear": "tete_cou",
             "upper extremity": "membre_sup", "hand": "membre_sup",
             "lower extremity": "membre_inf", "foot": "membre_inf",
             "genital": "autre", "acral": "autre", "unknown": "unknown"}
ZONES_BCN = {"Trunk": "tronc", "Head and neck": "tete_cou", "Upper extremity": "membre_sup",
             "Lower extremity": "membre_inf"}
CLASSES_BCN = {"Nevus": "nv", "Melanoma, NOS": "mel", "Basal cell carcinoma": "bcc",
               "Seborrheic keratosis": "bkl", "Solar lentigo": "bkl",
               "Solar or actinic keratosis": "akiec", "Squamous cell carcinoma, NOS": "akiec",
               "Dermatofibroma": "df"}


def classe_bcn(m: pd.DataFrame) -> pd.Series:
    """Diagnostic BCN → classe HAM ; NaN pour les exclus (métastases, cicatrices, sans diagnostic)."""
    dx = m.diagnosis_3.map(CLASSES_BCN)
    vasc = m.diagnosis_2.eq("Benign soft tissue proliferations - Vascular")
    return dx.mask(vasc, "vasc")


def charger_bcn() -> pd.DataFrame:
    m = pd.read_csv(next(BCN_DIR.glob("bcn20000_metadata*.csv")), low_memory=False)
    chemins = {p.stem: p for p in (BCN_DIR / "ISIC-images").glob("*.jpg")}
    manquantes = set(m.isic_id) - set(chemins)
    if manquantes:
        raise FileNotFoundError(f"{len(manquantes)} images BCN20000 introuvables, ex. {sorted(manquantes)[:3]}")
    m["dx"] = classe_bcn(m)
    m = m[m.dx.notna()].copy()
    zone = m.anatom_site_1.map(ZONES_BCN)
    zone = zone.mask(m.anatom_site_special.notna(), "autre")           # paumes, plantes, muqueuses
    return pd.DataFrame({
        "image_id": m.isic_id, "lesion_id": m.lesion_id, "dx": m.dx,
        "age": m.age_approx.astype(float), "sex": m.sex.fillna("unknown"),
        "localization": zone.fillna("unknown"), "path": m.isic_id.map(chemins), "source": "BCN20000"})


def charger_v3() -> pd.DataFrame:
    """Les deux bases, triées par source puis image (ordre des lignes du cache)."""
    ham = get_split()
    ham = ham.assign(localization=ham.localization.map(ZONES_HAM), source="HAM10000")
    assert ham.localization.notna().all(), "localisation HAM non prévue dans ZONES_HAM"
    cols = ["image_id", "lesion_id", "dx", "age", "sex", "localization", "path", "source"]
    df = pd.concat([ham[cols + ["split"]], charger_bcn()], ignore_index=True)
    df["y"] = df.dx.map({c: i for i, c in enumerate(C.CLASSES)}).astype(int)
    return df.sort_values(["source", "image_id"], kind="stable").reset_index(drop=True)


def get_split_v3() -> pd.DataFrame:
    """HAM garde son découpage ; BCN est découpé par lésion (sauvegardé pour que tous les modèles le partagent)."""
    df = charger_v3()
    bcn = df.source == "BCN20000"
    if SPLIT_V3_CSV.exists():
        sauve = pd.read_csv(SPLIT_V3_CSV).set_index("image_id").split
        df.loc[bcn, "split"] = df.loc[bcn, "image_id"].map(sauve)
    else:
        assert df[bcn].groupby("lesion_id").dx.nunique().max() == 1, "une lésion BCN a plusieurs diagnostics"
        parts = split_by_lesion(df[bcn].drop(columns="split"), C.SPLIT_SEED)
        df.loc[bcn, "split"] = parts.split.to_numpy()
        df.loc[bcn, ["image_id", "lesion_id", "dx", "split"]].to_csv(SPLIT_V3_CSV, index=False)
    assert df.split.notna().all(), "découpage v3 incomplet : supprimer split_v3.csv"
    les = df.groupby("lesion_id").split.nunique()
    assert les.max() == 1, "une lésion est dans deux jeux"
    return df


def zone_utile(im: Image.Image, seuil_coins: float = 30, seuil_clair: float = 20) -> tuple[int, int, int, int] | None:
    """Carré inscrit dans le cercle du dermoscope si les coins sont noirs, sinon None (image gardée entière)."""
    g = np.asarray(im.convert("L").resize((256, 256)), dtype=np.float32)
    s = 20
    coins = np.mean([g[:s, :s].mean(), g[:s, -s:].mean(), g[-s:, :s].mean(), g[-s:, -s:].mean()])
    if coins >= seuil_coins:
        return None
    m = g > seuil_clair
    if m.mean() < 0.15:
        return None
    ys, xs = np.nonzero(m)
    cy, cx = ys.mean() / 256, xs.mean() / 256
    c = np.sqrt(m.mean() / np.pi) * np.sqrt(2) * 0.97                  # côté du carré inscrit (côté image = 1)
    W, H = im.size
    return (int(max(0.0, cx - c / 2) * W), int(max(0.0, cy - c / 2) * H),
            int(min(1.0, cx + c / 2) * W), int(min(1.0, cy + c / 2) * H))


def _image(path: Path, taille: int) -> tuple[np.ndarray, bool]:
    with Image.open(path) as im:
        im = im.convert("RGB")
        b = zone_utile(im)
        if b:
            im = im.crop(b)
        return np.asarray(im.resize((taille, taille), Image.LANCZOS), dtype=np.uint8), b is not None


def cache_v3(df: pd.DataFrame, taille: int = 288) -> np.ndarray:
    """Cache uint8 (n, taille, taille, 3) sur disque, dans l'ordre de `charger_v3`, lu en mmap."""
    cache = C.CACHE_DIR / f"images_v3_{taille}.npy"
    ids = C.CACHE_DIR / f"images_v3_{taille}_ids.txt"
    if cache.exists() and ids.exists() and ids.read_text().split() == list(df.image_id):
        return np.load(cache, mmap_mode="r")
    ids.unlink(missing_ok=True)
    banque = np.lib.format.open_memmap(cache, mode="w+", dtype=np.uint8, shape=(len(df), taille, taille, 3))
    recadrees = np.zeros(len(df), dtype=bool)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for debut in range(0, len(df), 1024):
            lot = list(ex.map(lambda p: _image(p, taille), df.path.iloc[debut:debut + 1024]))
            banque[debut:debut + len(lot)] = np.stack([a for a, _ in lot])
            recadrees[debut:debut + len(lot)] = [r for _, r in lot]
            print(f"  cache v3 : {debut + len(lot)}/{len(df)}", flush=True)
    banque.flush()
    del banque
    pd.DataFrame({"image_id": df.image_id, "source": df.source, "recadree": recadrees}).to_csv(
        C.TAB_DIR / "14_v3_recadrage.csv", index=False)
    ids.write_text("\n".join(df.image_id))
    return np.load(cache, mmap_mode="r")
