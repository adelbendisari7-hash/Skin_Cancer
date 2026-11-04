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
DOSSIERS = {"HAM10000": Path(os.environ.get("HAM_DIR", ICI.parents[2] / "HAM10000")),
            "BCN20000": Path(os.environ.get("BCN_DIR", ICI.parents[2] / "BCN20000"))}
REF = json.loads((ICI / "reference_v3.json").read_text(encoding="utf-8"))["cas"]


@pytest.fixture(scope="session")
def moteur() -> Moteur:
    return Moteur(BUNDLE_DIR, device=DEVICE)


@pytest.mark.parametrize("cas", REF, ids=[c["image_id"] for c in REF])
def test_non_regression(moteur: Moteur, cas: dict):
    """Les probabilités de l'application = celles du rapport (même pipeline, recadrage et zones compris).

    Référence calculée en demi-précision sur GPU : tolérance 2·10⁻³ sur GPU, 10⁻² sur processeur (float32).
    """
    dossier = DOSSIERS[cas["source"]]
    if not dossier.exists():
        pytest.skip(f"images {cas['source']} absentes ({dossier})")
    image = Image.open(dossier / cas["fichier"])
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


def test_localisation_detaillee_ramenee_a_sa_zone(moteur: Moteur):
    """L'interface envoie la localisation détaillée ; le réseau v3 voit la zone commune (dos → tronc)."""
    assert moteur.zone("back") == moteur.zone("chest") == "tronc" and moteur.zone("tronc") == "tronc"
    assert moteur.zone("n'importe quoi") == "unknown"
    z1 = moteur.encoder_contexte(Contexte(55, "male", "back"))
    z2 = moteur.encoder_contexte(Contexte(55, "male", "tronc"))
    assert (z1 == z2).all()


def test_recadrage_du_champ_du_dermoscope(moteur: Moteur):
    """Coins noirs autour d'un disque clair → seule la partie utile est analysée ; image normale → entière."""
    from PIL import ImageDraw
    im = Image.new("RGB", (800, 600), (0, 0, 0))
    ImageDraw.Draw(im).ellipse([130, 30, 670, 570], fill=(200, 150, 140))
    x0, y0, x1, y1 = moteur.cadre(im)
    assert 130 < x0 < 400 < x1 < 670 and 30 < y0 < 300 < y1 < 570
    assert moteur.cadre(Image.new("RGB", (600, 450), (190, 140, 130))) is None
