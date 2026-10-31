"""Traductions des messages de l'API et compte rendu PDF trilingue (sans moteur d'IA)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image
from reportlab.pdfbase.ttfonts import TTFont

from dermia import i18n, pdf

SOURCES = Path(i18n.__file__).parent
MOTIFS = [r'HTTPException\(\s*(?:status\.\w+|\d+)\s*,\s*"([^"{]+)"', r'SauvegardeInvalide\("([^"{]+)"\)',
          r'\{"detail": (?:traduire\()?"([^"]+)"', r'"message": "([^"]+)"', r'traduire\("([^"]+)"']


def messages_du_code() -> set[str]:
    trouves = set()
    for f in SOURCES.rglob("*.py"):
        if f.name == "i18n.py":
            continue
        s = f.read_text(encoding="utf-8")
        for motif in MOTIFS:
            trouves |= set(re.findall(motif, s))
    return trouves


def test_tous_les_messages_sont_traduits():
    msgs = messages_du_code()
    assert len(msgs) > 40
    manquants = [m for m in msgs if i18n.traduire(m, "en") == m or i18n.traduire(m, "ar") == m]
    assert not manquants, manquants


def test_messages_variables_et_details():
    assert i18n.traduire("Rapport de coût non calibré pour ce modèle (disponibles : [5, 10]).", "en") == \
        "Cost ratio not calibrated for this model (available: [5, 10])."
    assert i18n.traduire("Moteur d'IA indisponible : chargement en cours", "ar").startswith("محرك")
    assert i18n.traduire("Message inconnu.", "en") == "Message inconnu."
    d = i18n.traduire_detail({"code": "image_hors_sujet", "message": "Cette image ne ressemble pas à une image "
                              "dermoscopique.", "score": 3.0}, "en")
    assert d == {"code": "image_hors_sujet", "message": "This image does not look like a dermoscopic image.",
                 "score": 3.0}
    assert i18n.traduire_detail([{"loc": ["body"], "msg": "x"}], "en") == [{"loc": ["body"], "msg": "x"}]


def _textes_pdf() -> list[str]:
    out = [s for v in pdf.T.values() for s in v]
    for table in (pdf.LOCALISATIONS, pdf.SEXES, pdf.COULEURS_ABCD):
        out += [s for v in table.values() for s in v]
    out += [s for v in pdf.NOMS_CLASSES.values() for s in v] + list(pdf.STATUT_V1)
    return out


def test_police_couvre_tous_les_caracteres():
    import arabic_reshaper
    cmap = TTFont("verif", str(pdf.POLICES / "IBMPlexSansArabic-Regular.ttf")).face.charToGlyph
    absents = {c for s in _textes_pdf() for c in arabic_reshaper.reshape(s) if not c.isspace() and ord(c) not in cmap}
    assert not absents, sorted(absents)


@pytest.mark.parametrize("texte, attendu", [
    ("(عدد الأيام: 92)", "(92 :ﻡﺎﻳﻷﺍ ﺩﺪﻋ)"),                                 # parenthèses arabes en miroir
    ("بيانات: HAM10000 (Tschandl, 2018) — نص", "ﺺﻧ — HAM10000 (Tschandl, 2018) :ﺕﺎﻧﺎﻴﺑ"),  # passage latin intact
    ("إذا كان p(mel) ≥ 0,21", "p(mel) ≥ 0,21 ﻥﺎﻛ ﺍﺫﺇ"),
])
def test_affichage_droite_a_gauche(texte, attendu):
    assert pdf._affichage_rtl(texte) == attendu


@pytest.fixture(scope="module")
def analyse_factice(tmp_path_factory):
    d = tmp_path_factory.mktemp("cr")
    Image.new("RGB", (600, 450), (180, 120, 110)).save(d / "image.png")
    Image.new("RGB", (288, 288), (90, 40, 40)).save(d / "gradcam.png")
    Image.new("RGB", (600, 450), (200, 200, 200)).save(d / "abcd.png")
    maint = datetime.now(timezone.utc)
    a = NS(patient=NS(code="P-2026-0042"), cree_le=maint, age=57.0, sexe="female", localisation="back",
           auteur=NS(nom_complet="Dr A"), modele="ham10000-m5", version_modele="2.0.0", profil="complet",
           lesion=NS(numero=2, nom=None), calibration="locale:3", niveau="urgent", statut="alerte_melanome",
           titre="t", message="m", decision="mel",
           probabilites={"mel": 0.46, "nv": 0.41, "bkl": 0.08, "bcc": 0.02, "akiec": 0.015, "vasc": 0.01, "df": 0.005},
           ensemble_conforme=["mel", "nv"], seuil_melanome=0.21, rapport_cout=10,
           avertissements=[{"code": "faible_resolution", "largeur": 140, "hauteur": 120}, {"code": "image_atypique"},
                           {"code": "evolution", "depuis": "x"}, {"code": "texte", "texte": "Ancien message."}],
           abcd={"fiable": False, "alertes": ["lesion_coupee"], "A": {"score": 1}, "B": {"score": 3},
                 "C": {"score": 2, "couleurs": ["brun_fonce", "noir"]}, "D": {"mm": 6.4, "superieur_6mm": True}},
           evolution={"analyse_precedente": 1, "depuis": (maint - timedelta(days=92)).isoformat(), "jours": 92,
                      "delta_p_melanome": 0.21, "notable": True,
                      "signaux": [{"code": "p_mel_hausse", "de": 0.25, "a": 0.46},
                                  {"code": "orientation_aggravee", "de": "renvoi", "a": "urgent"},
                                  {"code": "asymetrie_hausse", "de": 0, "a": 1},
                                  {"code": "bords_hausse", "de": 1, "a": 3},
                                  {"code": "nouvelles_couleurs", "couleurs": ["noir"]},
                                  {"code": "diametre_hausse", "de": 5.1, "a": 6.4}]},
           revue="corrigee", revue_le=maint, relecteur=NS(nom_complet="Pr B"), diagnostic_final="mel",
           histologie=True, commentaire="Exérèse programmée.")
    manifest = {"noms_classes": {"mel": "Mélanome", "nv": "Nævus mélanocytaire", "bkl": "Kératose bénigne",
                                 "bcc": "Carcinome basocellulaire", "akiec": "Kératose actinique / Bowen",
                                 "vasc": "Lésion vasculaire", "df": "Dermatofibrome"},
                "abstention": {"alpha": 0.1}, "statut": pdf.STATUT_V1[0],
                "donnees_entrainement": {"jeu": "HAM10000", "licence": "CC BY-NC 4.0 (Attribution - Pas d'utilisation "
                                                                       "commerciale)"}}
    return a, d, manifest


@pytest.mark.parametrize("langue", ["fr", "en", "ar"])
def test_compte_rendu_trois_langues(analyse_factice, langue):
    a, d, manifest = analyse_factice
    contenu = pdf.compte_rendu_pdf(a, "Clinique", d / "image.png", d / "gradcam.png", d / "abcd.png", manifest, langue)
    assert contenu[:4] == b"%PDF" and len(contenu) > 5000


def test_compte_rendu_analyse_v1(analyse_factice):
    """Analyse antérieure à la v2 : ni ABCD, ni lésion, ni évolution, avertissements en texte libre."""
    a, d, manifest = analyse_factice
    ancien = NS(**{**vars(a), "abcd": None, "evolution": None, "lesion": None, "calibration": None,
                   "avertissements": [{"code": "texte", "texte": "Contexte incomplet."}], "revue": "en_attente",
                   "revue_le": None, "relecteur": None, "diagnostic_final": None, "histologie": False})
    contenu = pdf.compte_rendu_pdf(ancien, "", d / "image.png", d / "gradcam.png", None, manifest, "ar")
    assert contenu[:4] == b"%PDF"
