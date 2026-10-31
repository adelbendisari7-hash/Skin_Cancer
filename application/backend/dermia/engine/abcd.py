"""Critères ABCD(E) assistés : estimation automatique, à interpréter par le médecin.

Pipeline (méthodes classiques, sans apprentissage) :
1. image ramenée à 320 px (côté long) ; exclusion du cadre noir du dermoscope ;
2. suppression des poils (« black-hat » morphologique, esprit DullRazor) ;
3. constance des couleurs « shades of gray » (Finlayson & Trezzi, 2004) ;
4. segmentation : seuil d'Otsu sur la luminance L*, nettoyage morphologique, composante la plus centrale ;
5. A — asymétrie de forme (recouvrement du masque et de son miroir selon chaque axe principal)
       et de couleur (écart ΔE entre les deux moitiés) ;
   B — nombre de secteurs (sur 8) où le bord est abrupt (gradient de L* au bord / contraste lésion-peau) ;
   C — couleurs dermoscopiques présentes parmi 6 (blanc, rouge, brun clair, brun foncé, bleu-gris, noir) ;
   D — plus grand diamètre en mm, seulement si la largeur du champ du dermoscope est connue.
Les seuils (A, B) sont fixés sur le jeu de VALIDATION HAM10000 (fichier seuils_abcd.json).
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage as ndi
from skimage import color, filters, measure, morphology

TAILLE = 320
SEUILS_DEFAUT = {"forme": 0.12, "couleur": 8.0, "abrupt": 0.9, "part_couleur": 0.04}
_FICHIER_SEUILS = Path(__file__).with_name("seuils_abcd.json")

# Centres Lab des 6 couleurs dermoscopiques + « peau » (absorbe la peau incluse dans le contour, non comptée)
COULEURS = {
    "blanc": (88.0, 0.0, 6.0),
    "rouge": (45.0, 45.0, 25.0),
    "brun_clair": (55.0, 18.0, 32.0),
    "brun_fonce": (30.0, 15.0, 18.0),
    "bleu_gris": (45.0, -2.0, -10.0),
    "noir": (12.0, 2.0, 2.0),
}
_PEAU = (68.0, 20.0, 18.0)
NB_SECTEURS = 8


def seuils() -> dict:
    if _FICHIER_SEUILS.exists():
        return {**SEUILS_DEFAUT, **json.loads(_FICHIER_SEUILS.read_text(encoding="utf-8"))}
    return dict(SEUILS_DEFAUT)


def _preparer(image: Image.Image) -> np.ndarray:
    im = ImageOps.exif_transpose(image).convert("RGB")
    e = TAILLE / max(im.size)
    im = im.resize((max(1, round(im.width * e)), max(1, round(im.height * e))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64) / 255.0


def _morpho(op, masque: np.ndarray, rayon: int) -> np.ndarray:
    """Ouverture / fermeture avec bords prolongés (sinon les lésions qui touchent le cadre sont rognées)."""
    m = np.pad(masque, rayon + 1, mode="edge")
    return op(m, structure=morphology.disk(rayon))[rayon + 1:-rayon - 1, rayon + 1:-rayon - 1]


def _champ_valide(gris: np.ndarray) -> np.ndarray:
    """Exclut le cadre noir (vignettage du dermoscope) : zones très sombres reliées au bord de l'image."""
    sombre = gris < 0.12
    lab, n = ndi.label(sombre)
    bord = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    cadre = np.isin(lab, bord[bord > 0])
    return ~ndi.binary_dilation(cadre, iterations=3)


def _sans_poils(rgb: np.ndarray, gris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Détecte les poils (structures fines et sombres) et les remplace par leur voisinage (fermeture)."""
    pied = morphology.disk(4)
    black_hat = morphology.closing(gris, pied) - gris
    poils = ndi.binary_dilation(black_hat > 0.07, structure=morphology.disk(1))
    propre = rgb.copy()
    for k in range(3):
        ferme = morphology.closing(rgb[..., k], pied)
        propre[..., k] = np.where(poils, ferme, rgb[..., k])
    return propre, poils


def _shades_of_gray(rgb: np.ndarray, masque: np.ndarray, p: int = 6) -> np.ndarray:
    pix = rgb[masque] if masque.any() else rgb.reshape(-1, 3)
    norme = np.power(np.mean(np.power(pix, p), axis=0), 1.0 / p)
    gain = norme.mean() / np.maximum(norme, 1e-6)
    return np.clip(rgb * gain, 0, 1)


def segmenter(image: Image.Image) -> dict:
    """Masque de la lésion et images intermédiaires (au format de travail)."""
    rgb = _preparer(image)
    gris = rgb.mean(axis=2)
    valide = _champ_valide(gris)
    rgb, poils = _sans_poils(rgb, gris)
    rgb = _shades_of_gray(rgb, valide)
    lab = color.rgb2lab(rgb)
    L = filters.gaussian(lab[..., 0], sigma=2)
    vals = L[valide]
    if vals.size < 100:
        return {"rgb": rgb, "lab": lab, "valide": valide, "masque": np.zeros_like(valide), "poils": poils}
    seuil = filters.threshold_otsu(vals)
    masque = (L < seuil) & valide
    masque = _morpho(ndi.binary_opening, masque, 3)
    masque = _morpho(ndi.binary_closing, masque, 5)
    masque = ndi.binary_fill_holes(masque)
    etiq = measure.label(masque)
    regions = [r for r in measure.regionprops(etiq) if r.area >= 0.005 * valide.sum()]
    if not regions:
        return {"rgb": rgb, "lab": lab, "valide": valide, "masque": np.zeros_like(valide), "poils": poils}
    h, w = masque.shape
    centre = np.array([h / 2, w / 2])
    # composante la plus proche du centre, pondérée par sa taille
    meilleure = max(regions, key=lambda r: r.area / (1 + np.linalg.norm(np.array(r.centroid) - centre) / (0.15 * max(h, w))))
    return {"rgb": rgb, "lab": lab, "valide": valide, "masque": etiq == meilleure.label, "poils": poils}


def _miroir(masque: np.ndarray, centre: np.ndarray, angle: float, axe: str) -> np.ndarray:
    """Reflète le masque par rapport à l'axe principal (« majeur ») ou secondaire (« mineur »)."""
    r, c = np.nonzero(masque)
    y, x = r - centre[0], c - centre[1]
    cos, sin = np.cos(angle), np.sin(angle)
    u, v = x * cos + y * sin, -x * sin + y * cos          # repère des axes principaux
    if axe == "majeur":
        v = -v
    else:
        u = -u
    x2, y2 = u * cos - v * sin, u * sin + v * cos
    rr, cc = np.round(y2 + centre[0]).astype(int), np.round(x2 + centre[1]).astype(int)
    ok = (rr >= 0) & (rr < masque.shape[0]) & (cc >= 0) & (cc < masque.shape[1])
    out = np.zeros_like(masque)
    out[rr[ok], cc[ok]] = True
    return ndi.binary_closing(out, iterations=1)


def mesurer(image: Image.Image, champ_mm: float | None = None) -> dict:
    """Calcule les critères A, B, C, D. `champ_mm` : largeur du champ du dermoscope (mm), facultative."""
    s = seuils()
    seg = segmenter(image)
    masque, valide, lab = seg["masque"], seg["valide"], seg["lab"]
    alertes = []
    aire, aire_valide = int(masque.sum()), int(valide.sum())
    if aire == 0:
        return {"fiable": False, "alertes": ["segmentation_impossible"], "A": None, "B": None, "C": None, "D": None,
                "surface_relative": 0.0}
    part = aire / max(aire_valide, 1)
    bord_image = masque[0].any() or masque[-1].any() or masque[:, 0].any() or masque[:, -1].any()
    if part > 0.85 or bord_image:
        alertes.append("lesion_coupee")                 # la lésion dépasse du champ : A, B, D moins fiables
    if part < 0.01:
        alertes.append("lesion_tres_petite")

    props = measure.regionprops(masque.astype(np.uint8))[0]
    centre = np.array(props.centroid)
    # orientation skimage : angle entre l'axe des lignes et l'axe majeur → angle dans le repère (x, y)
    angle = np.pi / 2 - props.orientation

    # ---- A : asymétrie de forme et de couleur selon chaque axe
    forme, couleur, asym = [], [], []
    r, c = np.nonzero(masque)
    y, x = r - centre[0], c - centre[1]
    for i, axe in enumerate(("majeur", "mineur")):
        miroir = _miroir(masque, centre, angle, axe)
        indice = 1.0 - (masque & miroir).sum() / aire
        u = x * np.cos(angle) + y * np.sin(angle)
        v = -x * np.sin(angle) + y * np.cos(angle)
        cote = v > 0 if axe == "majeur" else u > 0
        m1, m2 = lab[r[cote], c[cote]], lab[r[~cote], c[~cote]]
        de = float(np.linalg.norm(m1.mean(0) - m2.mean(0))) if len(m1) and len(m2) else 0.0
        forme.append(round(float(indice), 4)); couleur.append(round(de, 2))
        asym.append(bool(indice > s["forme"] or de > s["couleur"]))

    # ---- B : bords abrupts par secteur (gradient de L* au bord / contraste lésion-peau)
    L = filters.gaussian(lab[..., 0], sigma=1.5)
    gy, gx = np.gradient(L)
    grad = np.hypot(gx, gy)
    contour = masque & ~ndi.binary_erosion(masque)
    peau = valide & ~ndi.binary_dilation(masque, iterations=6)
    contraste = max(float(L[peau].mean() - L[masque].mean()) if peau.any() else 1.0, 1.0)
    rb, cb = np.nonzero(contour)
    secteurs = (np.floor((np.arctan2(rb - centre[0], cb - centre[1]) + np.pi) / (2 * np.pi) * NB_SECTEURS)
                .astype(int) % NB_SECTEURS)
    abrupt, intensites = [], []
    for k in range(NB_SECTEURS):
        sel = secteurs == k
        val = float(grad[rb[sel], cb[sel]].mean() * 6 / contraste) if sel.any() else 0.0  # ≈ largeur de transition
        intensites.append(round(val, 3)); abrupt.append(bool(val > s["abrupt"]))
    perimetre = props.perimeter
    irregularite = float(perimetre ** 2 / (4 * np.pi * aire))

    # ---- C : couleurs dermoscopiques (pixels de la lésion hors poils)
    pix = lab[masque & ~seg["poils"]]
    refs = np.array(list(COULEURS.values()) + [_PEAU])
    nearest = np.argmin(((pix[:, None, :] - refs[None]) ** 2).sum(-1), axis=1)
    fractions = {nom: round(float((nearest == i).mean()), 4) for i, nom in enumerate(COULEURS)}
    presentes = [nom for nom, f in fractions.items() if f >= s["part_couleur"]]

    # ---- D : diamètre (nécessite l'échelle)
    d_mm = None
    if champ_mm:
        mm_par_px = champ_mm / masque.shape[1]
        d_mm = round(float(props.feret_diameter_max * mm_par_px), 1)

    return {
        "fiable": "lesion_coupee" not in alertes,
        "alertes": alertes,
        "surface_relative": round(part, 4),
        "A": {"score": int(sum(asym)), "indice_forme": forme, "ecart_couleur": couleur, "axes_asymetriques": asym},
        "B": {"score": int(sum(abrupt)), "secteurs_abrupts": abrupt, "intensites": intensites,
              "irregularite": round(irregularite, 3)},
        "C": {"score": max(len(presentes), 1), "couleurs": presentes, "fractions": fractions},
        "D": {"mm": d_mm, "superieur_6mm": None if d_mm is None else d_mm > 6.0},
        "_geom": {"centre": centre.tolist(), "angle": float(angle), "majeur": float(props.axis_major_length),
                  "mineur": float(props.axis_minor_length), "masque": masque, "forme": masque.shape},
    }


def superposition_png(image: Image.Image, mesure: dict, cote_max: int = 640) -> bytes:
    """Image d'origine avec le contour de la lésion et ses deux axes principaux."""
    im = ImageOps.exif_transpose(image).convert("RGB")
    e = min(1.0, cote_max / max(im.size))
    im = im.resize((max(1, round(im.width * e)), max(1, round(im.height * e))), Image.LANCZOS)
    g = mesure.get("_geom")
    if not g:
        buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()
    h0, w0 = g["forme"]
    fy, fx = im.height / h0, im.width / w0
    masque = g["masque"]
    contour = masque & ~ndi.binary_erosion(masque, iterations=2)
    arr = np.asarray(im).copy()
    cr = np.asarray(Image.fromarray(contour.astype(np.uint8) * 255).resize(im.size, Image.NEAREST)) > 0
    cr = ndi.binary_dilation(cr, iterations=1)
    arr[cr] = (255, 255, 255)
    out = Image.fromarray(arr)
    d = ImageDraw.Draw(out)
    cy, cx = g["centre"][0] * fy, g["centre"][1] * fx
    for longueur, ang in ((g["majeur"], g["angle"]), (g["mineur"], g["angle"] + np.pi / 2)):
        dx, dy = np.cos(ang) * longueur / 2 * fx, np.sin(ang) * longueur / 2 * fy
        d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=(14, 106, 100), width=3)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def publiable(mesure: dict) -> dict:
    """Version enregistrable / sérialisable (sans le masque)."""
    return {k: v for k, v in mesure.items() if k != "_geom"}
