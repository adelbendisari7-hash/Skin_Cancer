"""Dossiers patients pseudonymisés."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import Analyse, Patient, Utilisateur, get_db, journaliser
from ..schemas import PatientEntree, PatientSortie
from ..security import utilisateur_courant

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _sortie(p: Patient) -> PatientSortie:
    out = PatientSortie.model_validate(p)
    out.nb_analyses = len(p.analyses)
    if p.analyses:
        out.derniere_analyse = p.analyses[0].cree_le
        out.dernier_statut = p.analyses[0].statut
    return out


def _nouveau_code(db: Session) -> str:
    annee = datetime.now().year
    n = db.scalar(select(func.count(Patient.id)).where(Patient.code.like(f"P-{annee}-%"))) + 1
    while db.scalar(select(Patient.id).where(Patient.code == f"P-{annee}-{n:04d}")):
        n += 1
    return f"P-{annee}-{n:04d}"


@router.get("", response_model=dict)
def lister(q: str = "", page: int = 1, taille: int = 25, db: Session = Depends(get_db),
           _: Utilisateur = Depends(utilisateur_courant)):
    taille = min(max(taille, 1), 100)
    req = select(Patient)
    if q:
        motif = f"%{q.strip()}%"
        req = req.where(or_(Patient.code.ilike(motif), Patient.reference_externe.ilike(motif)))
    total = db.scalar(select(func.count()).select_from(req.subquery()))
    rows = db.scalars(req.order_by(Patient.cree_le.desc()).offset((page - 1) * taille).limit(taille)).all()
    return {"total": total, "elements": [_sortie(p) for p in rows]}


@router.post("", response_model=PatientSortie, status_code=201)
def creer(data: PatientEntree, db: Session = Depends(get_db), u: Utilisateur = Depends(utilisateur_courant)):
    if data.reference_externe and db.scalar(select(Patient.id).where(Patient.reference_externe == data.reference_externe)):
        raise HTTPException(409, "Un patient avec cette référence existe déjà.")
    p = Patient(code=_nouveau_code(db), cree_par_id=u.id, **data.model_dump())
    db.add(p)
    db.flush()
    journaliser(db, u.id, "patient_cree", "patient", p.code)
    db.commit()
    db.refresh(p)
    return _sortie(p)


@router.get("/{pid}", response_model=PatientSortie)
def lire(pid: int, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    p = db.get(Patient, pid)
    if p is None:
        raise HTTPException(404, "Patient introuvable.")
    return _sortie(p)


@router.patch("/{pid}", response_model=PatientSortie)
def modifier(pid: int, data: PatientEntree, db: Session = Depends(get_db), u: Utilisateur = Depends(utilisateur_courant)):
    p = db.get(Patient, pid)
    if p is None:
        raise HTTPException(404, "Patient introuvable.")
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    journaliser(db, u.id, "patient_modifie", "patient", p.code)
    db.commit()
    return _sortie(p)


@router.get("/{pid}/analyses")
def analyses_du_patient(pid: int, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    from .analyses import sortie
    if db.get(Patient, pid) is None:
        raise HTTPException(404, "Patient introuvable.")
    rows = db.scalars(select(Analyse).where(Analyse.patient_id == pid).order_by(Analyse.cree_le.desc())).all()
    return [sortie(a) for a in rows]
