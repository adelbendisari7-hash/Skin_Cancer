"""Crée l'instance de DÉMONSTRATION (dossier donnees_demo) en pilotant l'application elle-même.

Tout passe par l'API réelle et le vrai moteur d'IA ; seule l'horloge du serveur est avancée pas à pas
pour étaler les analyses sur douze mois (suivi de lésions, tableau de bord, recalibrage).

Contenu :
- un « historique » d'environ 400 lésions du jeu de TEST HAM10000 (une image par lésion, jamais vue à
  l'entraînement), analysées puis validées avec le diagnostic de référence → base du recalibrage local ;
- des lésions suivies dans le temps (plusieurs images d'une même lésion HAM10000, datées à plusieurs mois
  d'intervalle), des analyses en attente de validation, une image hors sujet refusée puis forcée ;
- une proposition de recalibrage (non appliquée) et une sauvegarde.

Les images HAM10000 sont sous licence CC BY-NC 4.0 : démonstrations non commerciales uniquement.
Les dates et l'ordre des images d'une même lésion sont mis en scène : ce ne sont pas des suivis réels.
Comptes : admin / Demo2026admin et k.haddad / Demo2026medecin (à ne jamais utiliser en production).

Usage : python outils/creer_demo.py [--dossier donnees_demo] [--remplacer] [--historique 420]
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ICI = Path(__file__).resolve().parent
APP = ICI.parent
HAM = APP.parents[1] / "HAM10000"
SPLIT = APP.parent / "resultats" / "split_lesions.csv"
MALINS = {"mel", "bcc", "akiec"}
# Noms donnés par le médecin aux lésions suivies, cohérents avec la localisation HAM10000 de l'image
NOMS_LESIONS = {"back": "dos, sous l'omoplate gauche", "chest": "thorax, région sternale", "abdomen": "flanc droit",
                "trunk": "tronc, région lombaire", "upper extremity": "avant-bras droit", "lower extremity": "jambe gauche",
                "face": "tempe gauche", "scalp": "cuir chevelu, vertex", "neck": "cou, face latérale",
                "hand": "dos de la main", "foot": "plante du pied", "ear": "pavillon de l'oreille"}


class _Horloge:
    instant: datetime | None = None


class _DateDemo(datetime):
    """datetime dont `now()` renvoie l'instant choisi par le script (horloge du serveur de démonstration)."""

    @classmethod
    def now(cls, tz=None):
        if _Horloge.instant is None:
            return datetime.now(tz)
        return _Horloge.instant if tz else _Horloge.instant.astimezone().replace(tzinfo=None)


def lire_metadonnees() -> dict[str, dict]:
    with open(HAM / "HAM10000_metadata.csv", encoding="utf-8") as f:
        meta = {r["image_id"]: r for r in csv.DictReader(f)}
    with open(SPLIT, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            meta[r["image_id"]]["split"] = r["split"]
    for r in meta.values():
        r["chemin"] = next(p for p in (HAM / "HAM10000_images_part_1" / f"{r['image_id']}.jpg",
                                       HAM / "HAM10000_images_part_2" / f"{r['image_id']}.jpg") if p.exists())
    return meta


def capture_ecran() -> bytes:
    """Image manifestement hors sujet : capture d'écran factice d'un tableur."""
    im = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 900, 56], fill=(33, 115, 70))
    for i in range(16):
        d.line([(0, 90 + 30 * i), (900, 90 + 30 * i)], fill=(210, 210, 210))
    for j in range(6):
        d.line([(60 + 140 * j, 60), (60 + 140 * j, 600)], fill=(210, 210, 210))
        for i in range(15):
            d.rectangle([70 + 140 * j, 98 + 30 * i, 70 + 140 * j + (37 * (i + j)) % 100, 108 + 30 * i], fill=(40, 40, 40))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", default="donnees_demo")
    ap.add_argument("--remplacer", action="store_true")
    ap.add_argument("--historique", type=int, default=420, help="nombre de lésions validées (jeu de test)")
    args = ap.parse_args()
    dossier = Path(args.dossier) if Path(args.dossier).is_absolute() else APP / args.dossier
    if dossier.exists():
        if not args.remplacer:
            raise SystemExit(f"{dossier} existe déjà : ajoutez --remplacer pour le recréer.")
        shutil.rmtree(dossier)
    os.environ["DERMIA_DONNEES"] = str(dossier)
    os.environ["DERMIA_SAUVEGARDE_AUTO"] = "0"
    sys.path.insert(0, str(APP / "backend"))

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    import dermia.api.analyses as api_analyses
    from dermia import service
    from dermia.db import Analyse, Lesion, SessionLocal
    from dermia.engine import Contexte
    from dermia.main import app

    api_analyses.datetime = _DateDemo
    maintenant = datetime.now(timezone.utc).replace(microsecond=0)
    meta = lire_metadonnees()
    rng = random.Random(7)
    par_lesion: dict[str, list[dict]] = defaultdict(list)
    for r in meta.values():
        par_lesion[r["lesion_id"]].append(r)

    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        def entrer(identifiant: str, mdp: str) -> None:
            c.post("/api/connexion", json={"identifiant": identifiant, "mot_de_passe": mdp}).raise_for_status()

        def patient(annee: int | None, sexe: str, ref: str) -> dict:
            r = c.post("/api/patients", json={"annee_naissance": annee, "sexe": sexe, "reference_externe": ref})
            r.raise_for_status()
            return r.json()

        def analyser(p: dict, r: dict, quand: datetime, **extra) -> dict | None:
            _Horloge.instant = quand
            donnees = {"patient_id": p["id"], "localisation": r["localization"] or "unknown", "sexe": r["sex"]}
            if r["age"]:
                donnees["age"] = r["age"]
            donnees.update({k: str(v) for k, v in extra.items()})
            rep = c.post("/api/analyses", data=donnees,
                         files={"image": (f"{r['image_id']}.jpg", r["chemin"].read_bytes(), "image/jpeg")})
            if rep.status_code == 422 and isinstance(rep.json().get("detail"), dict):
                return None                                  # image refusée par le détecteur hors sujet
            rep.raise_for_status()
            return rep.json()

        def annee(r: dict, quand: datetime) -> int | None:
            return quand.year - int(float(r["age"])) if r["age"] else None

        # ---- installation et comptes
        _Horloge.instant = maintenant - timedelta(days=380)
        c.post("/api/installation", json={"identifiant": "admin", "nom_complet": "Dr Amina Benali",
                                          "mot_de_passe": "Demo2026admin",
                                          "nom_etablissement": "Cabinet de dermatologie Es-Senia"}).raise_for_status()
        c.post("/api/utilisateurs", json={"identifiant": "k.haddad", "nom_complet": "Dr Karim Haddad",
                                          "role": "medecin", "mot_de_passe": "Demo2026medecin"}).raise_for_status()
        c.put("/api/parametres", json={"champ_dermoscope_mm": 15}).raise_for_status()
        c.post("/api/deconnexion")
        entrer("k.haddad", "Demo2026medecin")

        # ---- historique validé (jeu de test, une image par lésion), étalé sur 12 mois
        lesions_test = sorted({r["lesion_id"] for r in meta.values() if r["split"] == "test"})
        historique = rng.sample(lesions_test, min(args.historique, len(lesions_test)))
        dates = sorted(maintenant - timedelta(days=rng.uniform(20, 365), hours=rng.uniform(0, 9)) for _ in historique)
        refusees = 0
        for k, (lid, quand) in enumerate(zip(historique, dates)):
            r = sorted(par_lesion[lid], key=lambda x: x["image_id"])[0]
            p = patient(annee(r, quand), r["sex"], f"HIST-{k + 1:04d}")
            a = analyser(p, r, quand)
            if a is None:
                refusees += 1
                continue
            _Horloge.instant = quand + timedelta(days=rng.randint(2, 12))
            corrige = a["decision"] != r["dx"]
            c.post(f"/api/analyses/{a['id']}/revue", json={
                "revue": "corrigee" if corrige else "confirmee", "diagnostic_final": r["dx"] if corrige else None,
                "histologie": r["dx"] in MALINS,
                "commentaire": "Exérèse, résultat anatomopathologique reçu." if r["dx"] in MALINS else None,
            }).raise_for_status()
            if (k + 1) % 50 == 0:
                print(f"  historique : {k + 1}/{len(historique)}")
        print(f"Historique validé : {len(historique) - refusees} analyses ({refusees} image(s) refusée(s) hors sujet).")

        utilisees = set(historique)
        libres = {lid: imgs for lid, imgs in par_lesion.items()
                  if lid not in utilisees and imgs[0]["split"] in ("test", "calib", "val")}

        # ---- lésions suivies : plusieurs images d'une même lésion, ordonnées par p(mélanome) croissante
        m = service.moteur()

        def p_mel(r: dict) -> float:
            ctx = Contexte(float(r["age"]) if r["age"] else None, r["sex"], r["localization"])
            res, _ = m.analyser(Image.open(r["chemin"]), ctx)
            return res.p_melanome

        def candidate(dx: str, ecart_min: float, n_min: int) -> tuple[str, list[dict]]:
            ordre = sorted(libres, key=lambda x: rng.random())
            for n in range(n_min, 1, -1):                    # au besoin, accepte moins d'images
                for lid in ordre:
                    imgs = libres.get(lid)
                    if not imgs or imgs[0]["dx"] != dx or len(imgs) < n:
                        continue
                    notes = sorted(((p_mel(r), r) for r in imgs[:4]), key=lambda x: x[0])
                    if notes[-1][0] - notes[0][0] >= ecart_min:
                        del libres[lid]
                        garde = [notes[0][1], *[r for _, r in notes[1:-1]][:max(n - 2, 0)], notes[-1][1]]
                        return lid, garde[:3]
            raise SystemExit(f"aucune lésion {dx} adaptée")

        suivis = [("mel", 0.15, 3, [200, 95, 4]), ("nv", 0.0, 2, [240, 6]), ("bkl", 0.0, 2, [150, 2])]
        patients_suivis = []
        for dx, ecart, n_min, jours in suivis:
            lid, imgs = candidate(dx, ecart, n_min)
            debut = maintenant - timedelta(days=jours[0], hours=3)
            p = patient(annee(imgs[0], debut), imgs[0]["sex"], f"DOS-{rng.randint(1100, 1999)}")
            patients_suivis.append(p)
            lesion_id = None
            for r, j in zip(imgs, jours[-len(imgs):]):          # la dernière image est la plus récente
                quand = maintenant - timedelta(days=j, hours=rng.uniform(1, 6))
                a = analyser(p, r, quand, **({"lesion_id": lesion_id} if lesion_id else {}))
                if a is None:
                    continue
                lesion_id = a["lesion_id"]
                if j > 30:                                   # examens anciens : déjà validés
                    _Horloge.instant = quand + timedelta(days=1)
                    c.post(f"/api/analyses/{a['id']}/revue", json={"revue": "confirmee"}).raise_for_status()
            nom = NOMS_LESIONS.get(imgs[0]["localization"])
            if nom:
                c.patch(f"/api/lesions/{lesion_id}", json={"nom": nom}).raise_for_status()
            print(f"Lésion suivie ({dx}) : {len(imgs)} images, lésion {lesion_id}")

        # ---- analyses récentes en attente de validation (une par diagnostic, quelques patients)
        recents = []
        for dx in ["mel", "bcc", "akiec", "nv", "bkl", "vasc", "df", "mel", "nv"]:
            lid = next(lid for lid in sorted(libres, key=lambda x: rng.random()) if libres[lid][0]["dx"] == dx)
            recents.append(libres.pop(lid)[0])
        for k, r in enumerate(recents):
            quand = maintenant - timedelta(days=rng.uniform(0.1, 12))
            p = patients_suivis[k] if k < 2 else patient(annee(r, quand), r["sex"], f"DOS-{rng.randint(2000, 2999)}")
            analyser(p, r, quand)

        # ---- image hors sujet : refusée, puis analysée de force (tracé dans le journal)
        _Horloge.instant = maintenant - timedelta(hours=5)
        hs = patient(1979, "female", "DOS-3104")
        champs = {"patient_id": hs["id"], "localisation": "hand", "sexe": "female", "age": "46"}
        rep = c.post("/api/analyses", data=champs, files={"image": ("capture.png", capture_ecran(), "image/png")})
        print("Image hors sujet :", rep.status_code, rep.json().get("detail", {}).get("code") if rep.status_code != 201 else "ACCEPTÉE")
        c.post("/api/analyses", data={**champs, "forcer": "true"},
               files={"image": ("capture.png", capture_ecran(), "image/png")}).raise_for_status()
        c.post("/api/deconnexion")

        # ---- administrateur : proposition de recalibrage et sauvegarde
        _Horloge.instant = maintenant - timedelta(hours=2)
        entrer("admin", "Demo2026admin")
        for profil in ("complet", "sans_contexte"):
            rep = c.post("/api/recalibrage/propositions", json={"profil": profil, "histologie_seulement": False})
            print(f"Proposition de recalibrage ({profil}) :", rep.status_code)
        _Horloge.instant = None

    # dates de création des lésions = première analyse ; puis sauvegarde (hors client : serveur arrêté)
    with SessionLocal() as s:
        premieres = dict(s.execute(select(Analyse.lesion_id, func.min(Analyse.cree_le)).group_by(Analyse.lesion_id)).all())
        for les in s.scalars(select(Lesion)).all():
            if les.id in premieres:
                les.cree_le = premieres[les.id]
        s.commit()
        n = s.scalar(select(func.count(Analyse.id)))
    from dermia import sauvegarde
    info = sauvegarde.creer("manuelle")
    print(f"Démonstration prête dans {dossier} : {n} analyses ; sauvegarde {info['nom']}.")


if __name__ == "__main__":
    main()
