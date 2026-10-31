"""Étape 9 — interprétation.

- Grad-CAM [Selvaraju et al. 2017] : zones de l'image qui font monter le score d'une classe.
- Paramètres FiLM : comment le contexte patient (localisation, âge) module la lecture de l'image.
- Contrefactuels : même image, contexte modifié → variation de p(mélanome).
- SHAP [Lundberg & Lee 2017] pour M2 (TreeSHAP exact calculé par XGBoost).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import torch

from . import config as C
from .data import ClinicalEncoder, build_image_cache, get_split, normalize, to_device_batch
from .models import SkinNet

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model(exp: str, seed: int, n_clin: int) -> SkinNet:
    """`n_clin` = enc.n_features (dépend des catégories présentes dans le train)."""
    meta = json.loads((C.PRED_DIR / f"{exp}_s{seed}.json").read_text(encoding="utf-8"))
    model = SkinNet(fusion=meta["fusion"], n_clin=n_clin, film=meta.get("film", "multi"), pretrained=False)
    model.load_state_dict(torch.load(C.CKPT_DIR / f"{exp}_s{seed}.pt", map_location="cpu"))
    return model.to(DEVICE).eval()


def context():
    """Données, encodeur clinique et cache d'images partagés par toutes les analyses."""
    df = get_split()
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    clin = torch.from_numpy(enc.transform(df)).to(DEVICE)
    bank = build_image_cache(df)
    return df, enc, clin, bank


def gradcam(model: SkinNet, bank, clin, idx: np.ndarray, target: int) -> np.ndarray:
    """Cartes Grad-CAM (n, 224, 224) dans [0, 1] pour la classe `target`."""
    x = normalize(to_device_batch(bank, idx, DEVICE)).requires_grad_(False)
    z = clin[idx] if model.fusion != "none" else None
    model.zero_grad(set_to_none=True)
    with torch.enable_grad():
        logits = model(x, z, keep_map=True)
        logits[:, target].sum().backward()
    a, g = model.feature_map, model.feature_map.grad
    cam = torch.relu((g.mean(dim=(2, 3), keepdim=True) * a).sum(1, keepdim=True))
    cam = torch.nn.functional.interpolate(cam, size=x.shape[-2:], mode="bilinear", align_corners=False)[:, 0]
    cam = cam - cam.amin(dim=(1, 2), keepdim=True)
    cam = cam / cam.amax(dim=(1, 2), keepdim=True).clamp_min(1e-8)
    return cam.detach().cpu().numpy()


@torch.no_grad()
def film_by_value(model: SkinNet, enc: ClinicalEncoder, df: pd.DataFrame, stage: int = 8) -> dict:
    """γ et β moyens par localisation et par âge, pour le contexte réel des patients du test."""
    test = df[df.split == "test"]
    out = {}
    z = torch.from_numpy(enc.transform(test)).to(DEVICE)
    gamma, beta = model.film_params(z)[stage]
    gamma, beta = gamma.cpu().numpy(), beta.cpu().numpy()
    out["gamma"], out["beta"], out["loc"] = gamma, beta, test.localization.to_numpy()
    out["age"] = test.age.to_numpy()
    return out


@torch.no_grad()
def counterfactual_pmel(model: SkinNet, enc: ClinicalEncoder, bank, df: pd.DataFrame, idx: np.ndarray,
                        column: str, values: list, batch: int = 128) -> pd.DataFrame:
    """p(mélanome) moyen des images `idx` quand on remplace `column` par chaque valeur (le reste inchangé)."""
    rows = []
    sub = df.iloc[idx].copy()
    for v in values:
        sub_v = sub.copy()
        sub_v[column] = v
        z = torch.from_numpy(enc.transform(sub_v)).to(DEVICE)
        p = []
        for s in range(0, len(idx), batch):          # un lot à la fois sur le GPU (4 Go)
            x = normalize(to_device_batch(bank, idx[s:s + batch], DEVICE))
            zz = z[s:s + batch]
            with torch.autocast(device_type=DEVICE.type, dtype=torch.float16, enabled=DEVICE.type == "cuda"):
                logits = model(x, zz)
            p.append(torch.softmax(logits.float(), 1)[:, C.MEL].cpu().numpy())
        rows.append({column: v, "p(mel) moyen": float(np.concatenate(p).mean())})
    return pd.DataFrame(rows)
