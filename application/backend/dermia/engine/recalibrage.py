"""Recalibrage local : adapter les seuils de prudence aux patients et à l'appareil de l'établissement.

À partir des analyses VALIDÉES par les médecins (diagnostic retenu = étiquette), on recalcule :
- les seuils conformes Mondrian q_k (un par classe), pour les classes ayant au moins N_MIN_CLASSE cas ;
  la garantie « la vraie classe est dans l'ensemble avec probabilité ≥ 1 − α » vaut alors pour les
  futurs cas qui ressemblent aux cas validés de l'établissement ;
- le seuil de décision mélanome (pour chaque rapport de coût R), s'il y a au moins N_MIN_MEL mélanomes
  et N_MIN_TOTAL cas.
Les autres paramètres restent ceux d'origine. La couverture obtenue est estimée par validation croisée
à 5 plis (les paramètres sont réestimés sans le pli évalué), comparée à celle des paramètres d'origine.
"""
from __future__ import annotations

import numpy as np

N_MIN_CLASSE = 20
N_MIN_MEL = 20
N_MIN_TOTAL = 100
GRILLE_T = np.round(np.arange(0.01, 0.991, 0.01), 2)


def quantile_conforme(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return float("inf") if k > n else float(np.sort(scores)[k - 1])


def decider(p: np.ndarray, t: float, mel: int) -> np.ndarray:
    autres = p.copy()
    autres[:, mel] = -1
    pred = autres.argmax(1)
    pred[p[:, mel] >= t] = mel
    return pred


def cout_moyen(y: np.ndarray, pred: np.ndarray, R: float, mel: int) -> float:
    c = np.where(y == pred, 0.0, 1.0)
    c[(y == mel) & (pred != mel)] = R
    return float(c.mean())


def _ajuster(p: np.ndarray, y: np.ndarray, alpha: float, rapports: list[int], origine: dict, mel: int) -> tuple[dict, list[str], dict]:
    K = p.shape[1]
    q, sources = [], []
    for k in range(K):
        sel = y == k
        if sel.sum() >= N_MIN_CLASSE:
            q.append(quantile_conforme(1.0 - p[sel, k], alpha)); sources.append("locale")
        else:
            q.append(float(origine["conformal_q"][k])); sources.append("origine")
    if (y == mel).sum() >= N_MIN_MEL and len(y) >= N_MIN_TOTAL:
        seuils = {}
        for R in rapports:
            couts = np.array([cout_moyen(y, decider(p, t, mel), R, mel) for t in GRILLE_T])
            seuils[str(R)] = float(GRILLE_T[np.flatnonzero(couts <= couts.min() + 1e-12).max()])
        source_seuil = "locale"
    else:
        seuils, source_seuil = {str(R): float(origine["thresholds"][str(R)]) for R in rapports}, "origine"
    return {"thresholds": seuils, "conformal_q": q}, sources, {"seuil": source_seuil}


def _evaluer(p: np.ndarray, y: np.ndarray, params: dict, R: int, mel: int) -> dict:
    q = np.asarray(params["conformal_q"])
    ens = (1.0 - p) <= q[None, :]
    couvert = ens[np.arange(len(y)), y]
    pred = decider(p, params["thresholds"][str(R)], mel)
    traite = (ens.sum(1) == 1) & ens[np.arange(len(y)), pred]
    est_mel = y == mel
    return {"couverture": float(couvert.mean()),
            "couverture_mel": float(couvert[est_mel].mean()) if est_mel.any() else None,
            "taux_traite": float(traite.mean()),
            "mel_manques_en_silence": int((est_mel & traite & (pred != mel)).sum())}


def recommander(resume: dict) -> dict:
    """Recommandation prudente, fondée sur l'estimation honnête (validation croisée) comparée aux seuils
    d'origine évalués sur les mêmes cas locaux.

    Constat expérimental (projet/src/experience_recalibrage.py) : sans changement d'appareil, recalibrer sur
    quelques centaines de cas DÉGRADE la sécurité mélanome (bruit d'échantillonnage) ; avec un appareil
    différent, le recalibrage la restaure. On ne recommande donc d'appliquer que si la sécurité mélanome
    estimée ne se dégrade pas ET qu'il y a un gain (sécurité mélanome, ou couverture d'origine insuffisante).
    """
    o, v = resume["origine"], resume.get("recalibre_validation_croisee")
    if v is None:
        return {"decision": "conserver", "raison": "estimation_indisponible"}
    mel_connu = o["couverture_mel"] is not None and v["couverture_mel"] is not None
    if (mel_connu and v["couverture_mel"] < o["couverture_mel"]) or v["mel_manques_en_silence"] > o["mel_manques_en_silence"]:
        return {"decision": "conserver", "raison": "securite_melanome_degradee"}
    if (mel_connu and v["couverture_mel"] > o["couverture_mel"]) or v["mel_manques_en_silence"] < o["mel_manques_en_silence"]:
        return {"decision": "appliquer", "raison": "gain_securite_melanome"}
    if o["couverture"] < 1 - resume["alpha"] - 0.02 and v["couverture"] > o["couverture"]:
        return {"decision": "appliquer", "raison": "couverture_restauree"}
    return {"decision": "conserver", "raison": "aucun_gain"}


def proposer(p: np.ndarray, y: np.ndarray, origine: dict, alpha: float, rapports: list[int], R_defaut: int,
             mel: int, classes: list[str], plis: int = 5, graine: int = 0) -> dict:
    """Proposition de recalibrage et estimation honnête de son effet (validation croisée)."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    params, sources, src = _ajuster(p, y, alpha, rapports, origine, mel)
    n_par_classe = {c: int((y == k).sum()) for k, c in enumerate(classes)}
    resume = {"n": int(len(y)), "n_par_classe": n_par_classe,
              "sources_q": dict(zip(classes, sources)), "source_seuil": src["seuil"],
              "seuil_mel": {"origine": float(origine["thresholds"][str(R_defaut)]),
                            "propose": float(params["thresholds"][str(R_defaut)])},
              "alpha": alpha, "rapport_cout": R_defaut,
              "origine": _evaluer(p, y, origine, R_defaut, mel)}
    # Validation croisée : on réestime sans le pli, on évalue sur le pli → estimation non optimiste
    if len(y) >= 2 * plis:
        ordre = np.random.default_rng(graine).permutation(len(y))
        pli = np.empty(len(y), int)
        pli[ordre] = np.arange(len(y)) % plis
        couvert, traite, mel_sil = np.zeros(len(y), bool), np.zeros(len(y), bool), 0
        for f in range(plis):
            a, b = pli != f, pli == f
            pr, _, _ = _ajuster(p[a], y[a], alpha, rapports, origine, mel)
            qv = np.asarray(pr["conformal_q"])
            ens = (1.0 - p[b]) <= qv[None, :]
            yb = y[b]
            couvert[b] = ens[np.arange(len(yb)), yb]
            pred = decider(p[b], pr["thresholds"][str(R_defaut)], mel)
            tr = (ens.sum(1) == 1) & ens[np.arange(len(yb)), pred]
            traite[b] = tr
            mel_sil += int(((yb == mel) & tr & (pred != mel)).sum())
        est_mel = y == mel
        resume["recalibre_validation_croisee"] = {
            "couverture": float(couvert.mean()),
            "couverture_mel": float(couvert[est_mel].mean()) if est_mel.any() else None,
            "taux_traite": float(traite.mean()), "mel_manques_en_silence": mel_sil}
    resume["recommandation"] = recommander(resume)
    return {"parametres": {**params, "sources_q": sources, "source_seuil": src["seuil"]}, "resume": resume}
