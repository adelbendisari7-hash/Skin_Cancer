"""Tests des critères ABCD sur des images synthétiques dont la réponse est connue."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from dermia.engine import abcd

PEAU, BRUN, NOIR = (214, 160, 140), (110, 66, 44), (30, 26, 26)


def image_ellipse(angle_deg: float, bosse: bool = False, deux_couleurs: bool = False, taille=(600, 450)) -> Image.Image:
    im = Image.new("RGB", taille, PEAU)
    calque = Image.new("L", taille, 0)
    d = ImageDraw.Draw(calque)
    cx, cy = taille[0] / 2, taille[1] / 2
    d.ellipse([cx - 150, cy - 80, cx + 150, cy + 80], fill=255)
    if bosse:
        d.ellipse([cx + 60, cy - 150, cx + 160, cy - 40], fill=255)       # excroissance d'un seul côté
    calque = calque.rotate(angle_deg, center=(cx, cy))
    im.paste(Image.new("RGB", taille, BRUN), mask=calque)
    if deux_couleurs:
        demi = Image.new("L", taille, 0)
        ImageDraw.Draw(demi).rectangle([0, 0, cx, taille[1]], fill=255)
        im.paste(Image.new("RGB", taille, NOIR), mask=Image.fromarray(np.minimum(np.asarray(calque), np.asarray(demi))))
    return im


@pytest.mark.parametrize("angle", [0, 25, 60, 90, 135])
def test_ellipse_symetrique(angle):
    m = abcd.mesurer(image_ellipse(angle))
    assert m["fiable"]
    assert max(m["A"]["indice_forme"]) < 0.06, m["A"]
    assert m["A"]["score"] == 0


def test_forme_asymetrique():
    m = abcd.mesurer(image_ellipse(30, bosse=True))
    assert max(m["A"]["indice_forme"]) > 0.15
    assert m["A"]["score"] >= 1


def test_couleurs():
    une = abcd.mesurer(image_ellipse(0))
    deux = abcd.mesurer(image_ellipse(0, deux_couleurs=True))
    assert "brun_fonce" in une["C"]["couleurs"] or "brun_clair" in une["C"]["couleurs"]
    assert "noir" in deux["C"]["couleurs"] and deux["C"]["score"] >= 2
    assert deux["A"]["score"] >= 1                     # deux moitiés de couleurs différentes


def test_diametre_avec_echelle():
    m = abcd.mesurer(image_ellipse(0), champ_mm=12.0)  # champ de 12 mm sur 600 px → 0,02 mm/px ; grand axe 300 px
    assert m["D"]["mm"] == pytest.approx(6.0, abs=0.4)
    assert abcd.mesurer(image_ellipse(0))["D"]["mm"] is None


def test_image_sans_lesion():
    m = abcd.mesurer(Image.new("RGB", (400, 300), PEAU))
    assert not m["fiable"] or m["A"] is None


def test_superposition_png():
    im = image_ellipse(40)
    png = abcd.superposition_png(im, abcd.mesurer(im))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
