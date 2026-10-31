"""Traduction de la sortie du modèle en orientation clinique lisible (statut, niveau, message)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Triage:
    statut: str      # code stable utilisé par l'interface et la base
    niveau: str      # urgent | eleve | renvoi | faible
    titre: str
    message: str


def triage(decision: str, traite: bool, malignes: list[str], noms: dict[str, str]) -> Triage:
    """Règle de triage.

    - décision « mel » (seuil de coût franchi)          → alerte mélanome, toujours vers le médecin ;
    - cas traité, décision maligne / pré-maligne        → avis dermatologique recommandé ;
    - cas traité, décision bénigne                      → bénin probable ;
    - cas non traité (ensemble conforme ambigu)         → l'IA s'abstient, renvoi au médecin.
    """
    nom = noms.get(decision, decision)
    if decision == "mel":
        return Triage("alerte_melanome", "urgent", "Suspicion de mélanome",
                      "La probabilité de mélanome dépasse le seuil de sécurité. "
                      "Avis dermatologique rapide recommandé.")
    if not traite:
        return Triage("incertain", "renvoi", "Résultat incertain : l'IA s'abstient",
                      "Plusieurs diagnostics restent plausibles au niveau de confiance garanti. "
                      "Le cas doit être examiné par un médecin.")
    if decision in malignes:
        return Triage("maligne_probable", "eleve", f"{nom} probable",
                      "Lésion maligne ou pré-maligne probable. Avis dermatologique recommandé.")
    return Triage("benigne_probable", "faible", f"{nom} probable",
                  "Lésion bénigne probable. Suivi selon le jugement clinique ; "
                  "tout changement de la lésion justifie un nouvel examen.")
