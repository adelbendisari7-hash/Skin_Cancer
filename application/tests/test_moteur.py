"""Tests du moteur d'IA : non-régression par rapport au modèle du rapport, intégrité, Grad-CAM."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dermia.config import BUNDLE_DIR, DEVICE
from dermia.engine import BundleError, Contexte, Moteur

ICI = Path(__file__).parent
HAM_DIR = Path(os.environ.get("HAM_DIR", ICI.parents[2] / "HAM10000"))
REF = json.loads((ICI / "reference_ham10000.json").read_text(encoding="utf-8"))["cas"]


@pytest.fixture(scope="session")
def moteur() -> Moteur:
    return Moteur(BUNDLE_DIR, device=DEVICE)


@pytest.mark.skipif(not HAM_DIR.exists(), reason="images HAM10000 absentes (variable HAM_DIR)")
@pytest.mark.parametrize("cas", REF, ids=[c["image_id"] for c in REF])
def test_non_regression(moteur: Moteur, cas: dict):
    """Les probabilités de l'application = celles du rapport (même pipeline).

    Référence calculée en demi-précision sur GPU : tolérance 2·10⁻³ sur GPU, 10⁻² sur processeur (float32).
    """
    image = Image.open(HAM_DIR / cas["fichier"])
    ctx = Contexte(cas["age"], cas["sexe"], cas["localisation"])
    res, _ = moteur.analyser(image, ctx)
    assert res.profil == cas["profil"]
    obtenu = np.array([res.probabilites[c] for c in moteur.classes])
    attendu = np.array(cas["probabilites"])
    tol = 2e-3 if moteur.device.type == "cuda" else 1e-2
    assert np.abs(obtenu - attendu).max() < tol, (obtenu.round(4), attendu.round(4))
    assert abs(sum(res.probabilites.values()) - 1) < 1e-4


def test_empreinte_alteree(tmp_path: Path):
    """Un fichier de poids modifié doit être refusé (intégrité du dispositif)."""
    copie = tmp_path / "paquet"
    shutil.copytree(BUNDLE_DIR, copie)
    m = json.loads((copie / "manifest.json").read_text(encoding="utf-8"))
    m["profils"]["complet"]["poids"][0]["sha256"] = "0" * 64
    (copie / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(BundleError):
        Moteur(copie)


def test_contexte_incomplet_bascule_sur_profil_robuste(moteur: Moteur):
    image = Image.new("RGB", (600, 450), (180, 120, 110))
    res, _ = moteur.analyser(image, Contexte(age=None, sexe="female", localisation="back"))
    assert res.profil == "sans_contexte" and res.avertissements


def test_gradcam_et_et_si(moteur: Moteur):
    image = Image.new("RGB", (600, 450), (180, 120, 110))
    ctx = Contexte(55, "male", "back")
    res, x = moteur.analyser(image, ctx)
    cam = moteur.gradcam(x, ctx, res.decision)
    assert cam.shape == (moteur.taille, moteur.taille) and 0 <= cam.min() and cam.max() <= 1
    assert moteur.gradcam_png(image, cam)[:8] == b"\x89PNG\r\n\x1a\n"
    serie = moteur.et_si(image, ctx, "age", [20, 40, 60])
    assert [s["valeur"] for s in serie] == [20, 40, 60]
    assert all(0 <= s["p_melanome"] <= 1 for s in serie)


def test_rapport_cout_non_calibre(moteur: Moteur):
    with pytest.raises(ValueError):
        moteur.analyser(Image.new("RGB", (300, 300)), Contexte(50, "male", "back"), rapport_cout=7)
