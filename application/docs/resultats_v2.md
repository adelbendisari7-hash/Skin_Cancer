# Version 2 — résultats mesurés

Tous les chiffres viennent d'exécutions réelles (scripts cités). Rien n'a été réglé sur le jeu de test :
les choix sont faits sur la validation, le test est mesuré ensuite. Données : HAM10000 (CC BY-NC 4.0, usage non
commercial), découpage par lésion 70/10/10/10.

## 12 — Modèle plus puissant (EfficientNet-B2, 288 px)

Règle fixée avant l'entraînement (`docs/plan_v2.md`) : B2 n'est retenu que si, pour chacun des deux profils,
l'ensemble des 3 graines atteint au moins le F1 macro ET l'AUC macro de B0 **sur la validation**.

| Validation | F1 macro B0 → B2 | AUC macro B0 → B2 | Règle |
|---|---|---|---|
| Contexte complet | 0,705 → 0,721 | 0,970 → 0,972 | satisfaite |
| Contexte incomplet | 0,653 → 0,680 | 0,968 → 0,971 | satisfaite |

→ **B2 retenu** (`projet/src/export_v2.py`, table `resultats/tableaux/12_choix_architecture_validation.csv`).

Test, mesuré **après** le choix (`12_architecture_test_apres_choix.csv`) : le gain est **modeste**.

| Test (classe la plus probable) | F1 macro | AUC macro | AUC mélanome |
|---|---|---|---|
| Complet B0 / B2 | 0,694 / 0,699 | 0,967 / 0,966 | 0,926 / 0,938 |
| Incomplet B0 / B2 | 0,652 / 0,670 | 0,960 / 0,963 | 0,920 / 0,933 |

Avec la règle de prudence (R = 10) et l'abstention, profil complet, v1 → v2 :
mélanomes classés bénins sans renvoi **11 → 1 sur 113**, lésions malignes orientées vers un médecin
**93,3 % → 99,0 %**, couverture garantie 87,7 % → 90,1 % (cible 90 %). **Contrepartie** : l'IA conclut seule moins
souvent (75,7 % → 62,6 % des cas) et la spécificité mélanome baisse (82,0 % → 77,5 %), donc plus de renvois et de
fausses alertes. Profil incomplet : résultats mitigés (8 mélanomes non renvoyés sur 113 contre 6 en v1 ;
spécificité 77,1 % → 83,9 %).

## 7 — Refus des images hors sujet

Distance de Mahalanobis aux images d'entraînement dans l'espace des caractéristiques du réseau (Lee et al., NeurIPS
2018), seuil au 99,5ᵉ centile des images dermoscopiques de **validation**. Deux variantes ; les images hors sujet
sont coupées en deux moitiés, l'une pour choisir la variante, l'autre pour les chiffres annoncés
(`12_hors_sujet_evaluation.csv`, figure `12_hors_sujet_scores.png`).

| Variante | Dermoscopies du test refusées à tort | Images hors sujet refusées (moitié évaluation, n = 55) |
|---|---|---|
| Dernière couche seulement | 1,0 % | 65 % |
| **Toutes les couches (retenue)** | **0,4 %** | **87 %** |

Par source (variante retenue) : fonds d'écran 94 %, captures d'écran 100 %, images synthétiques 100 %, photos et
images scientifiques 64 %, illustrations Windows 60 %. **Limite** : aucune photo de peau prise sans dermoscope n'était
disponible pour le test ; ce type d'image peut passer le contrôle. L'utilisateur peut forcer l'analyse : elle est
alors marquée, tracée dans le journal et exclue du recalibrage.

## 5 — Recalibrage local

Expérience `projet/src/experience_recalibrage.py` : images du test (985, contexte complet), avec ou sans
« autre dermoscope » simulé (dominante chaude, gamma, flou, JPEG fort) ; 20 fois, recalibrage sur la moitié des
lésions, évaluation sur l'autre moitié (`13_recalibrage_decalage.csv`).

| Condition | Seuils | Couverture mélanome | Mélanomes non renvoyés (par moitié) | Sensibilité mélanome |
|---|---|---|---|---|
| Images d'origine | d'origine | 97,1 % | 0,55 | 91,6 % |
| Images d'origine | recalibrés | 89,9 % | 3,50 | 88,2 % |
| Autre dermoscope | d'origine | 86,7 % | 5,55 | 80,5 % |
| Autre dermoscope | recalibrés | 89,5 % | 2,65 | 88,3 % |

Conclusion honnête : le recalibrage restaure la sécurité mélanome quand l'appareil change, mais **la dégrade**
lorsqu'il n'y a pas de dérive (bruit d'un petit échantillon local). L'application affiche donc une
**recommandation** fondée sur l'estimation par validation croisée : dans l'expérience, elle ne recommande jamais
d'appliquer sans dérive (0 % des tirages) et recommande d'appliquer dans 80 % des tirages avec l'autre dermoscope
(mélanomes non renvoyés 5,55 → 3,00, sensibilité 80,5 % → 87,7 % en suivant la recommandation). Sur les données de
démonstration (pas de dérive), elle conseille de conserver les seuils d'origine.

## 11 — Critères ABCD automatiques

Segmentation classique de la lésion, puis A (asymétrie de forme et de couleur selon les 2 axes), B (8 secteurs à
transition abrupte), C (6 couleurs dermoscopiques), D (diamètre si la largeur du champ du dermoscope est
renseignée). Seuils choisis sur la validation, mesure sur le test (`11_abcd_performances_test.csv`) :
AUC mélanome contre nævus A 0,715, B 0,658, C 0,728 ; segmentation impossible 0 % ; lésion touchant le bord 23 %.
Ces critères sont présentés comme **indicateurs**, pas comme diagnostic.

## 6, 8, 9 — Suivi, sauvegarde, langues

Fonctions vérifiées par les tests automatiques (`application/tests`, 70 tests, GPU et processeur) : suivi et
comparaison de deux analyses d'une même lésion, migration d'une base v1, sauvegarde cohérente (API SQLite),
vérification d'archive (intégrité, empreinte, contenu), restauration avec sauvegarde de sécurité, messages du
serveur et comptes rendus PDF en français, anglais et arabe (contrôle que la police couvre tous les caractères).

Performances : une analyse ~0,5 s sur processeur, ~0,2 s sur GPU (RTX 3050 portable), contrôle hors sujet compris.
