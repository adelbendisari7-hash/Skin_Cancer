"""Architecture du réseau (identique à projet/src/models.py, dont elle est une copie autonome).

L'application ne dépend pas du code de recherche : seule cette définition et le paquet de modèle
(poids + manifest) sont nécessaires. Le test de non-régression vérifie l'équivalence.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import efficientnet_b0, efficientnet_b2

FILM_PRESETS = {"final": (8,), "multi": (6, 7, 8)}
TRONCS = {"efficientnet_b0": efficientnet_b0, "efficientnet_b2": efficientnet_b2}


def canaux_par_etage(features: nn.Sequential) -> list[int]:
    """Canaux de sortie de chaque bloc, lus dans la structure (dernière convolution du bloc)."""
    return [[m for m in blk.modules() if isinstance(m, nn.Conv2d)][-1].out_channels for blk in features]


class ClinicalMLP(nn.Module):
    def __init__(self, n_in: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(hidden, hidden), nn.ReLU())

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z)


class SkinNet(nn.Module):
    """EfficientNet-B0 + fusion du contexte clinique ("none", "concat" ou "film")."""

    def __init__(self, fusion: str, n_clin: int, film: str = "final", n_classes: int = 7,
                 clin_hidden: int = 64, backbone: str = "efficientnet_b0"):
        super().__init__()
        self.features = TRONCS[backbone](weights=None).features
        self.canaux = canaux_par_etage(self.features)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fusion = fusion
        head_in = self.canaux[-1]
        if fusion != "none":
            self.clin = ClinicalMLP(n_clin, clin_hidden)
        if fusion == "concat":
            head_in += clin_hidden
        self.film_stages = FILM_PRESETS[film] if fusion == "film" else ()
        if fusion == "film":
            self.film = nn.ModuleDict({str(s): nn.Linear(clin_hidden, 2 * self.canaux[s])
                                       for s in self.film_stages})
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(head_in, n_classes))
        self.feature_map: torch.Tensor | None = None

    def film_params(self, z: torch.Tensor) -> dict[int, tuple[torch.Tensor, torch.Tensor]]:
        c = self.clin(z)
        return {s: tuple(self.film[str(s)](c).chunk(2, dim=1)) for s in self.film_stages}

    def caracteristiques(self, x: torch.Tensor, etages: tuple[int, ...] | None = None):
        """Caractéristiques de l'image seule (avant modulation FiLM) : sert à repérer les images hors sujet.

        Sans `etages` : moyenne spatiale de la dernière étape (N, C). Avec `etages` : liste des moyennes
        spatiales des étapes demandées (une matrice (N, C_e) par étape), en un seul passage.
        """
        sorties = []
        for i, block in enumerate(self.features):
            x = block(x)
            if etages is not None and i in etages:
                sorties.append(self.pool(x).flatten(1))
        return sorties if etages is not None else self.pool(x).flatten(1)

    def forward(self, x: torch.Tensor, z: torch.Tensor | None = None, keep_map: bool = False) -> torch.Tensor:
        film = self.film_params(z) if self.fusion == "film" else {}
        for i, block in enumerate(self.features):
            x = block(x)
            if i in film:
                gamma, beta = film[i]
                x = x * (1 + gamma[:, :, None, None]) + beta[:, :, None, None]
        if keep_map:
            x.retain_grad()
            self.feature_map = x
        h = self.pool(x).flatten(1)
        if self.fusion == "concat":
            h = torch.cat([h, self.clin(z)], dim=1)
        return self.head(h)
