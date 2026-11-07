"""Recalibrage local de l'application testé dans un nouvel hôpital (HIBA), selon application/docs/plan_hiba.md.

Moitiés par patient : paramètres recalibrés sur une moitié par le code de l'application (recalibrage.proposer), profil
par profil, puis appliqués à l'autre moitié, et inversement. Chaque image est mesurée une fois, avec des paramètres
qui ne l'ont pas vue ; comparaison avec les paramètres d'origine sur les mêmes images.

Usage : python -m src.recalibrage_hiba   (après python -m src.evaluer_hiba)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C
from .evaluer_hiba import PAQUETS, charger_hiba, mesurer
from dermia.engine import recalibrage  # noqa: E402  (chemin ajouté par evaluer_hiba)

CLES_P = [f"p_{c}" for c in C.CLASSES]


def appliquer(t: pd.DataFrame, params: dict, R: int) -> pd.DataFrame:
    """Décision, ensemble conforme et abstention recalculés avec `params`, comme le moteur."""
    p = t[CLES_P].to_numpy()
    pred = recalibrage.decider(p, params["thresholds"][str(R)], C.MEL)
    ens = (1.0 - p) <= np.asarray(params["conformal_q"])[None, :]
    t = t.copy()
    t["decision"] = [C.CLASSES[k] for k in pred]
    t["ensemble"] = ["|".join(c for c, e in zip(C.CLASSES, ligne) if e) for ligne in ens]
    t["traite"] = (ens.sum(1) == 1) & ens[np.arange(len(pred)), pred]
    return t


def main() -> None:
    df = charger_hiba()
    pr = pd.read_csv(C.PRED_DIR / "hiba_predictions.csv")
    t = pr.merge(df[["isic_id", "y", "age_approx", "patient_id"]], on="isic_id")
    patients = np.random.default_rng(0).permutation(df.patient_id.unique())
    moitie = dict(zip(patients, np.arange(len(patients)) % 2))
    t["moitie"] = t.patient_id.map(moitie)
    print("mélanomes par moitié :", t[(t.version == "v3") & (t.contexte == "aucun")].groupby("moitie").y.apply(
        lambda s: int((s == C.MEL).sum())).to_dict())

    lignes, recommandations = [], []
    for version, paquet in PAQUETS.items():
        m = json.loads((C.PROJECT_DIR / "application" / "modeles" / paquet / "manifest.json").read_text(encoding="utf-8"))
        R = m["decision"]["rapport_defaut"]
        for contexte in ("reel", "aucun"):
            s = t[(t.version == version) & (t.contexte == contexte)]
            recal = []
            for profil, sp in s.groupby("profil"):
                origine = m["profils"][profil]
                for a in (0, 1):
                    A, B = sp[sp.moitie == a], sp[sp.moitie == 1 - a]
                    prop = recalibrage.proposer(A[CLES_P].to_numpy(), A.y.to_numpy(), origine, m["abstention"]["alpha"],
                                                m["decision"]["rapports_cout"], R, C.MEL, C.CLASSES)
                    recal.append(appliquer(B, prop["parametres"], R))
                    rs = prop["resume"]
                    recommandations.append({"version": version, "contexte": contexte, "profil": profil,
                                            "moitie_calibration": a, "n": rs["n"], "source_seuil": rs["source_seuil"],
                                            "seuil_mel_origine": rs["seuil_mel"]["origine"],
                                            "seuil_mel_propose": rs["seuil_mel"]["propose"],
                                            "recommandation": rs["recommandation"]["decision"],
                                            "raison": rs["recommandation"]["raison"]})
            for etat, tt in (("origine", s), ("recalibré", pd.concat(recal))):
                lignes.append({"version": version, "contexte": contexte, "parametres": etat, **mesurer(tt)})
    res = pd.DataFrame(lignes)
    res.to_csv(C.TAB_DIR / "15_hiba_recalibrage.csv", index=False, encoding="utf-8")
    rec = pd.DataFrame(recommandations)
    rec.to_csv(C.TAB_DIR / "15_hiba_recalibrage_recommandations.csv", index=False, encoding="utf-8")
    with pd.option_context("display.max_columns", None, "display.width", 250):
        print(res.T.to_string())
        print(rec.to_string(index=False))


if __name__ == "__main__":
    main()
