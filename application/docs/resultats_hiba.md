# Validation externe sur HIBA (Buenos Aires) : résultats

Exécution réelle du 7 novembre 2026, selon le protocole fixé avant le calcul (`plan_hiba.md`). Script :
`python -m src.evaluer_hiba`. Journal : `logs/hiba_evaluation.log`. Tableau : `resultats/tableaux/15_hiba_tests.csv`.

Les données :
- 1 270 images dermoscopiques, 1 191 lésions, 584 patients, dont 194 images de mélanome ;
- un hôpital qu'aucune des deux versions n'a vu à l'entraînement ;
- aucun réglage sur ces données.

Les intervalles de confiance à 95 % sont calculés par bootstrap sur les patients.

## Contexte réel (âge, sexe, localisation, comme un médecin les saisirait)

| | v2 (HAM10000) | v3 (HAM10000 + BCN20000) |
|---|---|---|
| F1 macro (7 classes) | 0,437 | **0,584** |
| Exactitude équilibrée | 0,442 | **0,589** |
| AUC macro | 0,876 | **0,916** |
| AUC mélanome [IC95] | 0,857 [0,817–0,892] | 0,868 [0,830–0,902] |
| Sensibilité mélanome (R = 10) [IC95] | 73,2 % [66,2–79,5] | **90,7 % [86,1–94,8]** |
| Spécificité mélanome [IC95] | **81,7 % [77,7–85,3]** | 54,3 % [47,7–61,0] |
| Valeur prédictive d'une alerte mélanome | **41,9 %** | 26,3 % |
| Mélanomes signalés chez les moins de 50 ans (32) | 59 % | **78 %** |
| Mélanomes classés bénins sans renvoi | 15 [8–24] | 14 [7–23] |
| Cancers orientés vers un médecin (triage) | 93,4 % | **97,1 %** |
| Part des cas renvoyés au médecin | **62 %** | 81 % |
| Couverture conforme (cible 90 %) | 80,6 % | 84,5 % |
| Vraies dermoscopies signalées « hors sujet » | 10,6 % | **3,5 %** |

## Sans aucun contexte

| | v2 | v3 |
|---|---|---|
| AUC mélanome [IC95] | 0,864 [0,826–0,896] | **0,902 [0,875–0,927]** |
| Sensibilité mélanome | 65,5 % [57,2–72,9] | **96,9 % [94,3–99,0]** |
| Spécificité mélanome | **88,9 %** | 54,6 % |
| Mélanomes signalés chez les moins de 50 ans | 63 % | **94 %** |
| Mélanomes classés bénins sans renvoi | 24 [15–35] | **4 [1–8]** |
| Part des cas renvoyés | **62 %** | 81 % |

Sans les 158 carcinomes épidermoïdes invasifs (analyse annexe), les conclusions sont les mêmes : la v3 garde son
avance (AUC macro 0,921 contre 0,881).

## Lecture honnête

1. **Les deux versions perdent en performance hors de leurs hôpitaux.** L'AUC mélanome de la v3 passe de 0,94 sur le
   test HAM à 0,87–0,90 à Buenos Aires ; celle de la v2, de 0,94 à 0,86.
2. **La v3 est meilleure que la v2 sur la plupart des critères.**
   - Elle classe mieux les 7 types de lésions (F1 macro 0,58 contre 0,44).
   - Elle rate beaucoup moins de mélanomes (91 % contre 73 % de sensibilité) et en signale plus chez les moins de 50 ans.
   - Elle refuse trois fois moins de vraies dermoscopies comme « hors sujet ».
   - Sans contexte, elle laisse 4 mélanomes sans renvoi, contre 24 pour la v2.
   - Avec contexte réel, l'écart d'AUC mélanome est faible et les intervalles se chevauchent.
3. **Le prix de cette prudence.** Au seuil d'origine, la v3 lance beaucoup de fausses alertes : spécificité de 54 %,
   seulement une alerte sur quatre est un vrai mélanome, et 81 % des cas sont renvoyés au médecin. La v2 est plus
   spécifique, mais parce qu'elle laisse passer un mélanome sur quatre.
4. **Le contexte clinique appris en Europe et en Australie n'aide pas à Buenos Aires.** Pour la v3, l'AUC mélanome est
   meilleure sans contexte (0,902) qu'avec (0,868). Âge, sexe et localisation se répartissent sans doute autrement
   entre les diagnostics dans cette population. C'est un résultat important pour un déploiement : le profil
   « sans contexte » est le plus fiable dans un nouvel hôpital, tant que les seuils n'y ont pas été recalibrés.
5. **Couverture conforme sous la cible.** 84,5 % pour la v3 au lieu des 90 % visés : la garantie statistique ne tient
   que pour des images semblables à celles de la calibration. C'est attendu dans un nouvel hôpital, et c'est ce que le
   recalibrage local de l'application est fait pour corriger.

Limites : 72 % des nævus de HIBA n'ont pas de confirmation histologique ; la base compte beaucoup de cancers, ce qui
influe sur la valeur prédictive des alertes ; peaux surtout de phototype II et III.
