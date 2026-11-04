# Version 3 — HAM10000 + BCN20000 : plan fixé avant l'entraînement

Rédigé le 3 novembre 2026, **avant tout entraînement**, avec le feu vert de l'équipe. Aucune règle ci-dessous ne sera
modifiée après avoir vu un résultat. Version de **recherche** : BCN20000 est, comme HAM10000, sous licence CC BY-NC
sur l'archive ISIC (18 946 images vérifiées) ; le modèle obtenu reste non commercial.

## Données

- HAM10000 : inchangé, même découpage par lésion qu'en v1/v2 (`resultats/split_lesions.csv`). Le test HAM (1 009
  images) reste exactement le même, pour comparer v2 et v3 sur les mêmes images.
- BCN20000 (collection ISIC 249, dossier `BCN20000/`, en lecture seule) : 18 946 images, 5 440 lésions.
  Classes : Nevus → nv ; Melanoma, NOS → mel ; Basal cell carcinoma → bcc ; Seborrheic keratosis et Solar lentigo →
  bkl ; Solar or actinic keratosis et Squamous cell carcinoma, NOS → akiec ; Dermatofibroma → df ; diagnostic de
  niveau 2 « Vascular » → vasc. **Exclus** : Melanoma metastasis (633, l'outil trie des lésions primaires), Scar
  (314), sans diagnostic (1 156). Soit 16 843 images retenues.
- BCN20000 est découpé par lésion, stratifié par diagnostic, 70/10/10/10, graine 42. Pas d'identifiant patient : un
  même patient peut apparaître dans deux jeux (limite connue).
- `diagnosis_confirm_type`, `concomitant_biopsy` et `dx_type` ne sont **jamais** des entrées.

## Contexte clinique

- Localisation en zones communes aux deux bases : tronc (back, trunk, abdomen, chest / Trunk), tête et cou (face,
  scalp, neck, ear / Head and neck), membre supérieur (upper extremity, hand), membre inférieur (lower extremity,
  foot), autre (genital, acral / acral palms or soles, oral or genital), inconnue. Garder les 15 zones de HAM et
  « inconnue » pour BCN laisserait « inconnue » signaler la source, donc la fréquence des cancers.
- Âge et sexe comme avant (âge imputé par la médiane du train, indicateur de manque).

## Images

- Même règle pour les deux bases : si les coins sont noirs (moyenne < 30 sur 256 niveaux), l'image est recadrée au
  carré inscrit dans le cercle du dermoscope. Mesuré sur 400 images par base : 44 % des images BCN ont des coins
  noirs, contre 3 % des images HAM ; sans recadrage, le réseau pourrait reconnaître l'hôpital au lieu de la lésion.
- 288 × 288 px, normalisation ImageNet, mêmes augmentations qu'en v2.

## Entraînement

Identique à la v2 pour isoler l'effet des données : EfficientNet-B2, FiLM sur les caractéristiques finales, perte
pondérée par classe, AdamW, 15 époques au plus, arrêt sur le F1 macro de la validation combinée (HAM + BCN), 3 graines
(0, 1, 2), deux profils (contexte complet ; dropout clinique pour le profil sans contexte).

## Règle de retenue (fixée maintenant)

La v3 remplace la v2 seulement si, **pour chacun des deux profils**, l'ensemble des 3 graines atteint au moins la v2
**sur la validation HAM10000** (1 023 images, jamais le test) pour les trois mesures : F1 macro, AUC macro un contre
tous, AUC mélanome. Sinon la v2 est conservée, et le résultat est rapporté tel quel.

## Mesure (une seule fois, après la décision)

- Seuil de coût (R = 10) choisi sur la validation combinée ; prédiction conforme Mondrian (α = 0,1) sur la
  calibration combinée ; mêmes procédures qu'en v2.
- Test HAM (les mêmes 1 009 images, v2 et v3 côte à côte) et test BCN (jamais vu), séparément : F1 macro, exactitude
  équilibrée, AUC, sensibilité et spécificité mélanome, mélanomes classés bénins sans renvoi, part des cas renvoyés,
  sensibilité mélanome chez les moins de 50 ans ; intervalles de confiance par bootstrap sur les lésions.
- Remplacer le modèle de l'application ou du site demandera un second accord de l'équipe.
