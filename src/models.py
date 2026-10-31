"""Réseaux image / multimodaux construits sur EfficientNet-B0 pré-entraîné (ImageNet).

`SkinNet(fusion=...)` couvre trois modèles avec le même tronc et la même tête :
- "none"   → M1 : image seule ;
- "concat" → M3 : fusion précoce, [caractéristiques image ; encodage clinique] → tête ;
- "film"   → M5 : fusion guidée par le patient. Un MLP clinique produit, pour chaque canal,
             un gain γ et un décalage β : h ← (1 + γ) ⊙ h + β (FiLM, Perez et al. 2018).
             Le contexte change ainsi *la façon de lire l'image* au lieu d'ajouter un simple
             biais à la décision. La modulation peut être appliquée à plusieurs étages du CNN.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import EfficientNet_B0_Weights, EfficientNet_B2_Weights, efficientnet_b0, efficientnet_b2

from . import config as C

# Nombre de canaux en sortie de chaque bloc de `efficientnet_b0().features`
STAGE_CHANNELS = [32, 16, 24, 40, 80, 112, 192, 320, 1280]
TRONCS = {"efficientnet_b0": (efficientnet_b0, EfficientNet_B0_Weights.IMAGENET1K_V1),
          "efficientnet_b2": (efficientnet_b2, EfficientNet_B2_Weights.IMAGENET1K_V1)}


def canaux_par_etage(features: nn.Sequential) -> list[int]:
    """Canaux de sortie de chaque bloc, lus dans la structure (dernière convolution du bloc)."""
    return [[m for m in blk.modules() if isinstance(m, nn.Conv2d)][-1].out_channels for blk in features]
FILM_PRESETS = {
    "final": (8,),          # caractéristiques finales (1280 canaux) uniquement
    "multi": (6, 7, 8),     # étages profonds 192, 320 et 1280 canaux
}


class ClinicalMLP(nn.Module):
    """Encode les 20 variables cliniques en un vecteur de contexte."""

    def __init__(self, n_in: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(hidden, hidden), nn.ReLU())

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z)


class SkinNet(nn.Module):
    def __init__(self, fusion: str = "none", n_clin: int = 20, film: str = "multi",
                 clin_hidden: int = 64, dropout: float = 0.3, pretrained: bool = True,
                 backbone: str = "efficientnet_b0"):
        super().__init__()
        assert fusion in ("none", "concat", "film")
        constructeur, poids = TRONCS[backbone]
        self.features = constructeur(weights=poids if pretrained else None).features
        self.canaux = canaux_par_etage(self.features)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fusion = fusion
        head_in = self.canaux[-1]
        if fusion != "none":
            self.clin = ClinicalMLP(n_clin, clin_hidden)
        if fusion == "concat":
            head_in += clin_hidden
        if fusion == "film":
            self.film_stages = FILM_PRESETS[film]
            # Un générateur linéaire (γ, β) par étage modulé, initialisé à zéro :
            # au départ γ = β = 0, donc le réseau est exactement le CNN pré-entraîné.
            self.film = nn.ModuleDict()
            for s in self.film_stages:
                gen = nn.Linear(clin_hidden, 2 * self.canaux[s])
                nn.init.zeros_(gen.weight); nn.init.zeros_(gen.bias)
                self.film[str(s)] = gen
        else:
            self.film_stages = ()
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(head_in, C.N_CLASSES))
        self.feature_map = None      # carte de la dernière couche (pour Grad-CAM)

    def film_params(self, z: torch.Tensor) -> dict[int, tuple[torch.Tensor, torch.Tensor]]:
        """γ et β de chaque étage pour un lot de contextes cliniques (analyse étape 9)."""
        c = self.clin(z)
        out = {}
        for s in self.film_stages:
            gamma, beta = self.film[str(s)](c).chunk(2, dim=1)
            out[s] = (gamma, beta)
        return out

    def forward(self, x: torch.Tensor, z: torch.Tensor | None = None,
                keep_map: bool = False) -> torch.Tensor:
        film = self.film_params(z) if self.fusion == "film" else {}
        for i, block in enumerate(self.features):
            x = block(x)
            if i in film:
                gamma, beta = film[i]
                x = x * (1 + gamma[:, :, None, None]) + beta[:, :, None, None]
        if keep_map:                 # Grad-CAM : on garde la carte (après modulation)
            x.retain_grad()
            self.feature_map = x
        h = self.pool(x).flatten(1)
        if self.fusion == "concat":
            h = torch.cat([h, self.clin(z)], dim=1)
        return self.head(h)

    def param_groups(self, lr_backbone: float, lr_head: float) -> list[dict]:
        """Taux d'apprentissage plus faible pour le tronc pré-entraîné que pour les parties neuves."""
        backbone = list(self.features.parameters())
        ids = {id(p) for p in backbone}
        rest = [p for p in self.parameters() if id(p) not in ids]
        return [{"params": backbone, "lr": lr_backbone}, {"params": rest, "lr": lr_head}]
