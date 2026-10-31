"""Texte de la voix off de la vidéo de présentation, et génération de l'audio (edge-tts).

Public : médecins et responsables de clinique. Chaque chiffre vient de la fiche du modèle (test HAM10000).
Usage : python outils/narration_presentation.py → docs/video/voix/<scene>.mp3 et durees.json
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

VOIX = "fr-FR-VivienneMultilingualNeural"
SORTIE = Path(__file__).resolve().parent.parent / "docs" / "video" / "voix"

SCENES = {
    "intro": "Face à une lésion cutanée, le médecin doit décider vite : surveiller, ou adresser à un spécialiste. "
             "DermIA Prudence l'aide à faire ce tri, sans jamais décider à sa place.",
    "connexion": "L'outil s'ouvre dans un simple navigateur, en français, en anglais ou en arabe.",
    "file": "Le médecin retrouve d'abord sa file de travail. Les cas les plus graves sont en tête, et un badge signale "
            "les lésions qui ont changé depuis le dernier examen.",
    "nouvelle": "Pour une nouvelle analyse, il choisit le patient, dépose l'image prise au dermoscope et indique la "
                "localisation sur le schéma du corps. Dans cette démonstration, tout le calcul se fait sur l'ordinateur "
                "du médecin : l'image n'est envoyée à aucun serveur.",
    "resultat": "Quelques secondes plus tard, le résultat apparaît. L'outil propose une orientation claire, ici une "
                "suspicion de mélanome, avec les probabilités de sept diagnostics et un seuil d'alerte réglé pour "
                "limiter les mélanomes manqués.",
    "explication": "Le médecin voit où l'intelligence artificielle a regardé. Il dispose aussi des critères A, B, C, D, "
                   "mesurés automatiquement sur le contour de la lésion.",
    "prudence": "Sa particularité, c'est la prudence. Quand plusieurs diagnostics restent plausibles, l'outil s'abstient "
                "et renvoie le cas au médecin.",
    "hors_sujet": "Et si l'image n'est pas une dermoscopie, il la refuse, plutôt que de répondre au hasard.",
    "suivi": "Chaque lésion est suivie dans le temps : chronologie des examens, comparaison avant et après, et signaux "
             "d'évolution.",
    "validation": "Le médecin valide ou corrige le résultat. Un compte rendu est alors prêt à signer, en français, en "
                  "anglais ou en arabe.",
    "administration": "L'établissement garde la main : gestion des comptes, journal d'audit, sauvegarde en un clic, et "
                      "recalibrage des seuils sur ses propres cas, avec une recommandation prudente.",
    "chiffres": "Les performances sont publiées avec leurs limites. Sur mille neuf images de test jamais vues par le "
                "modèle, quatre-vingt-douze pour cent des mélanomes sont signalés, au prix d'une fausse alerte pour près "
                "d'une lésion non mélanome sur quatre.",
    "fin": "Cette version est une démonstration. Ce n'est pas un dispositif médical, et son modèle, entraîné sur des "
           "données à usage non commercial, devra être réentraîné et validé cliniquement avant tout usage réel. "
           "Pour la découvrir : dermia-prudence point vercel point app.",
}


async def generer() -> dict[str, float]:
    SORTIE.mkdir(parents=True, exist_ok=True)
    durees = {}
    for nom, texte in SCENES.items():
        f = SORTIE / f"{nom}.mp3"
        await edge_tts.Communicate(texte, VOIX, rate="-4%").save(str(f))
        d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                           capture_output=True, text=True, check=True).stdout
        durees[nom] = round(float(d), 2)
    (SORTIE / "durees.json").write_text(json.dumps(durees, indent=1), encoding="utf-8")
    return durees


if __name__ == "__main__":
    d = asyncio.run(generer())
    print(d, "total", round(sum(d.values()), 1), "s")
