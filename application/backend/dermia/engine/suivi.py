"""Suivi d'une lésion dans le temps : signaux d'évolution entre deux analyses (critère E de l'ABCDE).

Les signaux sont volontairement simples et explicables ; ils ne remplacent pas la comparaison
visuelle par le médecin (les deux images peuvent différer par le cadrage ou le grossissement).
"""
from __future__ import annotations

from datetime import datetime

RANG_NIVEAU = {"faible": 0, "renvoi": 1, "eleve": 2, "urgent": 3}
SEUIL_HAUSSE_PMEL = 0.10
SEUIL_HAUSSE_BORDS = 2
SEUIL_HAUSSE_DIAMETRE_MM = 1.0


def comparer(avant: dict, apres: dict) -> dict:
    """`avant` / `apres` : {id, cree_le (datetime), p_melanome, niveau, abcd (dict ou None)}."""
    signaux: list[dict] = []
    dp = apres["p_melanome"] - avant["p_melanome"]
    if dp >= SEUIL_HAUSSE_PMEL:
        signaux.append({"code": "p_mel_hausse", "de": round(avant["p_melanome"], 3), "a": round(apres["p_melanome"], 3)})
    if RANG_NIVEAU.get(apres["niveau"], 0) > RANG_NIVEAU.get(avant["niveau"], 0):
        signaux.append({"code": "orientation_aggravee", "de": avant["niveau"], "a": apres["niveau"]})
    a0, a1 = avant.get("abcd") or {}, apres.get("abcd") or {}
    if a0.get("A") and a1.get("A"):
        if a1["A"]["score"] > a0["A"]["score"]:
            signaux.append({"code": "asymetrie_hausse", "de": a0["A"]["score"], "a": a1["A"]["score"]})
        if a1["B"]["score"] - a0["B"]["score"] >= SEUIL_HAUSSE_BORDS:
            signaux.append({"code": "bords_hausse", "de": a0["B"]["score"], "a": a1["B"]["score"]})
        nouvelles = sorted(set(a1["C"]["couleurs"]) - set(a0["C"]["couleurs"]))
        if nouvelles:
            signaux.append({"code": "nouvelles_couleurs", "couleurs": nouvelles})
        d0, d1 = (a0.get("D") or {}).get("mm"), (a1.get("D") or {}).get("mm")
        if d0 is not None and d1 is not None and d1 - d0 >= SEUIL_HAUSSE_DIAMETRE_MM:
            signaux.append({"code": "diametre_hausse", "de": d0, "a": d1})
    t0, t1 = avant["cree_le"], apres["cree_le"]
    jours = (t1 - t0).days if isinstance(t0, datetime) and isinstance(t1, datetime) else None
    return {"analyse_precedente": avant["id"], "depuis": t0.isoformat() if isinstance(t0, datetime) else t0,
            "jours": jours, "delta_p_melanome": round(dp, 3), "signaux": signaux, "notable": bool(signaux)}
