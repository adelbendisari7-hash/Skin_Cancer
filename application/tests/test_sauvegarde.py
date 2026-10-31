"""Tests de la sauvegarde / restauration (dossier de données temporaire des tests)."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import func, select

from dermia import config, sauvegarde
from dermia.db import Patient, SessionLocal, Utilisateur, init_db
from dermia.security import hacher


@pytest.fixture(scope="module", autouse=True)
def base():
    init_db()
    with SessionLocal() as s:
        if not s.scalar(select(func.count(Utilisateur.id))):
            s.add(Utilisateur(identifiant="test.sauvegarde", nom_complet="Test", role="admin",
                              mot_de_passe=hacher("Sauvegarde2026x")))
        s.commit()
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def nb_patients() -> int:
    with SessionLocal() as s:
        return s.scalar(select(func.count(Patient.id)))


def test_aller_retour():
    img = config.IMAGES_DIR / "test-sauvegarde_image.png"
    Image.new("RGB", (40, 30), (120, 80, 60)).save(img)
    avant = nb_patients()
    info = sauvegarde.creer("manuelle")
    assert info["n_patients"] == avant and (sauvegarde.REP / info["nom"]).exists()
    # modifications après la sauvegarde
    with SessionLocal() as s:
        s.add(Patient(code=f"P-TEST-{datetime.now():%H%M%S%f}", sexe="female"))
        s.commit()
    img.unlink()
    assert nb_patients() == avant + 1
    res = sauvegarde.restaurer(info["nom"])
    assert nb_patients() == avant                                  # état de la sauvegarde retrouvé
    assert img.exists()                                            # image restaurée
    assert (sauvegarde.REP / res["sauvegarde_de_securite"]).exists()
    assert not sauvegarde.MAINTENANCE.is_set()


def test_zip_slip_refuse(tmp_path):
    f = tmp_path / "piege.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("manifest.json", json.dumps({"schema": 2}))
        z.writestr("dermia.sqlite", b"x")
        z.writestr("../../evil.txt", "pirate")
    with pytest.raises(sauvegarde.SauvegardeInvalide):
        sauvegarde.verifier(f)


def test_base_corrompue_refusee(tmp_path):
    f = tmp_path / "corrompue.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("manifest.json", json.dumps({"schema": 2}))
        z.writestr("dermia.sqlite", b"ceci n'est pas une base sqlite" * 100)
    with pytest.raises(sauvegarde.SauvegardeInvalide):
        sauvegarde.verifier(f)


def test_version_future_refusee():
    info = sauvegarde.creer("manuelle")
    f = sauvegarde.REP / info["nom"]
    g = f.with_name(f.stem + "_futur.zip")
    with zipfile.ZipFile(f) as src, zipfile.ZipFile(g, "w") as dst:
        for n in src.namelist():
            data = src.read(n)
            if n == "manifest.json":
                m = json.loads(data); m["schema"] = 99; data = json.dumps(m).encode()
            dst.writestr(n, data)
    with pytest.raises(sauvegarde.SauvegardeInvalide):
        sauvegarde.verifier(g)
    g.unlink()


def test_nom_invalide():
    with pytest.raises(sauvegarde.SauvegardeInvalide):
        sauvegarde.chemin("../dermia.sqlite")


def test_automatique_quotidienne_et_retention():
    for f in sauvegarde.REP.glob("*_auto.zip"):
        f.unlink()
    t0 = datetime(2030, 1, 1, 8, 0, 0)
    for j in range(9):                                             # 9 anciennes sauvegardes automatiques
        (sauvegarde.REP / f"{(t0 - timedelta(days=10 - j)):%Y-%m-%d_%H%M%S}_auto.zip").write_bytes(b"PK")
    assert sauvegarde.automatique(maintenant=t0) is not None        # dernière > 24 h → nouvelle sauvegarde
    assert len(list(sauvegarde.REP.glob("*_auto.zip"))) == sauvegarde.GARDER_AUTO
