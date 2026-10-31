"""Tests du recalibrage local (garanties, garde-fous) et des signaux d'évolution."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from dermia.engine import recalibrage as rc
from dermia.engine import suivi

CLASSES = ["nv", "mel", "bkl", "bcc", "akiec", "vasc", "df"]
MEL = 1


def donnees(n: int, rng, surconfiance: float = 1.0, poids=(0.6, 0.15, 0.1, 0.06, 0.04, 0.03, 0.02)):
    """Modèle calibré (y tiré selon p) ; `surconfiance` > 1 simule un appareil qui rend le modèle trop sûr de lui."""
    vraies = rng.dirichlet(np.ones(7) * 0.35, n)
    vraies = vraies * np.array(poids)[None]
    vraies /= vraies.sum(1, keepdims=True)
    y = np.array([rng.choice(7, p=v) for v in vraies])
    logits = np.log(vraies + 1e-9) * surconfiance
    p = np.exp(logits - logits.max(1, keepdims=True))
    return p / p.sum(1, keepdims=True), y


def origine_depuis(p, y, alpha=0.1):
    q = [rc.quantile_conforme(1 - p[y == k, k], alpha) for k in range(7)]
    return {"conformal_q": q, "thresholds": {"5": 0.2, "10": 0.1, "20": 0.05}}


def test_recalibrage_restaure_la_couverture():
    rng = np.random.default_rng(0)
    origine = origine_depuis(*donnees(6000, rng))
    p_loc, y_loc = donnees(3000, rng, surconfiance=2.5)            # autre appareil : modèle trop confiant
    prop = rc.proposer(p_loc, y_loc, origine, 0.1, [5, 10, 20], 10, MEL, CLASSES)
    r = prop["resume"]
    assert r["origine"]["couverture"] < 0.86                      # les seuils d'origine ne couvrent plus
    vc = r["recalibre_validation_croisee"]
    assert 0.87 <= vc["couverture"] <= 0.95                       # recalibré : ≈ 90 % (estimation non biaisée)
    assert vc["couverture_mel"] >= 0.85
    assert all(s == "locale" for s in prop["parametres"]["sources_q"][:5])
    assert r["recommandation"]["decision"] == "appliquer"


def _resume(o_couv, o_mel, o_sil, v_couv, v_mel, v_sil):
    ev = lambda c, m, s: {"couverture": c, "couverture_mel": m, "taux_traite": 0.6, "mel_manques_en_silence": s}  # noqa: E731
    return {"alpha": 0.1, "origine": ev(o_couv, o_mel, o_sil), "recalibre_validation_croisee": ev(v_couv, v_mel, v_sil)}


def test_recommandation_prudente():
    # sécurité mélanome dégradée par le recalibrage (cas typique sans changement d'appareil) : conserver
    assert rc.recommander(_resume(0.90, 0.97, 1, 0.91, 0.90, 4))["decision"] == "conserver"
    assert rc.recommander(_resume(0.90, 0.95, 1, 0.92, 0.95, 2))["raison"] == "securite_melanome_degradee"
    # gain de sécurité mélanome (appareil différent) : appliquer
    assert rc.recommander(_resume(0.90, 0.85, 6, 0.90, 0.90, 3)) == {"decision": "appliquer",
                                                                     "raison": "gain_securite_melanome"}
    # couverture globale d'origine insuffisante, restaurée sans perte sur le mélanome : appliquer
    assert rc.recommander(_resume(0.82, 0.92, 2, 0.90, 0.92, 2))["raison"] == "couverture_restauree"
    # rien ne change : conserver ; pas d'estimation (trop peu de cas) : conserver
    assert rc.recommander(_resume(0.90, 0.92, 2, 0.90, 0.92, 2))["raison"] == "aucun_gain"
    assert rc.recommander({"alpha": 0.1, "origine": {}})["raison"] == "estimation_indisponible"


def test_gardes_fous_effectifs():
    rng = np.random.default_rng(1)
    origine = origine_depuis(*donnees(4000, rng))
    p, y = donnees(60, rng)                                       # trop peu de cas : on garde l'origine
    prop = rc.proposer(p, y, origine, 0.1, [5, 10, 20], 10, MEL, CLASSES)
    sources = dict(zip(CLASSES, prop["parametres"]["sources_q"]))
    for k, c in enumerate(CLASSES):
        attendu = "locale" if (y == k).sum() >= rc.N_MIN_CLASSE else "origine"
        assert sources[c] == attendu
        if attendu == "origine":
            assert prop["parametres"]["conformal_q"][k] == origine["conformal_q"][k]
    assert prop["parametres"]["source_seuil"] == "origine"
    assert prop["parametres"]["thresholds"] == origine["thresholds"]


def test_quantile_conforme_inf_si_trop_peu():
    assert rc.quantile_conforme(np.array([0.1, 0.2]), 0.1) == float("inf")


def _analyse(i, jours, p, niveau, a=0, b=1, couleurs=("brun_clair",), d=None):
    return {"id": i, "cree_le": datetime(2026, 1, 1) + timedelta(days=jours), "p_melanome": p, "niveau": niveau,
            "abcd": {"A": {"score": a}, "B": {"score": b}, "C": {"couleurs": list(couleurs)}, "D": {"mm": d}}}


def test_evolution_notable():
    r = suivi.comparer(_analyse(1, 0, 0.05, "faible", couleurs=("brun_clair",), d=4.0),
                       _analyse(2, 180, 0.40, "urgent", a=2, b=4, couleurs=("brun_clair", "noir", "bleu_gris"), d=5.5))
    codes = {s["code"] for s in r["signaux"]}
    assert codes == {"p_mel_hausse", "orientation_aggravee", "asymetrie_hausse", "bords_hausse",
                     "nouvelles_couleurs", "diametre_hausse"}
    assert r["notable"] and r["jours"] == 180


def test_lesion_stable():
    r = suivi.comparer(_analyse(1, 0, 0.05, "faible"), _analyse(2, 90, 0.08, "faible"))
    assert r["signaux"] == [] and not r["notable"]
