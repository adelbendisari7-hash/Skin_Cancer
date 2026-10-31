# Résumé des résultats et suite du projet

*Tous les chiffres viennent de `resultats/tableaux/` (test, moyenne de 3 graines).*

## Résultats clés

| | Classifieur classique (M1, argmax) | IA prudente (M5 + coût + abstention) |
|---|---|---|
| Sensibilité mélanome (tous les cas, sans abstention) | 0,593 | 0,882 |
| Coût attendu (R = 10) | 0,595 | 0,389 |
| Mélanomes classés bénins sans renvoi (sur 113) | 46 | 6,7 |
| Lésions malignes non renvoyées (sur 194) | 70 | 8,7 |
| Part des cas traités seuls par l'IA | 100 % | 65,5 % (exactitude 0,90) |
| Part des cas vus par un médecin | 17 % | 45 % |
| F1 macro (tous les cas) | 0,646 | 0,609 |

1. **L'image domine** (F1 macro M1 0,646 ; clinique seule M2 0,165). Le contexte aide modestement s'il est fusionné
   tôt (M3 : +0,038, IC 95 % [+0,005 ; +0,074]) ; la fusion tardive M4 n'apporte rien.
2. **Plus sûre : oui.** Toutes les mesures de sécurité s'améliorent nettement (voir tableau).
3. **Meilleure : non, pas sur les métriques habituelles.** F1 macro et spécificité baissent, et 45 % des cas sont
   renvoyés à un médecin. La sécurité se paie en charge de travail.
4. **D'où vient le gain ?** Surtout du **seuil de coût** et de l'**abstention conforme par classe (Mondrian)**.
   FiLM apporte un supplément modeste mais reproduit (sensibilité mélanome +0,065 dans deux comparaisons
   indépendantes, environ 7 mélanomes manqués en silence contre 10 à 12 avec la concaténation), sans gain significatif
   d'AUC. La perte pondérée est redondante avec le seuil.
5. **Bonus.** Sans contexte au test, M5 s'effondre (sensibilité 0,189). Le **dropout de la modalité clinique** à
   l'entraînement le rend robuste (0,625).
6. **Vigilance.** Le modèle dépend fortement de l'âge et rate davantage de mélanomes chez les moins de 50 ans
   (0,59 de sensibilité, sur 22 mélanomes seulement). Le seuil de coût est instable entre graines (validation petite).

## Ce qui reste à faire

**Pour rendre le TP**
- [ ] Remplacer « [Nom Prénom 1/2/3] » sur la page de titre (`rapport/construire_rapport.py`, puis relancer le script).
- [ ] Relire le rapport à trois et vérifier que la présentation orale reprend les mêmes chiffres.
- [ ] Facultatif : tester le notebook sur Colab (adapter les deux chemins de la première cellule).

**Pour un projet à long terme**
- [ ] Validation externe : ISIC 2019/2020 et autres phototypes (le modèle n'a vu que deux centres).
- [ ] Fixer la matrice de coût avec des dermatologues (valeur de R, coût des renvois, gravité des carcinomes).
- [ ] Estimer les seuils sur plus de données (validation croisée) pour réduire leur instabilité.
- [ ] Prédiction conforme au niveau lésion (agréger les images d'une même lésion).
- [ ] Entraîner M5 avec le dropout clinique par défaut ; étudier la correction du biais lié à l'âge.
- [ ] Résolution plus élevée (300–450 px), modèles plus grands et ensembles, si le GPU le permet.
- [ ] Étude de la charge de travail réelle induite par les renvois, avec des cliniciens.
