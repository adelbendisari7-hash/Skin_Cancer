"""État de l'application, installation initiale, fiche du modèle, paramètres, journal, tableau de bord."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__, config, service
from ..db import Analyse, Journal, Parametre, Patient, Utilisateur, get_db, journaliser, parametre
from ..schemas import Installation, Parametres
from ..security import admin_requis, creer_jeton, hacher, poser_cookie, utilisateur_courant, valider_mot_de_passe

router = APIRouter(prefix="/api", tags=["système"])


@router.get("/etat")
def etat(db: Session = Depends(get_db)):
    return {"produit": config.NOM_PRODUIT, "version": __version__,
            "installation_requise": db.scalar(select(func.count(Utilisateur.id))) == 0,
            "etablissement": parametre(db, "nom_etablissement"), "modele": service.etat()}


@router.post("/installation")
def installation(data: Installation, response: Response, db: Session = Depends(get_db)):
    """Crée le premier compte administrateur. Impossible dès qu'un compte existe."""
    if db.scalar(select(func.count(Utilisateur.id))) > 0:
        raise HTTPException(409, "L'application est déjà installée.")
    valider_mot_de_passe(data.mot_de_passe)
    u = Utilisateur(identifiant=data.identifiant, nom_complet=data.nom_complet, role="admin",
                    mot_de_passe=hacher(data.mot_de_passe), derniere_connexion=datetime.now(timezone.utc))
    db.add(u)
    db.merge(Parametre(cle="nom_etablissement", valeur=data.nom_etablissement))
    db.flush()
    journaliser(db, u.id, "installation", "utilisateur", u.id)
    db.commit()
    poser_cookie(response, creer_jeton(u))
    return {"ok": True}


@router.get("/modele")
def fiche_modele(_: Utilisateur = Depends(utilisateur_courant)):
    return service.moteur().fiche()


@router.get("/parametres")
def lire_parametres(db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    champ = parametre(db, "champ_dermoscope_mm")
    return {"nom_etablissement": parametre(db, "nom_etablissement"),
            "rapport_cout_defaut": int(parametre(db, "rapport_cout_defaut")),
            "champ_dermoscope_mm": float(champ) if champ else None}


@router.put("/parametres")
def ecrire_parametres(data: Parametres, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    if data.rapport_cout_defaut is not None:
        dispo = service.moteur().m["decision"]["rapports_cout"]
        if data.rapport_cout_defaut not in dispo:
            raise HTTPException(422, f"Rapport de coût non calibré pour ce modèle (disponibles : {dispo}).")
        db.merge(Parametre(cle="rapport_cout_defaut", valeur=str(data.rapport_cout_defaut)))
    if data.nom_etablissement:
        db.merge(Parametre(cle="nom_etablissement", valeur=data.nom_etablissement))
    if data.champ_dermoscope_mm is not None:
        db.merge(Parametre(cle="champ_dermoscope_mm",
                           valeur="" if data.champ_dermoscope_mm == 0 else str(data.champ_dermoscope_mm)))
    journaliser(db, u.id, "parametres", details=data.model_dump(exclude_none=True))
    db.commit()
    return lire_parametres(db, u)


@router.get("/journal")
def journal(page: int = 1, taille: int = 50, db: Session = Depends(get_db), _: Utilisateur = Depends(admin_requis)):
    taille = min(max(taille, 1), 200)
    total = db.scalar(select(func.count(Journal.id)))
    rows = db.scalars(select(Journal).order_by(Journal.le.desc()).offset((page - 1) * taille).limit(taille)).all()
    return {"total": total, "elements": [
        {"id": j.id, "le": j.le, "utilisateur": j.utilisateur.nom_complet if j.utilisateur else None,
         "action": j.action, "objet": j.objet, "objet_id": j.objet_id, "details": j.details} for j in rows]}


@router.get("/tableau-de-bord")
def tableau_de_bord(db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    depuis = datetime.now(timezone.utc) - timedelta(days=30)
    par_statut = dict(db.execute(select(Analyse.statut, func.count()).group_by(Analyse.statut)).all())
    par_revue = dict(db.execute(select(Analyse.revue, func.count()).group_by(Analyse.revue)).all())
    jours = db.execute(select(func.date(Analyse.cree_le), func.count()).where(Analyse.cree_le >= depuis)
                       .group_by(func.date(Analyse.cree_le))).all()
    revues = par_revue.get("confirmee", 0) + par_revue.get("corrigee", 0)
    return {
        "total_analyses": sum(par_statut.values()),
        "analyses_30j": sum(n for _, n in jours),
        "patients": db.scalar(select(func.count(Patient.id))),
        "par_statut": par_statut,
        "revues_en_attente": par_revue.get("en_attente", 0),
        "taux_accord": (par_revue.get("confirmee", 0) / revues) if revues else None,
        "par_jour": [{"jour": str(d), "n": n} for d, n in sorted(jours)],
    }
