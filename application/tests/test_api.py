"""Tests de bout en bout de l'API (base temporaire, vrai moteur d'IA).

Les tests s'enchaînent dans l'ordre du fichier sur la même base (fixture de module).
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from dermia import service
from dermia.db import Analyse, SessionLocal
from dermia.main import app

ICI = Path(__file__).parent
HAM_DIR = Path(os.environ.get("HAM_DIR", ICI.parents[2] / "HAM10000"))
ADMIN = {"identifiant": "admin", "nom_complet": "Dr Admin", "mot_de_passe": "Admin2026secure",
         "nom_etablissement": "Clinique de test"}
MEDECIN = {"identifiant": "dr.ali", "nom_complet": "Dr Ali", "role": "medecin", "mot_de_passe": "Medecin2026ok"}


def image_test(nom: str = "ISIC_0024306.jpg") -> bytes:
    f = HAM_DIR / "HAM10000_images_part_1" / nom
    if f.exists():
        return f.read_bytes()
    buf = io.BytesIO()
    Image.new("RGB", (600, 450), (170, 110, 100)).save(buf, "JPEG")
    return buf.getvalue()


def image_hors_sujet() -> bytes:
    """Capture d'écran factice : fond blanc, bandeau bleu, lignes de texte noires."""
    im = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 800, 70], fill=(30, 80, 200))
    for i in range(14):
        d.rectangle([40, 110 + 32 * i, 40 + (i * 53) % 500 + 200, 124 + 32 * i], fill=(20, 20, 20))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def connecter(c: TestClient, ident: dict):
    r = c.post("/api/connexion", json={"identifiant": ident["identifiant"], "mot_de_passe": ident["mot_de_passe"]})
    assert r.status_code == 200, r.text


def analyser(c: TestClient, pid: int, **champs) -> dict:
    image = champs.pop("image", None) or image_test()
    r = c.post("/api/analyses", data={"patient_id": pid, **champs}, files={"image": ("lesion.jpg", image, "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def test_parcours_complet(client: TestClient):
    c = client
    etat = c.get("/api/etat").json()
    assert etat["installation_requise"] and etat["modele"]["charge"]

    # installation : mot de passe faible refusé, puis création de l'administrateur
    assert c.post("/api/installation", json={**ADMIN, "mot_de_passe": "court"}).status_code == 422
    assert c.post("/api/installation", json=ADMIN).status_code == 200
    assert c.post("/api/installation", json=ADMIN).status_code == 409
    assert c.get("/api/moi").json()["role"] == "admin"

    # gestion des utilisateurs
    assert c.post("/api/utilisateurs", json=MEDECIN).status_code == 201
    assert c.post("/api/utilisateurs", json=MEDECIN).status_code == 409
    c.post("/api/deconnexion")
    assert c.get("/api/moi").status_code == 401
    assert c.post("/api/connexion", json={"identifiant": "dr.ali", "mot_de_passe": "faux"}).status_code == 401
    connecter(c, MEDECIN)
    assert c.post("/api/utilisateurs", json={**MEDECIN, "identifiant": "x.y"}).status_code == 403
    assert c.get("/api/journal").status_code == 403

    # patient pseudonymisé
    r = c.post("/api/patients", json={"annee_naissance": 1961, "sexe": "male", "reference_externe": "DOS-42"})
    assert r.status_code == 201
    patient = r.json()
    assert patient["code"] == f"P-{datetime.now().year}-0001"
    assert c.get("/api/patients", params={"q": "DOS-4"}).json()["total"] == 1

    # analyse : une lésion est créée automatiquement, critères ABCD calculés
    a = analyser(c, patient["id"], localisation="back")
    assert a["profil"] == "complet" and abs(sum(a["probabilites"].values()) - 1) < 1e-4
    assert a["age"] == datetime.now().year - 1961                   # âge déduit de l'année de naissance
    assert a["statut"] in {"alerte_melanome", "maligne_probable", "benigne_probable", "incertain"}
    assert a["lesion_id"] and a["lesion_numero"] == 1 and a["evolution"] is None
    assert a["calibration"] == "origine" and a["hors_sujet_force"] is False
    assert a["abcd"]["A"] is not None and 0 <= a["abcd"]["B"]["score"] <= 8
    assert a["abcd"]["D"]["mm"] is None                              # champ du dermoscope non renseigné
    assert a["cree_le"].endswith(("+00:00", "Z"))                     # date avec fuseau (UTC)
    for nature in ("image", "gradcam", "abcd"):
        r = c.get(f"/api/analyses/{a['id']}/image/{nature}")
        assert r.status_code == 200 and r.content[:4] == b"\x89PNG"

    # « et si » : l'âge actuel rejoue exactement l'analyse (image stockée sans perte)
    r = c.post(f"/api/analyses/{a['id']}/et-si", json={"variable": "age", "valeurs": [a["age"], 20]}).json()
    assert abs(r["serie"][0]["p_melanome"] - a["p_melanome"]) < 1e-5

    # suivi : deuxième analyse de la même lésion → comparaison avec la précédente
    b = analyser(c, patient["id"], lesion_id=a["lesion_id"], image=image_test("ISIC_0024307.jpg"))
    assert b["lesion_id"] == a["lesion_id"] and b["localisation"] == "back"   # localisation reprise de la lésion
    assert b["evolution"]["analyse_precedente"] == a["id"] and b["evolution"]["jours"] == 0
    assert any(av["code"] == "evolution" for av in b["avertissements"])
    lesions = c.get(f"/api/patients/{patient['id']}/lesions").json()
    assert len(lesions) == 1 and lesions[0]["nb_analyses"] == 2 and lesions[0]["derniere_image"] == b["id"]
    detail = c.get(f"/api/lesions/{a['lesion_id']}").json()
    assert [x["id"] for x in detail["analyses"]] == [a["id"], b["id"]]
    assert detail["comparaison"]["avant"] == a["id"] and detail["comparaison"]["apres"] == b["id"]
    r = c.patch(f"/api/lesions/{a['lesion_id']}", json={"nom": "Dos, omoplate gauche"})
    assert r.status_code == 200 and r.json()["nom"] == "Dos, omoplate gauche"
    # nouvelle lésion explicite : autre numéro ; lésion d'un autre patient refusée
    autre = c.post("/api/patients", json={"sexe": "female"}).json()
    r = c.post("/api/analyses", data={"patient_id": autre["id"], "lesion_id": a["lesion_id"]},
               files={"image": ("x.jpg", image_test(), "image/jpeg")})
    assert r.status_code == 404
    d = analyser(c, patient["id"], localisation="face")
    assert d["lesion_numero"] == 2

    # revue médicale (avec confirmation histologique)
    assert c.post(f"/api/analyses/{a['id']}/revue", json={"revue": "corrigee"}).status_code == 422
    r = c.post(f"/api/analyses/{a['id']}/revue", json={"revue": "corrigee", "diagnostic_final": "nv",
                                                       "commentaire": "Nævus banal à l'examen.", "histologie": True})
    assert r.status_code == 200 and r.json()["revue"] == "corrigee" and r.json()["relecteur"] == "Dr Ali"
    assert r.json()["histologie"] is True

    # compte rendu PDF dans les trois langues
    for lg in ("fr", "en", "ar"):
        r = c.get(f"/api/analyses/{b['id']}/compte-rendu.pdf", params={"langue": lg})
        assert r.status_code == 200 and r.content[:4] == b"%PDF", lg
        assert f"_{lg}.pdf" in r.headers["content-disposition"]
    assert c.get(f"/api/analyses/{b['id']}/compte-rendu.pdf", params={"langue": "de"}).status_code == 422
    tb = c.get("/api/tableau-de-bord").json()
    assert tb["total_analyses"] == 3 and tb["taux_accord"] == 0.0 and tb["revues_en_attente"] == 2

    # journal d'audit (administrateur)
    c.post("/api/deconnexion")
    connecter(c, ADMIN)
    actions = {e["action"] for e in c.get("/api/journal").json()["elements"]}
    assert {"installation", "connexion", "analyse_creee", "analyse_revue", "compte_rendu_exporte",
            "connexion_refusee"} <= actions

    # échelle du dermoscope renseignée → diamètre en mm
    assert c.put("/api/parametres", json={"champ_dermoscope_mm": 15}).json()["champ_dermoscope_mm"] == 15
    e = analyser(c, patient["id"], lesion_id=a["lesion_id"])
    assert e["abcd"]["D"]["mm"] is not None and e["abcd"]["D"]["mm"] > 0
    assert c.put("/api/parametres", json={"champ_dermoscope_mm": 0}).json()["champ_dermoscope_mm"] is None


def test_messages_traduits(client: TestClient):
    c = client
    connecter(c, ADMIN)
    assert c.get("/api/analyses/999999").json()["detail"] == "Analyse introuvable."
    assert c.get("/api/analyses/999999", headers={"X-Langue": "en"}).json()["detail"] == "Analysis not found."
    assert c.get("/api/analyses/999999", headers={"X-Langue": "ar"}).json()["detail"] == "التحليل غير موجود."
    assert c.get("/api/analyses/999999", headers={"X-Langue": "xx"}).json()["detail"] == "Analyse introuvable."
    r = c.post("/api/patients", json={"sexe": "female"}, headers={"Origin": "http://autre.example", "X-Langue": "en"})
    assert r.status_code == 403 and r.json()["detail"] == "Origin refused."
    c.post("/api/deconnexion")
    assert c.get("/api/moi", headers={"X-Langue": "en"}).json()["detail"] == "No session."


def test_images_hors_sujet(client: TestClient):
    c = client
    if not c.get("/api/etat").json()["modele"].get("detection_hors_sujet"):
        pytest.skip("le modèle chargé n'a pas de détecteur d'images hors sujet")
    connecter(c, MEDECIN)
    pid = c.post("/api/patients", json={"sexe": "male", "annee_naissance": 1980}).json()["id"]
    avant = c.get("/api/tableau-de-bord").json()["total_analyses"]
    r = c.post("/api/analyses", data={"patient_id": pid, "localisation": "back"},
               files={"image": ("ecran.png", image_hors_sujet(), "image/png")}, headers={"X-Langue": "en"})
    assert r.status_code == 422, r.text
    det = r.json()["detail"]
    assert det["code"] == "image_hors_sujet" and det["score"] > det["seuil"]
    assert det["message"] == "This image does not look like a dermoscopic image."
    assert c.get("/api/tableau-de-bord").json()["total_analyses"] == avant          # rien d'enregistré
    # l'utilisateur peut forcer l'analyse : elle est marquée et exclue du recalibrage
    f = analyser(c, pid, localisation="back", forcer="true", image=image_hors_sujet())
    assert f["hors_sujet_force"] is True and any(av["code"] == "image_atypique" for av in f["avertissements"])
    # une vraie image dermoscopique passe
    ok = analyser(c, pid, localisation="back")
    assert ok["hors_sujet_force"] is False and ok["score_hors_sujet"] <= det["seuil"]
    c.post("/api/deconnexion")
    connecter(c, ADMIN)
    actions = {e["action"] for e in c.get("/api/journal", params={"taille": 200}).json()["elements"]}
    assert {"image_refusee", "analyse_forcee"} <= actions


def _cas_valides(n: int, profil: str = "complet") -> None:
    """Insère n cas validés par un médecin (probabilités plausibles, diagnostics variés) dans la base."""
    m = service.moteur()
    rng = np.random.default_rng(0)
    with SessionLocal() as s:
        modele = s.get(Analyse, 1)
        for i in range(n):
            y = i % len(m.classes)
            logits = rng.normal(0, 1, len(m.classes))
            logits[y] += 3
            p = np.exp(logits) / np.exp(logits).sum()
            cols = {c.name: getattr(modele, c.name) for c in Analyse.__table__.columns
                    if c.name not in ("id", "uid", "cree_le")}
            cols.update(uid=f"test{i:04d}", probabilites={c: float(v) for c, v in zip(m.classes, p)},
                        p_melanome=float(p[m.mel]), profil=profil, revue="confirmee", diagnostic_final=m.classes[y],
                        modele=m.nom, version_modele=m.version, hors_sujet_force=False, evolution=None)
            s.add(Analyse(**cols))
        s.commit()


def test_recalibrage(client: TestClient):
    c = client
    connecter(c, MEDECIN)
    assert c.get("/api/recalibrage").status_code == 403
    connecter(c, ADMIN)
    etat = c.get("/api/recalibrage").json()
    assert etat["profils"]["complet"]["active"] is None
    r = c.post("/api/recalibrage/propositions", json={"profil": "complet"}, headers={"X-Langue": "en"})
    assert r.status_code == 422 and r.json()["detail"] == "Not enough validated cases to propose a recalibration."

    _cas_valides(140)
    etat = c.get("/api/recalibrage").json()["profils"]["complet"]
    assert etat["n_valides"] >= 140 and sum(etat["par_classe"].values()) == etat["n_valides"]
    r = c.post("/api/recalibrage/propositions", json={"profil": "complet"})
    assert r.status_code == 200, r.text
    prop = r.json()
    assert prop["active"] is False and prop["resume"]["n"] == etat["n_valides"]
    assert len(prop["parametres"]["conformal_q"]) == len(service.moteur().classes)

    pid = c.post("/api/patients", json={"sexe": "male", "annee_naissance": 1970}).json()["id"]
    assert analyser(c, pid, localisation="back")["calibration"] == "origine"     # proposition non appliquée
    assert c.post(f"/api/recalibrage/{prop['id']}/appliquer").json()["active"] is True
    assert c.get("/api/recalibrage").json()["profils"]["complet"]["active"]["id"] == prop["id"]
    assert analyser(c, pid, localisation="back")["calibration"] == f"locale:{prop['id']}"
    assert analyser(c, pid, localisation="unknown")["calibration"] == "origine"   # autre profil : inchangé
    assert c.post("/api/recalibrage/reinitialiser/complet").json()["ok"]
    assert analyser(c, pid, localisation="back")["calibration"] == "origine"
    assert c.post("/api/recalibrage/reinitialiser/inconnu").status_code == 404
    assert c.post("/api/recalibrage/99999/appliquer").status_code == 404


def test_sauvegarde_restauration(client: TestClient):
    c = client
    connecter(c, ADMIN)
    nb_patients = c.get("/api/patients").json()["total"]
    info = c.post("/api/sauvegardes").json()
    assert info["nom"].endswith(".zip") and info["n_patients"] == nb_patients
    assert info["nom"] in [s["nom"] for s in c.get("/api/sauvegardes").json()]
    archive = c.get(f"/api/sauvegardes/{info['nom']}")
    assert archive.status_code == 200 and zipfile.is_zipfile(io.BytesIO(archive.content))
    assert c.get("/api/sauvegardes/..%2Fdermia.sqlite").status_code in (404, 422)
    assert c.get("/api/sauvegardes/inexistante.zip").status_code == 404

    # import : archive invalide refusée, archive valide acceptée
    r = c.post("/api/sauvegardes/importer", files={"fichier": ("x.zip", b"pas un zip", "application/zip")})
    assert r.status_code == 422
    r = c.post("/api/sauvegardes/importer", files={"fichier": ("s.zip", archive.content, "application/zip")})
    assert r.status_code == 201
    importee = r.json()["nom"]

    # modification après la sauvegarde, puis restauration : la modification disparaît
    c.post("/api/patients", json={"sexe": "female", "reference_externe": "APRES-SAUVEGARDE"})
    assert c.get("/api/patients").json()["total"] == nb_patients + 1
    r = c.post(f"/api/sauvegardes/{importee}/restaurer")
    assert r.status_code == 200, r.text
    assert c.get("/api/moi").status_code == 401                       # reconnexion obligatoire
    connecter(c, ADMIN)
    assert c.get("/api/patients").json()["total"] == nb_patients
    assert c.get("/api/patients", params={"q": "APRES-SAUVEGARDE"}).json()["total"] == 0
    a = c.get("/api/analyses/1").json()
    assert c.get(f"/api/analyses/{a['id']}/image/image").status_code == 200      # images restaurées
    noms = [s["nom"] for s in c.get("/api/sauvegardes").json()]
    assert any("avant_restauration" in n for n in noms)               # sauvegarde de sécurité automatique
    actions = {e["action"] for e in c.get("/api/journal").json()["elements"]}
    assert "sauvegarde_restauree" in actions
    assert c.delete(f"/api/sauvegardes/{importee}").json()["ok"]
    assert importee not in [s["nom"] for s in c.get("/api/sauvegardes").json()]


def test_protections(client: TestClient):
    c = client
    connecter(c, ADMIN)
    # requête modifiante venant d'un autre site : refusée
    r = c.post("/api/patients", json={"sexe": "female"}, headers={"Origin": "http://site-malveillant.example"})
    assert r.status_code == 403
    # fichier qui n'est pas une image
    pid = c.post("/api/patients", json={"sexe": "female"}).json()["id"]
    r = c.post("/api/analyses", data={"patient_id": pid, "localisation": "face"},
               files={"image": ("x.jpg", b"pas une image", "image/jpeg")})
    assert r.status_code == 422
    # localisation inconnue
    r = c.post("/api/analyses", data={"patient_id": pid, "localisation": "lune"},
               files={"image": ("x.jpg", image_test(), "image/jpeg")})
    assert r.status_code == 422
    # contexte incomplet → profil robuste + avertissement codé
    r = c.post("/api/analyses", data={"patient_id": pid, "localisation": "unknown"},
               files={"image": ("x.jpg", image_test(), "image/jpeg")})
    assert r.status_code == 201 and r.json()["profil"] == "sans_contexte"
    assert {"code": "contexte_incomplet"} in r.json()["avertissements"]
    # limitation des tentatives de connexion
    for _ in range(5):
        c.post("/api/connexion", json={"identifiant": "inconnu", "mot_de_passe": "x"})
    assert c.post("/api/connexion", json={"identifiant": "inconnu", "mot_de_passe": "x"}).status_code == 429
