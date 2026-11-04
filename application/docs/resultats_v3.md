# Version 3 (HAM10000 + BCN20000) : résultats

Exécution réelle du 4 novembre 2026, selon le plan fixé avant l'entraînement (`plan_v3.md`).
- Entraînement : 2 profils × 3 graines, du 3 novembre à 23 h 23 au 4 novembre à 13 h 29, tous terminés sans erreur (journal `logs/v3_entrainement.log`).
- Évaluation : `python -m src.evaluer_v3` (journal `logs/v3_evaluation.log`, tableaux `resultats/tableaux/14_v3_*.csv`).

## 1. Règle de retenue (validation HAM, 1 023 images, fixée avant l'entraînement)

| Profil | Version | F1 macro | AUC macro | AUC mélanome | Exactitude équilibrée |
|---|---|---|---|---|---|
| complet | v2 | 0,721 | 0,972 | 0,928 | 0,707 |
| complet | v3 | 0,781 | 0,975 | 0,937 | 0,772 |
| sans contexte | v2 | 0,680 | 0,971 | 0,928 | 0,677 |
| sans contexte | v3 | 0,753 | 0,972 | 0,929 | 0,739 |

**Décision : la v3 est retenue.** Elle atteint au moins le niveau de la v2 sur les trois mesures, pour les deux profils. Sur les AUC, l'écart est faible ; sur le F1 macro, il est net.

## 2. Mesure unique sur les tests

| | v2, test HAM | v3, test HAM | v3, test BCN | v2, test BCN (externe) | v3 sans contexte, test BCN |
|---|---|---|---|---|---|
| Images / lésions / mélanomes | 1 009 / 747 / 113 | 1 009 / 747 / 113 | 1 747 / 476 / 429 | 1 747 / 476 / 429 | 1 747 / 476 / 429 |
| F1 macro | 0,699 | **0,755** | 0,623 | 0,458 | 0,705 |
| Exactitude équilibrée | 0,679 | **0,741** | 0,627 | 0,460 | 0,695 |
| AUC mélanome [IC95] | 0,938 [0,912–0,961] | 0,936 [0,905–0,962] | 0,921 [0,885–0,950] | 0,820 [0,764–0,869] | 0,925 [0,890–0,954] |
| Sensibilité mélanome (R = 10) [IC95] | 92,0 % [85,9–97,5] | 92,0 % [84,8–98,0] | 91,8 % [86,5–96,0] | 62,0 % [52,3–71,4] | 96,0 % [93,0–98,3] |
| Spécificité mélanome [IC95] | 77,5 % [73,8–81,0] | 76,2 % [72,9–79,7] | 67,6 % [63,1–72,2] | 83,5 % [79,8–86,7] | 59,8 % [55,1–64,6] |
| Valeur prédictive d'une alerte mélanome | 34,0 % | 32,8 % | 48,0 % | 55,0 % | 43,7 % |
| Mélanomes signalés chez les moins de 50 ans | 15 / 22 | 14 / 22 | 78 / 92 | 41 / 92 | 89 / 92 |
| Couverture de la prédiction conforme (cible 90 %) | 90,1 % | 92,0 % | 87,5 % | 73,5 % | 88,0 % |
| **Mélanomes classés bénins sans renvoi** | **1** | **9** | 19 | 73 | 7 |
| Sensibilité au triage (cancers renvoyés) | 99,0 % | 93,8 % | 97,0 % | 85,3 % | 98,8 % |
| Part des cas renvoyés au médecin | 46,6 % | 46,6 % | 82,0 % | 64,2 % | 85,7 % |

## 3. Lecture honnête

- **Gain réel en classification.** Sur les mêmes 1 009 images du test HAM, le F1 macro passe de 0,699 à 0,755 et l'exactitude équilibrée de 0,679 à 0,741. Les intervalles de confiance de ces deux mesures n'ont pas été calculés.
- **Pas de gain sur le mélanome dans HAM.** L'AUC (0,938 contre 0,936) et la sensibilité (92,0 % dans les deux cas) sont identiques, et les intervalles se chevauchent largement.
- **Recul sur la mesure de sécurité.** Avec la v3, 9 mélanomes du test HAM sur 113 seraient traités seuls comme bénins, sans renvoi au médecin, contre 1 avec la v2. La sensibilité au triage passe de 99,0 % à 93,8 %. Cause probable : le seuil et la calibration conforme sont réglés sur la validation et la calibration combinées, où BCN domine. Le réglage convient alors mieux à BCN qu'à HAM. C'est une hypothèse, pas encore vérifiée.
- **La v2 ne se généralise pas à un autre hôpital.** Sur le test BCN, elle tombe à une AUC mélanome de 0,820, une sensibilité de 62 % et 73 mélanomes classés bénins sans renvoi. C'est l'argument le plus fort en faveur de la v3. Ce test reste une estimation défavorable à la v2 : localisation inconnue, pas de recadrage, comme dans son prétraitement d'origine.
- **La v3 sur BCN.** Elle garde une AUC mélanome de 0,92 et une sensibilité de 92 à 96 %, mais renvoie 82 à 86 % des cas au médecin, avec une spécificité de 60 à 68 %. BCN est plus difficile que HAM : 25 % de mélanomes et beaucoup de lésions difficiles.
- **Limites.** BCN n'a pas d'identifiant patient, donc un même patient peut se trouver dans deux jeux. Le test BCN vient du même hôpital qu'une partie de l'entraînement : ce n'est pas une validation externe pour la v3. Les deux tests ont maintenant été vus : tout nouveau réglage devra être fait sur la validation et la calibration, et sa mesure ne serait plus un test vierge.

## 4. Le recul sur les mélanomes non renvoyés est-il réel ? (analyse du 4 novembre, sans le test)

Le test HAM ne contient que 113 mélanomes. Pour savoir si l'écart « 1 contre 9 » est solide, on a réutilisé les deux autres jeux HAM jamais vus à l'entraînement : la validation (117 mélanomes) et la calibration (110 mélanomes). On a fait un réglage croisé : seuil et ensembles conformes réglés sur l'un, mesure sur l'autre, puis l'inverse. Le test n'a pas été utilisé. Script : `python -m src.diagnostic_silence_v3` (exécution réelle).

| Profil | v2 : mélanomes classés bénins sans renvoi | v3 : mélanomes classés bénins sans renvoi |
|---|---|---|
| complet | 9 + 6 = **15 sur 227** | 5 + 9 = **14 sur 227** |
| sans contexte | 8 + 13 = **21 sur 227** | 3 + 7 = **10 sur 227** |

Sur 227 mélanomes, la v3 n'est pas moins sûre que la v2. Elle l'est même nettement plus sans contexte clinique. Le « 1 sur 113 » de la v2 sur le test était donc en partie un tirage favorable.

Une variante plus prudente a aussi été essayée : seuil réglé par base, puis le plus bas des deux retenu, et ensembles conformes réglés par base, puis les plus larges retenus. Sur le test HAM, elle laissait toujours 9 mélanomes sans renvoi. Comme elle n'apportait rien, elle n'a pas été retenue. On garde la calibration prévue par le plan, ce qui évite aussi tout réglage sur le test.

## 5. Mise en service (4 novembre 2026, sur demande de l'équipe)

- Paquet `application/modeles/ham10000-bcn20000-m5-v3`, construit par `python -m src.export_v3`. C'est le modèle par défaut de l'application ; le paquet v2 reste disponible.
- **Recadrage.** Le moteur de l'application et celui du navigateur appliquent la même règle de recadrage qu'à l'entraînement. Vérification : identique sur 120 images des deux bases.
- **Localisation.** Le médecin choisit toujours la localisation détaillée (dos, visage…), que le moteur ramène à l'une des cinq zones communes. L'outil « et si » compare désormais ces zones.
- **Détecteur d'images hors sujet**, recalculé sur les images d'entraînement v3 :
  - 85 % des 55 images hors sujet de la moitié d'évaluation sont refusées (87 % en v2) ;
  - 0,44 % des images du test sont refusées à tort.
- **Non-régression.** Sur 28 images des deux tests, le moteur reproduit les probabilités de l'entraînement : 72 tests de l'application passent.
- **Navigateur.** Les réseaux exportés en ONNX demi-précision s'écartent au plus de 0,0017 du moteur PyTorch, sur 48 analyses.
- **Analyse dans le navigateur** (site en ligne) : vérifiée dans Chrome sur 70 images des deux tests, dont 17 recadrées. Décision, orientation, ensemble conforme, refus hors sujet et ABCD sont identiques dans 100 % des cas ; l'écart de probabilité maximal est de 0,0046 (`docs/verification_navigateur.json`).
