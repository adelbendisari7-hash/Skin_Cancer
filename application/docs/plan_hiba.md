# Validation externe sur HIBA (Buenos Aires) : protocole fixé avant le calcul

Rédigé le 7 novembre 2026 avec le feu vert de l'équipe, **avant d'avoir analysé la moindre image**. Rien ne sera changé
après avoir vu un résultat.

## Données

- Hospital Italiano de Buenos Aires, Skin Lesions Images (2019-2022), archive ISIC, collection 251, licence CC BY.
  Ricci Lara et al., Sci Data 10, 712 (2023), doi:10.1038/s41597-023-02630-0. Dossier `HIBA/`, en lecture seule après
  extraction.
- Retenues : les 1 270 images **dermoscopiques** (1 191 lésions, 584 patients). Photos cliniques écartées.
- Classes, mêmes règles que pour BCN20000 : Nevus → nv ; Melanoma, NOS → mel ; Basal cell carcinoma → bcc ; Seborrheic
  keratosis, Solar lentigo, Lichen planus like keratosis → bkl ; Solar or actinic keratosis et Squamous cell carcinoma,
  NOS → akiec ; Dermatofibroma → df ; « Vascular » (diagnostic de niveau 2) → vasc.
- Aucun hôpital de HIBA n'a servi à l'entraînement de la v2 ni de la v3 : c'est une validation externe pour les deux.

## Modèles et réglages

- v2 (`ham10000-m5-v2`) et v3 (`ham10000-bcn20000-m5-v3`), exécutés par le moteur de l'application lui-même
  (prétraitement, recadrage pour la v3, choix du profil, seuils, ensembles conformes, détecteur hors sujet).
- **Aucun réglage sur HIBA** : seuils de coût (R = 10) et seuils conformes d'origine de chaque paquet.
- Analyse principale, « contexte réel » : âge, sexe et localisation de HIBA, comme un médecin les saisirait.
  - v3 : zones (Trunk → tronc, Head and neck → tête et cou, Upper/Lower extremity → membres, sites
    spéciaux → autre).
  - v2 : localisations HAM (Trunk → trunk, Upper extremity → upper extremity, Lower extremity → lower extremity,
    paumes et plantes → acral, muqueuses → genital). « Head and neck » n'a pas d'équivalent précis : localisation
    inconnue, donc profil sans contexte, exactement comme dans l'application.
- Analyse secondaire : aucun contexte, pour les deux versions.
- Les images signalées « hors sujet » sont analysées quand même (analyse forcée) ; le taux de refus est rapporté.

## Mesures (une seule fois)

AUC mélanome ; sensibilité et spécificité mélanome à R = 10 (y compris chez les moins de 50 ans) ; mélanomes classés
bénins sans renvoi ; sensibilité du triage des cancers (cancer prédit ou cas renvoyé) ; part des cas renvoyés ;
F1 macro, exactitude équilibrée et AUC macro ; couverture conforme ; images refusées comme hors sujet. Intervalles de
confiance à 95 % par bootstrap **sur les patients** (2 000 tirages).

Analyse annexe : sans les 158 images de carcinome épidermoïde invasif, que la v2 n'a jamais vues à l'entraînement.

## Limites connues avant le calcul

72 % des nævus n'ont pas de confirmation histologique ; la base compte beaucoup de cancers (sans doute plus qu'en
consultation courante), ce qui change la valeur prédictive des alertes ; peaux surtout de phototype II et III.
