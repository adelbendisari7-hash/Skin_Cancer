"""Lésions suivies : liste par patient, chronologie, comparaison de deux analyses, renommage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Lesion, Patient, Utilisateur, get_db, journaliser
from ..engine import suivi
from ..schemas import LesionMaj, LesionSortie
from ..security import utilisateur_courant
from .analyses import _resume_suivi, sortie

router = APIRouter(prefix="/api", tags=["lésions"])


def sortie_lesion(les: Lesion) -> LesionSortie:
    out = LesionSortie.model_validate(les)
    an = les.analyses
    out.nb_analyses = len(an)
    if an:
        derniere = an[-1]
        out.derniere_analyse, out.dernier_niveau, out.derniere_image = derniere.cree_le, derniere.niveau, derniere.id
        out.evolution_notable = bool(derniere.evolution and derniere.evolution.get("notable"))
    return out


def _get(db: Session, lid: int) -> Lesion:
    les = db.get(Lesion, lid)
    if les is None:
        raise HTTPException(404, "Lésion introuvable.")
    return les


@router.get("/patients/{pid}/lesions", response_model=list[LesionSortie])
def lesions_du_patient(pid: int, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    p = db.get(Patient, pid)
    if p is None:
        raise HTTPException(404, "Patient introuvable.")
    return [sortie_lesion(les) for les in p.lesions]


@router.get("/lesions/{lid}")
def lire(lid: int, a: int | None = None, b: int | None = None, db: Session = Depends(get_db),
         _: Utilisateur = Depends(utilisateur_courant)):
    """Lésion, ses analyses (ordre chronologique) et la comparaison de deux d'entre elles
    (par défaut : l'avant-dernière et la dernière)."""
    les = _get(db, lid)
    an = les.analyses
    comparaison = None
    if len(an) >= 2:
        par_id = {x.id: x for x in an}
        x, y = par_id.get(a, an[-2]), par_id.get(b, an[-1])
        if x.cree_le > y.cree_le:
            x, y = y, x
        if x.id != y.id:
            comparaison = {"avant": x.id, "apres": y.id, **suivi.comparer(_resume_suivi(x), _resume_suivi(y))}
    return {"lesion": sortie_lesion(les), "patient_code": les.patient.code,
            "analyses": [sortie(x) for x in an], "comparaison": comparaison}


@router.patch("/lesions/{lid}", response_model=LesionSortie)
def modifier(lid: int, data: LesionMaj, db: Session = Depends(get_db), u: Utilisateur = Depends(utilisateur_courant)):
    les = _get(db, lid)
    if data.nom is not None:
        les.nom = data.nom.strip() or None
    if data.notes is not None:
        les.notes = data.notes.strip() or None
    journaliser(db, u.id, "lesion_modifiee", "lesion", les.id)
    db.commit()
    return sortie_lesion(les)
