# Plan de la version 2 — propositions 5, 6, 7, 8, 9, 11, 12

## Principes

- Chaque fonction a ses tests automatiques ; la suite complète (moteur, API, interface) doit passer avant la vidéo.
- Rien n'est réglé sur le jeu de test : choix sur la validation, mesure finale une seule fois.
- Les chiffres affichés dans l'application viennent d'exécutions réelles ; les limites sont écrites.
- Compatibilité : une base de la version 1 est migrée automatiquement (colonnes et tables ajoutées).

## Ordre d'exécution (dépendances)

| Phase | Contenu | Dépend de |
|---|---|---|
| 1 | **12 — Modèle plus puissant** : EfficientNet-B2 en 288 px (FiLM + coût, et variante robuste au contexte manquant), 3 graines chacune, entraînement en arrière-plan sur le GPU | — |
| 2 | Base de données v2 + migration automatique | — |
| 3 | **11 — Critères ABCD(E)** : segmentation classique de la lésion, A asymétrie, B bords, C couleurs, D diamètre (si l'échelle du dermoscope est connue) ; validation sur le jeu de test HAM10000 | — |
| 4 | **7 — Images hors sujet** : distance de Mahalanobis dans l'espace des caractéristiques (Lee et al., 2018), seuil fixé sur la validation ; refus expliqué, « analyser quand même » tracé dans le journal | moteur |
| 5 | **6 — Suivi d'une lésion** : entité « lésion », chronologie, comparaison de deux analyses, signaux d'évolution (critère E) | 2, 3 |
| 6 | **5 — Recalibrage local** : seuils conformes Mondrian et seuil mélanome recalculés sur les cas validés de l'établissement (case « confirmé par histologie »), garde-fous d'effectifs, estimation de couverture par validation croisée, application / retour à l'origine par l'administrateur ; expérience « autre dermoscope » simulée | 2 |
| 7 | **8 — Sauvegarde / restauration** : archive ZIP cohérente (API de sauvegarde SQLite + images + manifeste), sauvegarde automatique quotidienne (7 conservées), restauration contrôlée (intégrité, anti « zip-slip », sauvegarde de sécurité préalable) | 2 |
| 8 | **9 — Français / anglais / arabe** : dictionnaires complets vérifiés à la compilation, arabe de droite à gauche, police arabe embarquée, messages du serveur et compte rendu PDF traduits | 3–7 |
| 9 | Fin de l'entraînement : comparaison B2 / B0 sur la validation (règle fixée avant : B2 retenu si F1 macro ET AUC macro de validation de l'ensemble sont au moins égaux), mesure test, nouveau paquet de modèle (+ statistiques hors sujet), nouvelle référence de non-régression | 1, 4 |
| 10 | Données de démonstration v2, revue visuelle des écrans dans les 3 langues, corrections | tout |
| 11 | Vidéo complète de l'application | tout |

## Statut (2026-10-18)

Toutes les phases sont terminées et testées (70 tests automatiques, GPU et processeur). Résultats chiffrés et limites : `docs/resultats_v2.md`. Vidéos : `docs/video/visite_complete_dermia.mp4` (3 min 12) et `docs/video/tutoriel_dermia.mp4` (1 min 29). Captures : `docs/captures/v2/`.
