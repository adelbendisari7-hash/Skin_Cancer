"""Recalibrage local des seuils sur les cas validés de l'établissement (administrateur)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import service
from ..db import Analyse, Calibration, Utilisateur, get_db, journaliser
from ..engine import recalibrage
from ..schemas import PropositionRecalibrage
from ..security import admin_requis

router = APIRouter(prefix="/api/recalibrage", tags=["recalibrage"])
PROFILS = ("complet", "sans_contexte")
N_MIN_PROPOSITION = 30


def _validees(db: Session, profil: str, histologie_seulement: bool) -> list[Analyse]:
    """Analyses validées par un médecin, faites avec le modèle actuel et ce profil, hors images forcées."""
    m = service.moteur()
    req = select(Analyse).where(Analyse.revue.in_(("confirmee", "corrigee")), Analyse.diagnostic_final.is_not(None),
                                Analyse.modele == m.nom, Analyse.version_modele == m.version,
                                Analyse.profil == profil, Analyse.hors_sujet_force.is_(False))
    if histologie_seulement:
        req = req.where(Analyse.histologie.is_(True))
    return list(db.scalars(req).all())


def _description(c: Calibration) -> dict:
    return {"id": c.id, "cree_le": c.cree_le, "auteur": c.auteur.nom_complet if c.auteur else None,
            "profil": c.profil, "active": c.active, "applique_le": c.applique_le,
            "parametres": c.parametres, "resume": c.resume}


@router.get("")
def etat(db: Session = Depends(get_db), _: Utilisateur = Depends(admin_requis)):
    m = service.moteur()
    out = {"modele": m.nom, "version": m.version, "minimum_par_classe": recalibrage.N_MIN_CLASSE,
           "minimum_proposition": N_MIN_PROPOSITION, "profils": {}}
    for profil in PROFILS:
        toutes = _validees(db, profil, False)
        histo = [a for a in toutes if a.histologie]
        cal = db.scalars(select(Calibration).where(Calibration.modele == m.nom, Calibration.version_modele == m.version,
                                                   Calibration.profil == profil)
                         .order_by(Calibration.cree_le.desc())).all()
        out["profils"][profil] = {
            "n_valides": len(toutes), "n_histologie": len(histo),
            "par_classe": {c: sum(a.diagnostic_final == c for a in toutes) for c in m.classes},
            "active": next((_description(c) for c in cal if c.active), None),
            "propositions": [_description(c) for c in cal[:5]],
            "origine": {"thresholds": m.m["profils"][profil]["thresholds"],
                        "conformal_q": m.m["profils"][profil]["conformal_q"]}}
    return out


@router.post("/propositions")
def proposer(data: PropositionRecalibrage, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    m = service.moteur()
    cas = _validees(db, data.profil, data.histologie_seulement)
    if len(cas) < N_MIN_PROPOSITION:
        raise HTTPException(422, "Pas assez de cas validés pour proposer un recalibrage.")
    p = np.array([[a.probabilites[c] for c in m.classes] for a in cas])
    y = np.array([m.classes.index(a.diagnostic_final) for a in cas])
    origine = m.m["profils"][data.profil]
    prop = recalibrage.proposer(p, y, {"thresholds": origine["thresholds"], "conformal_q": origine["conformal_q"]},
                                m.m["abstention"]["alpha"], m.m["decision"]["rapports_cout"],
                                m.m["decision"]["rapport_defaut"], m.mel, m.classes)
    prop["resume"]["histologie_seulement"] = data.histologie_seulement
    c = Calibration(auteur_id=u.id, modele=m.nom, version_modele=m.version, profil=data.profil, active=False,
                    parametres=prop["parametres"], resume=prop["resume"])
    db.add(c)
    db.flush()
    journaliser(db, u.id, "recalibrage_propose", "calibration", c.id, {"profil": data.profil, "n": len(cas)})
    db.commit()
    db.refresh(c)
    return _description(c)


@router.post("/{cid}/appliquer")
def appliquer(cid: int, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    m = service.moteur()
    c = db.get(Calibration, cid)
    if c is None or c.modele != m.nom or c.version_modele != m.version:
        raise HTTPException(404, "Proposition de recalibrage introuvable.")
    for autre in db.scalars(select(Calibration).where(Calibration.modele == m.nom, Calibration.profil == c.profil,
                                                      Calibration.active.is_(True))).all():
        autre.active = False
    c.active, c.applique_le = True, datetime.now(timezone.utc)
    journaliser(db, u.id, "recalibrage_applique", "calibration", c.id, {"profil": c.profil})
    db.commit()
    service.charger_calibrations(db)
    return _description(c)


@router.post("/reinitialiser/{profil}")
def reinitialiser(profil: str, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    if profil not in PROFILS:
        raise HTTPException(404, "Profil inconnu.")
    m = service.moteur()
    for c in db.scalars(select(Calibration).where(Calibration.modele == m.nom, Calibration.profil == profil,
                                                  Calibration.active.is_(True))).all():
        c.active = False
    journaliser(db, u.id, "recalibrage_annule", "profil", profil)
    db.commit()
    service.charger_calibrations(db)
    return {"ok": True}
