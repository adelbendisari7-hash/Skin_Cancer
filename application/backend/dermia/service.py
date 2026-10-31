"""Moteur d'IA partagé par toute l'application (chargé une fois au démarrage)."""
from __future__ import annotations

import logging
import threading

from fastapi import HTTPException

from . import config
from .engine import Moteur

log = logging.getLogger("dermia")
_etat: dict = {"moteur": None, "erreur": None}


def charger() -> None:
    try:
        _etat["moteur"] = Moteur(config.BUNDLE_DIR, device=config.DEVICE)
        m = _etat["moteur"]
        log.info("Modèle %s v%s chargé sur %s", m.nom, m.version, m.device)
    except Exception as e:  # le serveur démarre quand même et affiche l'erreur dans l'interface
        _etat["erreur"] = f"{type(e).__name__}: {e}"
        log.exception("Échec du chargement du modèle")
        return
    from .db import SessionLocal
    with SessionLocal() as s:
        charger_calibrations(s)
    # Préchauffage en arrière-plan : le serveur répond tout de suite, les premiers calculs seront rapides.
    threading.Thread(target=_prechauffer, daemon=True).start()


def charger_calibrations(db) -> None:
    """Transmet au moteur les recalibrages locaux actifs du modèle chargé (un par profil au plus)."""
    m = _etat["moteur"]
    if m is None:
        return
    from sqlalchemy import select
    from .db import Calibration
    actives = db.scalars(select(Calibration).where(Calibration.active.is_(True), Calibration.modele == m.nom,
                                                   Calibration.version_modele == m.version)).all()
    m.calibrations = {c.profil: {"id": c.id, "thresholds": c.parametres["thresholds"],
                                 "conformal_q": c.parametres["conformal_q"]} for c in actives}
    if actives:
        log.info("Recalibrage local actif : %s", ", ".join(f"{c.profil} (#{c.id})" for c in actives))


def sauvegardes_automatiques(intervalle_s: int = 6 * 3600) -> None:
    """Sauvegarde quotidienne (vérifiée au démarrage puis toutes les 6 h), dans un fil d'arrière-plan."""
    import time
    from . import sauvegarde

    def boucle():
        while True:
            try:
                info = sauvegarde.automatique()
                if info:
                    log.info("Sauvegarde automatique : %s", info["nom"])
            except Exception:
                log.exception("Échec de la sauvegarde automatique")
            time.sleep(intervalle_s)
    threading.Thread(target=boucle, daemon=True, name="dermia-sauvegarde").start()


def _prechauffer() -> None:
    try:
        log.info("Préchauffage du moteur terminé en %.1f s", _etat["moteur"].prechauffer())
    except Exception:
        log.exception("Échec du préchauffage (sans conséquence sur les résultats)")


def moteur() -> Moteur:
    if _etat["moteur"] is None:
        raise HTTPException(503, f"Moteur d'IA indisponible : {_etat['erreur'] or 'chargement en cours'}")
    return _etat["moteur"]


def etat() -> dict:
    m = _etat["moteur"]
    if m is None:
        return {"charge": False, "erreur": _etat["erreur"]}
    return {"charge": True, "nom": m.nom, "version": m.version, "statut": m.m["statut"],
            "statut_i18n": m.m.get("statut_i18n"), "detection_hors_sujet": m.hors_sujet is not None,
            "peripherique": str(m.device), "localisations": [lo for lo in m.localisations if lo != "unknown"],
            "classes": m.classes, "noms_classes": m.noms, "classes_malignes": m.m["classes_malignes"],
            "rapports_cout": m.m["decision"]["rapports_cout"]}
