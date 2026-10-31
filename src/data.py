"""Chargement, découpage par lésion et prétraitement des deux modalités.

- `load_metadata`      : lit le CSV et retrouve le chemin de chaque image.
- `split_by_lesion`    : découpage stratifié train/val/calib/test au niveau LÉSION.
- `ClinicalEncoder`    : imputation + encodage + normalisation (ajusté sur le train).
- `build_image_cache`  : redimensionne une fois les images en 224 px (cache .npy).
- `gpu_augment`        : augmentations aléatoires appliquées par lot sur GPU (train seulement).
Le dossier HAM10000 n'est jamais modifié.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.model_selection import train_test_split

from . import config as C


# --------------------------------------------------------------------------
# Métadonnées
# --------------------------------------------------------------------------
def load_metadata() -> pd.DataFrame:
    """Lit HAM10000_metadata.csv, ajoute le chemin de l'image et l'indice de classe."""
    df = pd.read_csv(C.METADATA_CSV)
    paths = {p.stem: p for d in C.IMAGE_DIRS for p in d.glob("*.jpg")}
    missing = set(df.image_id) - set(paths)
    if missing:
        raise FileNotFoundError(f"{len(missing)} images introuvables, ex. {sorted(missing)[:3]}")
    df["path"] = df.image_id.map(paths)
    df["y"] = df.dx.map({c: i for i, c in enumerate(C.CLASSES)}).astype(int)
    # Ordre stable : c'est aussi l'ordre des lignes du cache d'images.
    return df.sort_values("image_id").reset_index(drop=True)


# --------------------------------------------------------------------------
# Découpage par lésion
# --------------------------------------------------------------------------
def split_by_lesion(df: pd.DataFrame, seed: int = C.SPLIT_SEED) -> pd.DataFrame:
    """Affecte chaque LÉSION à un seul jeu (train/val/calib/test), stratifié sur dx.

    Toutes les images d'une même lésion restent ensemble : sinon le modèle verrait
    au test une photo quasi identique à une photo d'entraînement (fuite).
    Chaque lésion n'a qu'un diagnostic (vérifié), donc on stratifie au niveau lésion.
    """
    les = df.groupby("lesion_id").dx.first().reset_index()
    fr = C.SPLIT_FRACTIONS
    train, rest = train_test_split(les, train_size=fr["train"], stratify=les.dx, random_state=seed)
    # Le reste (30 %) est coupé en trois parts égales.
    val, rest2 = train_test_split(rest, train_size=fr["val"] / (1 - fr["train"]),
                                  stratify=rest.dx, random_state=seed)
    calib, test = train_test_split(rest2, train_size=fr["calib"] / (fr["calib"] + fr["test"]),
                                   stratify=rest2.dx, random_state=seed)
    split_of = {}
    for name, part in [("train", train), ("val", val), ("calib", calib), ("test", test)]:
        split_of.update(dict.fromkeys(part.lesion_id, name))
    out = df.copy()
    out["split"] = out.lesion_id.map(split_of)
    return out


def get_split(seed: int = C.SPLIT_SEED) -> pd.DataFrame:
    """Charge le découpage sauvegardé (ou le crée), pour que tous les modèles partagent le même."""
    df = load_metadata()
    if C.SPLIT_CSV.exists():
        saved = pd.read_csv(C.SPLIT_CSV)[["image_id", "split"]]
        df = df.merge(saved, on="image_id", how="left", validate="one_to_one")
        assert df.split.notna().all(), "découpage incomplet : supprimer split_lesions.csv"
        return df
    df = split_by_lesion(df, seed)
    df[["lesion_id", "image_id", "dx", "split"]].to_csv(C.SPLIT_CSV, index=False)
    return df


# --------------------------------------------------------------------------
# Modalité clinique
# --------------------------------------------------------------------------
class ClinicalEncoder:
    """Imputation, encodage one-hot et normalisation des variables cliniques.

    Ajusté sur le train uniquement. Les valeurs manquantes deviennent :
    - âge : médiane du train + indicateur `age_manquant` ;
    - sexe / localisation : catégorie « unknown » (déjà présente dans les données).
    Une catégorie inconnue au test est ramenée à « unknown ».
    """

    def fit(self, df: pd.DataFrame) -> "ClinicalEncoder":
        age = df.age
        self.age_median = float(age.median())
        filled = age.fillna(self.age_median)
        self.age_mean, self.age_std = float(filled.mean()), float(filled.std())
        self.sex_cats = sorted(set(df.sex) | {"unknown"})
        self.loc_cats = sorted(set(df.localization) | {"unknown"})
        return self

    @property
    def feature_names(self) -> list[str]:
        return (["age", "age_manquant"] + [f"sex={c}" for c in self.sex_cats]
                + [f"loc={c}" for c in self.loc_cats])

    @property
    def n_features(self) -> int:
        return len(self.feature_names)

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        age = df.age.to_numpy(dtype=float)
        miss = np.isnan(age)
        age = np.where(miss, self.age_median, age)
        age = (age - self.age_mean) / self.age_std
        sex = df.sex.where(df.sex.isin(self.sex_cats), "unknown")
        loc = df.localization.where(df.localization.isin(self.loc_cats), "unknown")
        sex_oh = (sex.to_numpy()[:, None] == np.array(self.sex_cats)[None]).astype(float)
        loc_oh = (loc.to_numpy()[:, None] == np.array(self.loc_cats)[None]).astype(float)
        return np.column_stack([age, miss.astype(float), sex_oh, loc_oh]).astype(np.float32)

    def missing_context(self, n: int) -> np.ndarray:
        """Encodage d'un patient sans aucune donnée clinique (âge, sexe, localisation inconnus)."""
        empty = pd.DataFrame({"age": [np.nan] * n, "sex": ["unknown"] * n,
                              "localization": ["unknown"] * n})
        return self.transform(empty)


# --------------------------------------------------------------------------
# Modalité image : cache redimensionné
# --------------------------------------------------------------------------
def _load_resized(path: Path, size: int) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.uint8)


def build_image_cache(df: pd.DataFrame, size: int = C.IMG_SIZE) -> np.ndarray:
    """Redimensionne toutes les images (600×450 → size×size) une seule fois.

    Le cache (uint8, ~1,5 Go) suit l'ordre de `load_metadata()` (tri par image_id).
    Il est dérivé des données et peut être supprimé et régénéré à tout moment.
    """
    cache = C.CACHE_DIR / f"images_{size}.npy"
    ids_file = C.CACHE_DIR / f"images_{size}_ids.txt"
    if cache.exists() and ids_file.exists():
        if ids_file.read_text().split() == list(df.image_id):
            return np.load(cache, mmap_mode="r")
    with ThreadPoolExecutor(max_workers=8) as ex:
        arrs = list(ex.map(lambda p: _load_resized(p, size), df.path))
    bank = np.stack(arrs)
    np.save(cache, bank)
    ids_file.write_text("\n".join(df.image_id))
    return np.load(cache, mmap_mode="r")


def to_device_batch(bank: np.ndarray, idx: np.ndarray, device: torch.device) -> torch.Tensor:
    """Lot uint8 (B,H,W,3) en mémoire → tenseur float (B,3,H,W) dans [0,1] sur le GPU."""
    x = torch.from_numpy(np.ascontiguousarray(bank[idx]))
    if device.type == "cuda":
        x = x.pin_memory().to(device, non_blocking=True)
    return x.permute(0, 3, 1, 2).float().div_(255.0)


_MEAN = torch.tensor(C.IMAGENET_MEAN).view(1, 3, 1, 1)
_STD = torch.tensor(C.IMAGENET_STD).view(1, 3, 1, 1)


def normalize(x: torch.Tensor) -> torch.Tensor:
    """Normalisation ImageNet (les poids pré-entraînés l'attendent)."""
    return (x - _MEAN.to(x.device)) / _STD.to(x.device)


def gpu_augment(x: torch.Tensor, gen: torch.Generator) -> torch.Tensor:
    """Augmentations aléatoires par image, en lot sur GPU (train seulement).

    Une image dermoscopique n'a pas d'orientation privilégiée : on applique des
    retournements, une rotation quelconque, un léger zoom/décalage, et une petite
    variation de luminosité/contraste/saturation (différences d'appareils).
    """
    b, dev = x.shape[0], x.device
    r = lambda *s: torch.rand(*s, generator=gen, device=dev)  # noqa: E731
    # Retournements horizontal et vertical
    x = torch.where((r(b) < 0.5).view(b, 1, 1, 1), x.flip(3), x)
    x = torch.where((r(b) < 0.5).view(b, 1, 1, 1), x.flip(2), x)
    # Rotation (0-360°), zoom (×1 à ×1,25) et translation (±6 %) en une transformation affine
    theta = r(b) * 2 * torch.pi
    zoom = 1.0 / (1.0 + 0.25 * r(b))
    tx, ty = (r(b) - 0.5) * 0.12, (r(b) - 0.5) * 0.12
    cos, sin = torch.cos(theta) * zoom, torch.sin(theta) * zoom
    mat = torch.stack([torch.stack([cos, -sin, tx], 1), torch.stack([sin, cos, ty], 1)], 1)
    grid = F.affine_grid(mat, list(x.shape), align_corners=False)
    x = F.grid_sample(x, grid, mode="bilinear", padding_mode="reflection", align_corners=False)
    # Couleur : luminosité, contraste, saturation (±15 %)
    v = lambda: (1 + (r(b) - 0.5) * 0.3).view(b, 1, 1, 1)  # noqa: E731
    x = x * v()
    mean = x.mean(dim=(1, 2, 3), keepdim=True)
    x = (x - mean) * v() + mean
    gray = (0.299 * x[:, :1] + 0.587 * x[:, 1:2] + 0.114 * x[:, 2:3])
    x = (x - gray) * v() + gray
    return x.clamp_(0, 1)
