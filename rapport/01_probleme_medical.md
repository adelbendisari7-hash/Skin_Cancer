# Étape 1 — Le problème médical et les données (résumé)

## Le problème clinique

Le **mélanome** est le cancer cutané le plus meurtrier : environ 325 000 nouveaux cas dans le monde en 2020, et une
projection de 510 000 cas et 96 000 décès par an en 2040 si les taux se maintiennent [Arnold 2022]. Détecté tôt, il
se traite par une simple exérèse. Détecté tard, il métastase. Le dermatologue examine la lésion au **dermoscope**
(loupe éclairée qui montre les structures pigmentaires sous la surface de la peau) et décide : surveiller, retirer,
ou faire une biopsie. La difficulté : la plupart des lésions pigmentées sont bénignes (nævus, kératoses), et certains
mélanomes ressemblent beaucoup à des nævus.

Le médecin ne regarde pas l'image seule : **l'âge du patient, la localisation et le sexe** modifient son
interprétation (un nouveau nævus à 70 ans inquiète plus qu'à 20 ans ; les kératoses actiniques siègent sur les zones
exposées au soleil, comme le visage). C'est ce raisonnement que notre modèle cherche à imiter.

Les erreurs n'ont pas le même coût : **manquer un mélanome** retarde le traitement d'un cancer potentiellement mortel ;
une **fausse alerte** coûte une consultation ou une biopsie inutile. Une IA utile doit en tenir compte, et savoir
**renvoyer au médecin** les cas où elle hésite plutôt que de répondre au hasard.

## Les données : HAM10000

HAM10000 (« Human Against Machine with 10 000 training images ») [Tschandl 2018] rassemble 10 015 images
dermoscopiques de 7 470 lésions, issues de deux centres (Vienne, Autriche ; Queensland, Australie) et de plusieurs
appareils. C'est le jeu d'entraînement du défi ISIC 2018 [Codella 2019].

| Code | Diagnostic | Nature | Images | Lésions |
|---|---|---|---|---|
| nv | Nævus mélanocytaire | bénin | 6 705 (66,9 %) | 5 403 |
| mel | Mélanome | **malin** | 1 113 (11,1 %) | 614 |
| bkl | Kératose bénigne (séborrhéique, lentigo solaire, lichen plan) | bénin | 1 099 (11,0 %) | 727 |
| bcc | Carcinome basocellulaire | **malin** | 514 (5,1 %) | 327 |
| akiec | Kératose actinique / maladie de Bowen | pré-malin / malin in situ | 327 (3,3 %) | 228 |
| vasc | Lésion vasculaire (angiome, hémangiome…) | bénin | 142 (1,4 %) | 98 |
| df | Dermatofibrome | bénin | 115 (1,1 %) | 73 |

Variables cliniques par image : `age` (par tranches de 5 ans, 57 manquants), `sex` (57 « unknown »),
`localization` (15 valeurs, 234 « unknown »). La variable `dx_type` indique **comment** le diagnostic a été établi
(histologie, suivi, consensus, microscopie confocale) : elle n'est **jamais** utilisée comme entrée, car elle trahit
la réponse (le suivi `follow_up` n'existe que pour les nævus ; tous les mélanomes sont histologiques).

## Ce qui rend le problème difficile

1. **Déséquilibre** : 67 % de nævus. Un modèle qui répond toujours « nævus » a 67 % d'exactitude et ne détecte aucun
   cancer. On utilise donc le F1 macro, l'exactitude équilibrée et la sensibilité au mélanome.
2. **Plusieurs images par lésion** (26 % des lésions) : il faut découper les jeux **par lésion**, sinon le test
   contient des quasi-doublons des images d'entraînement.
3. **Vérité terrain hétérogène** : un peu plus de la moitié des lésions sont confirmées par histologie, les autres
   par suivi ou consensus d'experts.
4. **Contexte clinique pauvre** : trois variables seulement, plus faibles que l'image (cf. étape 2).

## Question de recherche

> Une IA prudente — qui utilise le contexte du patient pour interpréter l'image, tient compte du coût d'un mélanome
> manqué et sait s'abstenir quand elle est incertaine — est-elle meilleure et plus sûre qu'un classifieur classique ?

## Références

- [Tschandl 2018] Tschandl P, Rosendahl C, Kittler H. *The HAM10000 dataset, a large collection of multi-source
  dermatoscopic images of common pigmented skin lesions.* Sci Data 5:180161 (2018). doi:10.1038/sdata.2018.161 —
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6091241/
- [Codella 2019] Codella N et al. *Skin lesion analysis toward melanoma detection 2018: a challenge hosted by the
  International Skin Imaging Collaboration (ISIC).* arXiv:1902.03368.
- [Arnold 2022] Arnold M et al. *Global burden of cutaneous melanoma in 2020 and projections to 2040.* JAMA Dermatol
  158(5):495-503 (2022). — https://melanoma.org.au/paper/global-burden-of-cutaneous-melanoma-in-2020-and-projections-to-2040/
