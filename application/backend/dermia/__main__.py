"""Lancement local : `python -m dermia` démarre le serveur et ouvre le navigateur."""
from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn

from . import config


def main() -> None:
    url = f"http://{config.HOTE}:{config.PORT}"
    print(f"\n  {config.NOM_PRODUIT} — démarrage sur {url}\n  (fermez cette fenêtre pour arrêter l'application)\n")
    if os.environ.get("DERMIA_NAVIGATEUR", "1") != "0":          # DERMIA_NAVIGATEUR=0 : ne pas ouvrir le navigateur
        threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(url)), daemon=True).start()
    uvicorn.run("dermia.main:app", host=config.HOTE, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
