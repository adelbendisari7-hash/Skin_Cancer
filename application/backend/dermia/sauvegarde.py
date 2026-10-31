"""Sauvegarde et restauration des données de l'établissement (base + images).

- Archive ZIP : manifest.json, dermia.sqlite (copie cohérente via l'API de sauvegarde SQLite, qui gère
  le journal WAL — une simple copie de fichier peut donner une base vide ou incohérente), images/.
- Vérification avant restauration : noms de fichiers sûrs (anti « zip-slip »), intégrité SQLite,
  tables attendues, version de schéma compatible.
- Restauration : sauvegarde de sécurité préalable, application en maintenance (requêtes suspendues),
  fermeture des connexions, remplacement des fichiers, migration éventuelle.
- Sauvegarde automatique quotidienne au démarrage puis toutes les 6 h ; 7 sauvegardes automatiques conservées.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__, config

REP = config.DATA_DIR / "sauvegardes"
NOM_DB = "dermia.sqlite"
TABLES_REQUISES = {"utilisateurs", "patients", "analyses", "journal", "parametres"}
NOM_VALIDE = re.compile(r"^[\w\-]+\.zip$")
IMAGE_VALIDE = re.compile(r"^images/[\w\-]+\.png$")
TAILLE_MAX = 20 * 1024 ** 3                 # 20 Go décompressés au maximum
GARDER_AUTO = 7
MAINTENANCE = threading.Event()             # levé pendant une restauration
_VERROU = threading.Lock()


class SauvegardeInvalide(ValueError):
    pass


def _db() -> Path:
    return config.DATA_DIR / NOM_DB


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _compter(db: Path) -> dict:
    con = sqlite3.connect(db)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("patients", "analyses", "utilisateurs")}
    finally:
        con.close()


def _nouveau_nom(type_: str) -> str:
    """Nom horodaté, rendu unique si deux archives sont créées dans la même seconde."""
    base = f"{datetime.now():%Y-%m-%d_%H%M%S}_{type_}"
    nom, i = f"{base}.zip", 2
    while (REP / nom).exists():
        nom, i = f"{base}-{i}.zip", i + 1
    return nom


def creer(type_: str = "manuelle") -> dict:
    """Crée une archive cohérente dans donnees/sauvegardes et renvoie sa description."""
    REP.mkdir(parents=True, exist_ok=True)
    nom = _nouveau_nom(type_)
    with _VERROU, tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / NOM_DB
        src, dst = sqlite3.connect(_db()), sqlite3.connect(copie)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        from .db import SCHEMA_VERSION
        manifest = {"application": config.NOM_PRODUIT, "version": __version__, "schema": SCHEMA_VERSION,
                    "date": datetime.now().astimezone().isoformat(timespec="seconds"), "type": type_,
                    "sha256_base": _sha256(copie), **{f"n_{k}": v for k, v in _compter(copie).items()}}
        images = sorted(config.IMAGES_DIR.glob("*.png")) if config.IMAGES_DIR.exists() else []
        cible = REP / nom
        with zipfile.ZipFile(cible, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.write(copie, NOM_DB)
            for im in images:
                z.write(im, f"images/{im.name}", compress_type=zipfile.ZIP_STORED)   # PNG déjà compressé
        manifest["n_images"] = len(images)
    return {"nom": nom, "taille": cible.stat().st_size, **manifest}


def lister() -> list[dict]:
    if not REP.exists():
        return []
    out = []
    for f in sorted(REP.glob("*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(f) as z:
                m = json.loads(z.read("manifest.json"))
                m["n_images"] = sum(1 for n in z.namelist() if n.startswith("images/"))
            out.append({"nom": f.name, "taille": f.stat().st_size, **m})
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            out.append({"nom": f.name, "taille": f.stat().st_size, "type": "illisible"})
    return out


def chemin(nom: str) -> Path:
    if not NOM_VALIDE.match(nom):
        raise SauvegardeInvalide("Nom de sauvegarde invalide.")
    f = REP / nom
    if not f.exists():
        raise FileNotFoundError(nom)
    return f


def verifier(f: Path) -> dict:
    """Contrôle complet d'une archive avant restauration ; renvoie son manifeste."""
    from .db import SCHEMA_VERSION
    try:
        z = zipfile.ZipFile(f)
    except zipfile.BadZipFile:
        raise SauvegardeInvalide("Ce fichier n'est pas une archive ZIP valide.")
    with z:
        noms = z.namelist()
        interdits = [n for n in noms if n not in ("manifest.json", NOM_DB) and not IMAGE_VALIDE.match(n)]
        if interdits:
            raise SauvegardeInvalide("L'archive contient des fichiers inattendus.")
        if "manifest.json" not in noms or NOM_DB not in noms:
            raise SauvegardeInvalide("L'archive est incomplète (manifeste ou base manquants).")
        if sum(i.file_size for i in z.infolist()) > TAILLE_MAX:
            raise SauvegardeInvalide("L'archive est trop volumineuse.")
        if z.testzip() is not None:
            raise SauvegardeInvalide("L'archive est endommagée.")
        m = json.loads(z.read("manifest.json"))
        if int(m.get("schema", 0)) > SCHEMA_VERSION:
            raise SauvegardeInvalide("Cette sauvegarde vient d'une version plus récente de l'application.")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(z.extract(NOM_DB, tmp))
            if m.get("sha256_base") and _sha256(db) != m["sha256_base"]:
                raise SauvegardeInvalide("L'archive est endommagée.")
            con = sqlite3.connect(db)
            try:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SauvegardeInvalide("La base de données de l'archive est corrompue.")
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            except sqlite3.DatabaseError:
                raise SauvegardeInvalide("La base de données de l'archive est corrompue.")
            finally:
                con.close()
        if not TABLES_REQUISES <= tables:
            raise SauvegardeInvalide("La base de données de l'archive est incomplète.")
    return m


def restaurer(nom: str) -> dict:
    """Restaure une archive (après vérification et sauvegarde de sécurité de l'état actuel)."""
    from . import db as base
    f = chemin(nom)
    manifest = verifier(f)
    securite = creer("avant_restauration")
    MAINTENANCE.set()
    try:
        with _VERROU, tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(f) as z:
                z.extractall(tmp)
            base.engine.dispose()                                    # ferme toutes les connexions
            for suffixe in ("", "-wal", "-shm"):
                p = config.DATA_DIR / f"{NOM_DB}{suffixe}"
                if p.exists():
                    p.unlink()
            shutil.copy2(Path(tmp) / NOM_DB, _db())
            if config.IMAGES_DIR.exists():
                shutil.rmtree(config.IMAGES_DIR)
            if (Path(tmp) / "images").exists():
                shutil.copytree(Path(tmp) / "images", config.IMAGES_DIR)
            else:
                config.IMAGES_DIR.mkdir(parents=True)
        base.init_db()                                               # migration si sauvegarde plus ancienne
    finally:
        MAINTENANCE.clear()
    return {"restauree": nom, "manifeste": manifest, "sauvegarde_de_securite": securite["nom"]}


def importer(contenu: bytes) -> str:
    """Enregistre une archive envoyée par l'utilisateur (après vérification)."""
    REP.mkdir(parents=True, exist_ok=True)
    cible = REP / _nouveau_nom("importee")
    cible.write_bytes(contenu)
    try:
        verifier(cible)
    except Exception:
        cible.unlink(missing_ok=True)
        raise
    return cible.name


def supprimer(nom: str) -> None:
    chemin(nom).unlink()


def automatique(maintenant: datetime | None = None) -> dict | None:
    """Une sauvegarde par jour au plus ; garde les GARDER_AUTO plus récentes."""
    maintenant = maintenant or datetime.now()
    if not _db().exists():
        return None
    con = sqlite3.connect(_db())
    try:
        n_util = con.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
    except sqlite3.OperationalError:
        n_util = 0
    finally:
        con.close()
    if n_util == 0:
        return None
    autos = sorted(REP.glob("*_auto.zip")) if REP.exists() else []
    if autos:
        derniere = datetime.strptime(autos[-1].name[:17], "%Y-%m-%d_%H%M%S")
        if maintenant - derniere < timedelta(hours=24):
            return None
    info = creer("auto")
    autos = sorted(REP.glob("*_auto.zip"))
    for vieux in autos[:-GARDER_AUTO]:
        vieux.unlink()
    return info
