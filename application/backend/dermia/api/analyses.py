"""Analyses : création (image + contexte), consultation, images, « et si », revue médicale, compte rendu PDF.

Version 2 : refus des images hors sujet (sauf « analyser quand même », tracé), critères ABCD,
rattachement à une lésion suivie et signaux d'évolution par rapport à l'analyse précédente.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, service
from ..db import Analyse, Lesion, Patient, Utilisateur, get_db, journaliser, parametre
from ..engine import Contexte, abcd, suivi
from ..schemas import AnalyseSortie, EtSi, Revue
from ..security import utilisateur_courant

router = APIRouter(prefix="/api/analyses", tags=["analyses"])
AGES_ET_SI = list(range(10, 90, 5))
NATURES = ("image", "gradcam", "abcd")


def sortie(a: Analyse) -> AnalyseSortie:
    return AnalyseSortie.model_validate({
        **{c.name: getattr(a, c.name) for c in Analyse.__table__.columns},
        "patient_code": a.patient.code, "auteur": a.auteur.nom_complet,
        "relecteur": a.relecteur.nom_complet if a.relecteur else None,
        "lesion_numero": a.lesion.numero if a.lesion else None, "lesion_nom": a.lesion.nom if a.lesion else None})


def _fichier(a: Analyse, nature: str):
    return config.IMAGES_DIR / f"{a.uid}_{nature}.png"     # PNG sans perte : « et si » rejoue la même image


def _get(db: Session, aid: int) -> Analyse:
    a = db.get(Analyse, aid)
    if a is None:
        raise HTTPException(404, "Analyse introuvable.")
    return a


def _lire_image(data: bytes) -> Image.Image:
    if len(data) > config.TAILLE_MAX_IMAGE:
        raise HTTPException(413, "Image trop volumineuse (15 Mo maximum).")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "Fichier illisible : envoyez une image JPEG, PNG, TIFF, BMP ou WEBP.")
    if im.format not in config.FORMATS_IMAGE:
        raise HTTPException(422, "Format d'image non pris en charge.")
    if min(im.size) < 64:
        raise HTTPException(422, "Image trop petite (64 px minimum).")
    return im


def champ_mm(db: Session) -> float | None:
    v = parametre(db, "champ_dermoscope_mm")
    try:
        return float(v) if v and float(v) > 0 else None
    except ValueError:
        return None


def _resume_suivi(a: Analyse) -> dict:
    return {"id": a.id, "cree_le": a.cree_le, "p_melanome": a.p_melanome, "niveau": a.niveau, "abcd": a.abcd}


@router.post("", response_model=AnalyseSortie, status_code=201)
def creer(patient_id: int = Form(...), localisation: str = Form("unknown"), age: float | None = Form(None),
          sexe: str | None = Form(None), rapport_cout: int | None = Form(None), lesion_id: int | None = Form(None),
          forcer: bool = Form(False), image: UploadFile = File(...), db: Session = Depends(get_db),
          u: Utilisateur = Depends(utilisateur_courant)):
    moteur = service.moteur()
    p = db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404, "Patient introuvable.")
    lesion = None
    if lesion_id is not None:
        lesion = db.get(Lesion, lesion_id)
        if lesion is None or lesion.patient_id != p.id:
            raise HTTPException(404, "Lésion introuvable pour ce patient.")
        localisation = lesion.localisation if localisation == "unknown" else localisation
    if localisation not in moteur.localisations:
        raise HTTPException(422, "Localisation inconnue.")
    if age is not None and not 0 <= age <= 120:
        raise HTTPException(422, "Âge invalide.")
    sexe = sexe or p.sexe
    if age is None and p.annee_naissance:
        age = float(datetime.now().year - p.annee_naissance)
    R = rapport_cout or int(parametre(db, "rapport_cout_defaut"))
    data = image.file.read()          # route synchrone : l'inférence tourne hors de la boucle d'événements
    im = _lire_image(data)

    ctx = Contexte(age=age, sexe=sexe, localisation=localisation)
    try:
        res, x = moteur.analyser(im, ctx, R)
    except ValueError:
        raise HTTPException(422, "Rapport de coût non calibré pour ce modèle.")

    # Images hors sujet : refus expliqué, sauf si le médecin choisit d'analyser quand même (tracé)
    if res.hors_sujet and not forcer:
        journaliser(db, u.id, "image_refusee", "patient", p.code,
                    {"score": res.score_hors_sujet, "seuil": moteur.hors_sujet["seuil"]})
        db.commit()
        raise HTTPException(422, {"code": "image_hors_sujet",
                                  "message": "Cette image ne ressemble pas à une image dermoscopique.",
                                  "score": res.score_hors_sujet, "seuil": round(moteur.hors_sujet["seuil"], 2)})
    if res.hors_sujet:
        res.avertissements.append({"code": "image_atypique"})

    cam = moteur.gradcam(x, ctx, res.decision)
    mesure = abcd.mesurer(im, champ_mm(db))

    if lesion is None:
        n = (db.scalar(select(func.max(Lesion.numero)).where(Lesion.patient_id == p.id)) or 0) + 1
        lesion = Lesion(patient_id=p.id, numero=n, localisation=localisation)
        db.add(lesion)
        db.flush()
    precedente = db.scalars(select(Analyse).where(Analyse.lesion_id == lesion.id)
                            .order_by(Analyse.cree_le.desc())).first()

    a = Analyse(uid=str(uuid.uuid4()), patient_id=p.id, auteur_id=u.id, age=age, sexe=sexe or "unknown",
                localisation=localisation, nom_fichier_original=(image.filename or "")[:256], lesion_id=lesion.id,
                modele=res.modele, version_modele=res.version, profil=res.profil, rapport_cout=res.rapport_cout,
                seuil_melanome=res.seuil_melanome, probabilites=res.probabilites, decision=res.decision,
                p_melanome=res.p_melanome, ensemble_conforme=res.ensemble_conforme, traite=res.traite,
                statut=res.statut, niveau=res.niveau, titre=res.titre, message=res.message,
                avertissements=res.avertissements, duree_ms=res.duree_ms, abcd=abcd.publiable(mesure),
                score_hors_sujet=res.score_hors_sujet, hors_sujet_force=bool(res.hors_sujet),
                calibration=res.calibration, cree_le=datetime.now(timezone.utc))
    if precedente is not None:
        evo = suivi.comparer(_resume_suivi(precedente), _resume_suivi(a))
        a.evolution = evo
        if evo["notable"]:
            a.avertissements = [*a.avertissements, {"code": "evolution", "depuis": evo["depuis"]}]
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    # copie sans perte et sans métadonnées, orientation EXIF appliquée (= l'image vue par le modèle)
    ImageOps.exif_transpose(im).convert("RGB").save(_fichier(a, "image"), "PNG")
    _fichier(a, "gradcam").write_bytes(moteur.gradcam_png(im, cam))
    _fichier(a, "abcd").write_bytes(abcd.superposition_png(im, mesure))
    db.add(a)
    db.flush()
    journaliser(db, u.id, "analyse_forcee" if res.hors_sujet else "analyse_creee", "analyse", a.id,
                {"patient": p.code, "statut": res.statut, "modele": f"{res.modele} v{res.version}",
                 "calibration": res.calibration})
    db.commit()
    db.refresh(a)
    return sortie(a)


@router.get("")
def lister(statut: str | None = None, revue: str | None = None, page: int = 1, taille: int = 25,
           db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    taille = min(max(taille, 1), 100)
    req = select(Analyse)
    if statut:
        req = req.where(Analyse.statut == statut)
    if revue:
        req = req.where(Analyse.revue == revue)
    total = db.scalar(select(func.count()).select_from(req.subquery()))
    rows = db.scalars(req.order_by(Analyse.cree_le.desc()).offset((page - 1) * taille).limit(taille)).all()
    return {"total": total, "elements": [sortie(a) for a in rows]}


@router.get("/{aid}", response_model=AnalyseSortie)
def lire(aid: int, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    return sortie(_get(db, aid))


@router.get("/{aid}/image/{nature}")
def image(aid: int, nature: str, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    if nature not in NATURES:
        raise HTTPException(404, "Fichier image manquant.")
    f = _fichier(_get(db, aid), nature)
    if not f.exists():
        raise HTTPException(404, "Fichier image manquant.")
    return FileResponse(f, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{aid}/et-si")
def et_si(aid: int, data: EtSi, db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    """Contrefactuel : même image, âge ou localisation modifiés → p(mélanome) (modèle et seuils actuels)."""
    a = _get(db, aid)
    moteur = service.moteur()
    valeurs = data.valeurs or (AGES_ET_SI if data.variable == "age"
                               else [lo for lo in moteur.localisations if lo != "unknown"])
    if len(valeurs) > 40:
        raise HTTPException(422, "40 valeurs au maximum.")
    im = Image.open(_fichier(a, "image"))
    ctx = Contexte(a.age, a.sexe, a.localisation)
    serie = moteur.et_si(im, ctx, data.variable, valeurs)
    seuils, _, _ = moteur.parametres(moteur._profil(ctx))
    return {"variable": data.variable, "actuel": getattr(ctx, data.variable), "serie": serie,
            "seuil_melanome": float(seuils[str(a.rapport_cout)]) if str(a.rapport_cout) in seuils else a.seuil_melanome,
            "meme_modele": a.modele == moteur.nom and a.version_modele == moteur.version}


@router.post("/{aid}/revue", response_model=AnalyseSortie)
def revue(aid: int, data: Revue, db: Session = Depends(get_db), u: Utilisateur = Depends(utilisateur_courant)):
    a = _get(db, aid)
    moteur = service.moteur()
    if data.revue == "corrigee":
        if data.diagnostic_final not in moteur.classes:
            raise HTTPException(422, "Indiquez le diagnostic retenu (une des 7 classes).")
        a.diagnostic_final = data.diagnostic_final
    else:
        a.diagnostic_final = a.decision
    a.revue, a.commentaire, a.histologie = data.revue, data.commentaire, data.histologie
    a.revue_par_id, a.revue_le = u.id, datetime.now(timezone.utc)
    journaliser(db, u.id, "analyse_revue", "analyse", a.id,
                {"revue": data.revue, "diagnostic": a.diagnostic_final, "histologie": data.histologie})
    db.commit()
    db.refresh(a)
    return sortie(a)


@router.get("/{aid}/compte-rendu.pdf")
def compte_rendu(aid: int, langue: str = Query("fr", pattern="^(fr|en|ar)$"), db: Session = Depends(get_db),
                 u: Utilisateur = Depends(utilisateur_courant)):
    from ..pdf import compte_rendu_pdf
    a = _get(db, aid)
    pdf = compte_rendu_pdf(a, parametre(db, "nom_etablissement"), _fichier(a, "image"), _fichier(a, "gradcam"),
                           _fichier(a, "abcd"), service.moteur().m, langue)
    journaliser(db, u.id, "compte_rendu_exporte", "analyse", a.id, {"langue": langue})
    db.commit()
    nom = f"compte-rendu_{a.patient.code}_{a.cree_le:%Y%m%d-%H%M}_{langue}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nom}"'})
