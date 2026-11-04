"""Exporte un instantané de l'instance de démonstration pour la démonstration en ligne (lecture seule, Vercel).

Toutes les données viennent des vraies réponses de l'API et du vrai moteur d'IA, sur une COPIE de donnees_demo.
Écrit dans frontend/demo-statique/ : donnees.json, images réduites (JPEG), comptes rendus PDF des cas présentés.
Images issues de HAM10000 (CC BY-NC 4.0) : démonstration non commerciale, attribution dans l'interface.

Usage (application arrêtée) : python outils/exporter_demo_statique.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from PIL import Image

ICI = Path(__file__).resolve().parent
APP = ICI.parent
SOURCE = APP / "donnees_demo"
SORTIE = APP / "frontend" / "demo-statique"
ATTRIBUTION = """Images dermoscopiques : jeu de données HAM10000
Tschandl P., Rosendahl C., Kittler H. The HAM10000 dataset, a large collection of multi-source dermatoscopic
images of common pigmented skin lesions. Sci Data 5, 180161 (2018). doi:10.1038/sdata.2018.161
Licence : CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/) — usage non commercial.
Modifications : images réduites et converties en JPEG ; cartes Grad-CAM et contours ABCD calculés par l'application.

Modèle d'IA (version 3) entraîné sur HAM10000 et sur BCN20000 :
Hernández-Pérez C. et al. BCN20000: Dermoscopic Lesions in the Wild. Sci Data 11, 641 (2024).
doi:10.1038/s41597-024-03387-w — Licence CC BY-NC 4.0 (archive ISIC) — usage non commercial.
"""


def jpeg(source: Path, cible: Path, cote: int, qualite: int) -> None:
    with Image.open(source) as im:
        im = im.convert("RGB")
        im.thumbnail((cote, cote), Image.LANCZOS)
        im.save(cible, "JPEG", quality=qualite, optimize=True, progressive=True)


def main() -> None:
    copie = Path(tempfile.mkdtemp(prefix="dermia_export_")) / "donnees"
    shutil.copytree(SOURCE, copie)
    debut = datetime.now(timezone.utc).isoformat()
    os.environ["DERMIA_DONNEES"] = str(copie)
    os.environ["DERMIA_SAUVEGARDE_AUTO"] = "0"
    sys.path.insert(0, str(APP / "backend"))

    from fastapi.testclient import TestClient

    from dermia import config, service
    from dermia.db import Analyse, SessionLocal, parametre
    from dermia.main import app
    from dermia.pdf import compte_rendu_pdf

    # modele/ vient de src/export_onnx.py : seul le contenu de l'instantané est remplacé
    for dossier in ("images", "pdf"):
        shutil.rmtree(SORTIE / dossier, ignore_errors=True)
    (SORTIE / "images").mkdir(parents=True)
    (SORTIE / "pdf").mkdir()

    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.post("/api/connexion", json={"identifiant": "admin", "mot_de_passe": "Demo2026admin"}).raise_for_status()

        def toutes(chemin: str) -> list[dict]:
            out, page = [], 1
            while True:
                d = c.get(chemin, params={"page": page, "taille": 100}).json()
                out += d["elements"]
                if len(out) >= d["total"]:
                    return out
                page += 1

        patients, analyses = toutes("/api/patients"), toutes("/api/analyses")
        journal = [j for j in c.get("/api/journal", params={"taille": 200}).json()["elements"] if j["le"] < debut]
        lesions = {str(p["id"]): c.get(f"/api/patients/{p['id']}/lesions").json() for p in patients}
        details = {}
        for liste in lesions.values():
            for les in liste:
                d = c.get(f"/api/lesions/{les['id']}").json()
                ids = [a["id"] for a in d["analyses"]]
                paires = {f"{min(a, b)}-{max(a, b)}": c.get(f"/api/lesions/{les['id']}", params={"a": a, "b": b}).json()["comparaison"]
                          for a, b in combinations(ids, 2)}
                details[str(les["id"])] = {"lesion": d["lesion"], "patient_code": d["patient_code"], "ids": ids,
                                           "defaut": d["comparaison"], "paires": paires}

        # Cas présentés en détail : tout ce qui n'est pas l'historique validé (patients HIST-xxxx)
        historique = {p["id"] for p in patients if (p["reference_externe"] or "").startswith("HIST-")}
        presentes = [a["id"] for a in analyses if a["patient_id"] not in historique]
        etsi = {f"{i}_{v}": c.post(f"/api/analyses/{i}/et-si", json={"variable": v}).json()
                for i in presentes for v in ("age", "localisation")}

        donnees = {
            "etat": c.get("/api/etat").json(), "moi": c.get("/api/moi").json(),
            "tableau": c.get("/api/tableau-de-bord").json(), "patients": patients, "analyses": analyses,
            "lesions": lesions, "details": details, "etsi": etsi, "fiche": c.get("/api/modele").json(),
            "parametres": c.get("/api/parametres").json(), "utilisateurs": c.get("/api/utilisateurs").json(),
            "journal": journal, "recalibrage": c.get("/api/recalibrage").json(),
            "sauvegardes": [{k: v for k, v in x.items() if k != "application"} for x in c.get("/api/sauvegardes").json()], "pdf": presentes,
        }

        with SessionLocal() as s:
            etab = parametre(s, "nom_etablissement")
            for a in analyses:
                detail = a["id"] in presentes
                cote, qualite = (640, 82) if detail else (320, 72)
                orm = s.get(Analyse, a["id"])
                for nature in ("image", "gradcam", "abcd"):
                    src = config.IMAGES_DIR / f"{orm.uid}_{nature}.png"
                    if src.exists():
                        jpeg(src, SORTIE / "images" / f"{a['id']}_{nature}.jpg", cote, qualite)
                if detail:
                    im = lambda n: SORTIE / "images" / f"{a['id']}_{n}.jpg"  # noqa: E731
                    for lg in ("fr", "en", "ar"):
                        pdf = compte_rendu_pdf(orm, etab, im("image"), im("gradcam"), im("abcd"), service.moteur().m, lg)
                        (SORTIE / "pdf" / f"{a['id']}_{lg}.pdf").write_bytes(pdf)

    (SORTIE / "donnees.json").write_text(json.dumps(donnees, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SORTIE / "LICENCE-IMAGES.txt").write_text(ATTRIBUTION, encoding="utf-8")
    shutil.rmtree(copie.parent, ignore_errors=True)
    taille = sum(f.stat().st_size for f in SORTIE.rglob("*") if f.is_file()) / 1e6
    print(f"Instantané écrit : {SORTIE} — {len(analyses)} analyses, {len(presentes)} présentées, {taille:.1f} Mo")


if __name__ == "__main__":
    main()
