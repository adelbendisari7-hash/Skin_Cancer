"""Connexion, session et gestion des utilisateurs."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Utilisateur, get_db, journaliser
from ..schemas import ChangementMotDePasse, Connexion, UtilisateurCreation, UtilisateurMaj, UtilisateurSortie
from ..security import (COOKIE, admin_requis, creer_jeton, effacer_echecs, hacher, noter_echec, poser_cookie,
                        utilisateur_courant, valider_mot_de_passe, verifier, verifier_tentatives)

router = APIRouter(prefix="/api", tags=["comptes"])


@router.post("/connexion", response_model=UtilisateurSortie)
def connexion(data: Connexion, response: Response, db: Session = Depends(get_db)):
    verifier_tentatives(data.identifiant)
    u = db.scalar(select(Utilisateur).where(func.lower(Utilisateur.identifiant) == data.identifiant.lower()))
    if u is None or not u.actif or not verifier(data.mot_de_passe, u.mot_de_passe):
        noter_echec(data.identifiant)
        journaliser(db, u.id if u else None, "connexion_refusee", details={"identifiant": data.identifiant})
        db.commit()
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")
    effacer_echecs(data.identifiant)
    u.derniere_connexion = datetime.now(timezone.utc)
    journaliser(db, u.id, "connexion")
    db.commit()
    poser_cookie(response, creer_jeton(u))
    return u


@router.post("/deconnexion")
def deconnexion(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/moi", response_model=UtilisateurSortie)
def moi(u: Utilisateur = Depends(utilisateur_courant)):
    return u


@router.post("/moi/mot-de-passe")
def changer_mot_de_passe(data: ChangementMotDePasse, db: Session = Depends(get_db),
                         u: Utilisateur = Depends(utilisateur_courant)):
    if not verifier(data.ancien, u.mot_de_passe):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    valider_mot_de_passe(data.nouveau)
    u = db.merge(u)
    u.mot_de_passe = hacher(data.nouveau)
    journaliser(db, u.id, "mot_de_passe_modifie", "utilisateur", u.id)
    db.commit()
    return {"ok": True}


@router.get("/utilisateurs", response_model=list[UtilisateurSortie])
def lister(db: Session = Depends(get_db), _: Utilisateur = Depends(admin_requis)):
    return db.scalars(select(Utilisateur).order_by(Utilisateur.nom_complet)).all()


@router.post("/utilisateurs", response_model=UtilisateurSortie, status_code=201)
def creer(data: UtilisateurCreation, db: Session = Depends(get_db), admin: Utilisateur = Depends(admin_requis)):
    if db.scalar(select(Utilisateur).where(func.lower(Utilisateur.identifiant) == data.identifiant.lower())):
        raise HTTPException(409, "Cet identifiant existe déjà.")
    valider_mot_de_passe(data.mot_de_passe)
    u = Utilisateur(identifiant=data.identifiant, nom_complet=data.nom_complet, role=data.role,
                    mot_de_passe=hacher(data.mot_de_passe))
    db.add(u)
    db.flush()
    journaliser(db, admin.id, "utilisateur_cree", "utilisateur", u.id, {"role": data.role})
    db.commit()
    return u


@router.patch("/utilisateurs/{uid}", response_model=UtilisateurSortie)
def modifier(uid: int, data: UtilisateurMaj, db: Session = Depends(get_db), admin: Utilisateur = Depends(admin_requis)):
    u = db.get(Utilisateur, uid)
    if u is None:
        raise HTTPException(404, "Utilisateur introuvable.")
    if u.id == admin.id and (data.actif is False or data.role == "medecin"):
        raise HTTPException(400, "Vous ne pouvez pas vous retirer vos propres droits d'administration.")
    if data.mot_de_passe:
        valider_mot_de_passe(data.mot_de_passe)
        u.mot_de_passe = hacher(data.mot_de_passe)
    for champ in ("nom_complet", "role", "actif"):
        if getattr(data, champ) is not None:
            setattr(u, champ, getattr(data, champ))
    journaliser(db, admin.id, "utilisateur_modifie", "utilisateur", u.id,
                data.model_dump(exclude_none=True, exclude={"mot_de_passe"}) | ({"mot_de_passe": "réinitialisé"}
                                                                               if data.mot_de_passe else {}))
    db.commit()
    return u
