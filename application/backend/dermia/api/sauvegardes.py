"""Sauvegarde et restauration des données de l'établissement (administrateur)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import sauvegarde, service
from ..db import SessionLocal, Utilisateur, get_db, journaliser
from ..security import COOKIE, admin_requis

router = APIRouter(prefix="/api/sauvegardes", tags=["sauvegardes"])
TAILLE_MAX_IMPORT = 4 * 1024 ** 3


def _chemin(nom: str):
    try:
        return sauvegarde.chemin(nom)
    except sauvegarde.SauvegardeInvalide:
        raise HTTPException(422, "Nom de sauvegarde invalide.")
    except FileNotFoundError:
        raise HTTPException(404, "Sauvegarde introuvable.")


@router.get("")
def lister(_: Utilisateur = Depends(admin_requis)):
    return sauvegarde.lister()


@router.post("", status_code=201)
def creer(db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    info = sauvegarde.creer("manuelle")
    journaliser(db, u.id, "sauvegarde_creee", "sauvegarde", info["nom"])
    db.commit()
    return info


@router.get("/{nom}")
def telecharger(nom: str, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    f = _chemin(nom)
    journaliser(db, u.id, "sauvegarde_telechargee", "sauvegarde", nom)
    db.commit()
    return FileResponse(f, media_type="application/zip", filename=f.name)


@router.delete("/{nom}")
def supprimer(nom: str, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    _chemin(nom).unlink()
    journaliser(db, u.id, "sauvegarde_supprimee", "sauvegarde", nom)
    db.commit()
    return {"ok": True}


@router.post("/importer", status_code=201)
def importer(fichier: UploadFile = File(...), db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    contenu = fichier.file.read(TAILLE_MAX_IMPORT + 1)
    if len(contenu) > TAILLE_MAX_IMPORT:
        raise HTTPException(413, "Archive trop volumineuse.")
    try:
        nom = sauvegarde.importer(contenu)
    except sauvegarde.SauvegardeInvalide as e:
        raise HTTPException(422, str(e))
    journaliser(db, u.id, "sauvegarde_importee", "sauvegarde", nom)
    db.commit()
    return {"nom": nom}


@router.post("/{nom}/restaurer")
def restaurer(nom: str, response: Response, db: Session = Depends(get_db), u: Utilisateur = Depends(admin_requis)):
    _chemin(nom)
    auteur = u.nom_complet
    db.close()                                  # libère la connexion avant le remplacement de la base
    try:
        res = sauvegarde.restaurer(nom)
    except sauvegarde.SauvegardeInvalide as e:
        raise HTTPException(422, str(e))
    with SessionLocal() as s:                   # journal écrit dans la base restaurée
        journaliser(s, None, "sauvegarde_restauree", "sauvegarde", nom, {"par": auteur})
        s.commit()
        service.charger_calibrations(s)
    response.delete_cookie(COOKIE, path="/")    # les comptes ont pu changer : reconnexion obligatoire
    return res
