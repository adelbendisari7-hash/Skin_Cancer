# IA prudente guidée par le contexte patient — HAM10000

Projet du TP *Advanced Applications of Data Science in Medicine* (USTO, Oran).

**Question de recherche.** Une IA prudente, qui utilise le contexte du patient pour interpréter l'image, tient
compte du coût d'un mélanome manqué et sait s'abstenir quand elle est incertaine, est-elle meilleure et plus sûre
qu'un classifieur classique ?

Le modèle proposé (M5) combine trois idées :

1. **Fusion guidée par le patient (FiLM)** : un petit réseau lit l'âge, le sexe et la localisation et produit, pour
   chaque canal de caractéristiques de l'image, un gain γ et un décalage β : `h ← (1 + γ) ⊙ h + β`. Le contexte change
   la façon de lire l'image au lieu d'être simplement collé à côté (concaténation).
2. **Décision sensible au coût** : perte pondérée (classes rares, mélanome renforcé) et seuil de décision sur
   p(mélanome) réglé sur la validation pour une matrice de coût où un mélanome manqué coûte R = 10 fausses alertes
   (5 et 20 testés).
3. **Abstention par prédiction conforme** : calibrée sur un jeu séparé, l'IA renvoie le cas au médecin quand
   l'ensemble de prédiction n'est pas un singleton.

## Résultats en bref (test, moyenne de 3 graines)

| | M1 classique | M5 + coût + abstention |
|---|---|---|
| Sensibilité mélanome (sans abstention) | 0,593 | 0,882 |
| Coût attendu (R = 10) | 0,595 | 0,389 |
| Mélanomes classés bénins sans renvoi (/113) | 46 | 6,7 |
| Cas traités seuls par l'IA | 100 % | 65,5 % (exactitude 0,90) |
| Cas vus par un médecin | 17 % | 45 % |

L'IA prudente est **nettement plus sûre**, mais **pas meilleure sur les métriques habituelles** (F1 macro 0,609 contre
0,646). Le gain vient surtout du seuil de coût et de l'abstention conforme ; FiLM apporte un supplément modeste mais
reproduit. Détails : `rapport/rapport_projet_ham10000.pdf` et `rapport/resume_et_suite.md`.

## Livrables

- `notebooks/projet_ham10000.ipynb` — les 10 étapes de la fiche, exécuté de bout en bout
- `rapport/rapport_projet_ham10000.docx` et `.pdf` — rapport en français (18 pages) ; régénéré par
  `python rapport/construire_rapport.py` (export PDF via Microsoft Word)
- `rapport/01_probleme_medical.md` — résumé médical d'une page (étape 1)
- `rapport/resume_et_suite.md` — résumé court et liste de ce qui reste à faire
- `resultats/figures/` et `resultats/tableaux/` — 21 figures PNG et 29 tableaux (CSV/JSON)
- `logs/` — sorties brutes des entraînements et des analyses

## Structure

```
projet/
├── src/                     code réutilisable
│   ├── config.py            chemins, graines, hyperparamètres (tout est réglable ici)
│   ├── data.py              chargement, découpage par lésion, encodage clinique, cache, augmentations GPU
│   ├── eda.py               étape 2 — exploration
│   ├── prepare.py           étape 3 — prétraitement et contrôles anti-fuite
│   ├── models.py            M1 / M3 / M5 (EfficientNet-B0 + concaténation ou FiLM)
│   ├── train.py             entraînement commun (AMP, arrêt sur F1 macro de validation, TTA)
│   ├── tabular.py           étape 5 — M2 XGBoost (+ forêt aléatoire, SHAP)
│   ├── decision.py          M4 (fusion tardive) et seuil de coût
│   ├── conformal.py         prédiction conforme LAC / APS / Mondrian, abstention
│   ├── metrics.py           métriques, matrice de coût, bootstrap par lésion
│   ├── evaluate.py          assemblage des prédictions et comparaisons
│   ├── figures.py           figures des étapes 4 à 8
│   ├── results.py           étapes 4 à 8 en une commande
│   ├── interpret.py         Grad-CAM, paramètres FiLM, contrefactuels
│   ├── analyses.py          étapes 9 et 10 (interprétation, sous-groupes, bonus)
│   ├── viz.py               style graphique commun
│   └── run_all.py           toute la chaîne d'entraînement (reprise possible)
├── notebooks/projet_ham10000.ipynb   notebook organisé selon les 10 étapes
├── resultats/
│   ├── figures/             figures PNG (préfixe = numéro d'étape)
│   ├── tableaux/            tableaux CSV
│   ├── predictions/         probabilités de chaque modèle et graine (+ historiques)
│   └── split_lesions.csv    le découpage utilisé (identique pour tous les modèles)
├── rapport/                 rapport final (Word + PDF) et résumé médical
├── cache/                   images redimensionnées (régénérable, non versionné)
└── checkpoints/             poids des réseaux (non versionné)
```

## Reproduire

Le dossier `HAM10000/` (lecture seule) doit être à côté de `projet/`, ou indiqué par la variable `HAM_DIR`.

```powershell
cd projet
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m src.run_all      # prétraitement + M2 + 18 entraînements (~2 h sur RTX 3050 4 Go)
.venv\Scripts\python -m src.results      # étapes 4 à 8 : tableaux et figures
.venv\Scripts\python -m src.analyses     # étapes 9 et 10
```

`run_all` saute les entraînements déjà faits : on peut l'interrompre et le relancer.

### Google Colab

1. Copier `projet/` et `HAM10000/` dans Google Drive, ouvrir `notebooks/projet_ham10000.ipynb` dans Colab.
2. Activer un GPU (Exécution → Modifier le type d'exécution).
3. La première cellule détecte Colab, monte le Drive et règle `HAM_DIR` ; adapter les deux chemins si besoin.
4. Mettre `RUN_TRAINING = True` pour réentraîner, sinon le notebook relit les prédictions sauvegardées.

## Règles respectées

- Découpage **par lésion** (aucune lésion dans deux jeux), stratifié : 70 % train, 10 % validation, 10 % calibration,
  10 % test ; graine 42 ; 3 graines d'entraînement (0, 1, 2).
- `dx_type` n'est **jamais** une entrée (fuite : `follow_up` n'existe que pour les nævus).
- Aucun réglage sur le test : poids de M4, seuils de coût, choix de la variante FiLM et de la méthode conforme sont
  faits sur la validation ; les seuils conformes sur la calibration.
- Tous les chiffres du rapport viennent des fichiers de `resultats/`.

## Avertissement

Projet pédagogique. Ce n'est **pas** un dispositif médical et il ne doit pas servir à un diagnostic réel.
