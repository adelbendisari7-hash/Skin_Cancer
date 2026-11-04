"""Configuration de l'application (modifiable par variables d'environnement DERMIA_*)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]                      # .../application

NOM_PRODUIT = os.environ.get("DERMIA_NOM", "dermIA")
DATA_DIR = Path(os.environ.get("DERMIA_DONNEES", APP_DIR / "donnees"))
BUNDLE_DIR = Path(os.environ.get("DERMIA_MODELE", APP_DIR / "modeles" / "ham10000-bcn20000-m5-v3"))
FRONTEND_DIR = Path(os.environ.get("DERMIA_INTERFACE", APP_DIR / "frontend" / "dist"))
HOTE = os.environ.get("DERMIA_HOTE", "127.0.0.1")                  # local uniquement par défaut
PORT = int(os.environ.get("DERMIA_PORT", "8765"))
DEVICE = os.environ.get("DERMIA_DEVICE")                           # "cuda" / "cpu" (auto si absent)
DUREE_SESSION_H = int(os.environ.get("DERMIA_SESSION_H", "10"))
# Origines supplémentaires autorisées pour les requêtes modifiantes (ex. serveur de dev Vite)
ORIGINES_AUTORISEES = {o.strip().rstrip("/") for o in os.environ.get("DERMIA_ORIGINES", "").split(",") if o.strip()}

SAUVEGARDE_AUTO = os.environ.get("DERMIA_SAUVEGARDE_AUTO", "1") != "0"   # sauvegarde quotidienne

IMAGES_DIR = DATA_DIR / "images"
DB_URL = os.environ.get("DERMIA_DB", f"sqlite:///{(DATA_DIR / 'dermia.sqlite').as_posix()}")
TAILLE_MAX_IMAGE = 15 * 1024 * 1024                                # 15 Mo
FORMATS_IMAGE = {"JPEG", "PNG", "TIFF", "BMP", "WEBP"}


def secret_key() -> str:
    """Clé de signature des sessions, créée au premier lancement et conservée localement."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = DATA_DIR / "cle_secrete.txt"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()
