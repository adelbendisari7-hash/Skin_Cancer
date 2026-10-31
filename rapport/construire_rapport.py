"""Construit le rapport final (Word + PDF) à partir des tableaux et figures de resultats/.

Usage (depuis projet/) : python rapport/construire_rapport.py
Les tableaux sont relus dans les CSV ; les chiffres cités dans le texte ont été vérifiés
dans ces mêmes fichiers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from docx.enum.text import WD_ALIGN_PARAGRAPH

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_outils import Rapport, docx_to_pdf  # noqa: E402

from src import config as C  # noqa: E402

FIG, TAB = C.FIG_DIR, C.TAB_DIR


def fr(x: float, nd: int = 3) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def tableau_classes() -> pd.DataFrame:
    t = pd.read_csv(TAB / "02_classes.csv")
    noms = C.CLASS_NAMES_FR
    t.insert(1, "diagnostic", t.dx.map(noms))
    t["% images"] = t["% images"].map(lambda v: fr(v, 1))
    t["images / lésion"] = t["images / lésion"].map(lambda v: fr(v, 2))
    return t.rename(columns={"dx": "code", "lesions": "lésions"})


def tableau_decoupage() -> pd.DataFrame:
    t = pd.read_csv(TAB / "03_decoupage.csv", header=[0, 1], index_col=0)
    les, img = t["lésions"], t["images"]
    out = pd.DataFrame({"classe": les.index})
    for s in ["train", "val", "calib", "test"]:
        out[s] = [f"{int(a)} ({int(b)})" for a, b in zip(les[s], img[s])]
    return out


SHORT = {"M1 image": "M1 image", "M2 clinique": "M2 clinique", "M3 concaténation": "M3 concat.",
         "M4 fusion tardive": "M4 tardive", "M5 FiLM + coût (proposé)": "M5 proposé",
         "M5 sans FiLM (concat + coût)": "M5 sans FiLM", "M5 sans coût (FiLM + CE)": "M5 sans coût",
         "M5 + dropout clinique (bonus)": "M5 + dropout clin."}

COLS = ["F1 macro", "Exactitude équilibrée", "AUC OvR macro", "AUC mel", "Sensibilité mel", "Spécificité mel",
        "Coût attendu"]


def tableau_comparaison(models: list[str]) -> pd.DataFrame:
    t = pd.read_csv(TAB / "07_comparaison_finale.csv")
    t = t[t.modèle.isin(models)].copy()
    t["décision"] = t["décision"].replace({"coût R=10": "coût"})
    t["modèle"] = t["modèle"].replace(SHORT)
    t = t[["modèle", "décision"] + COLS]
    for c in COLS:
        t[c] = t[c].str.replace(".", ",", regex=False)
    return t.rename(columns={"Exactitude équilibrée": "Exact. équil.", "AUC OvR macro": "AUC macro",
                             "Sensibilité mel": "Sens. mel", "Spécificité mel": "Spéc. mel",
                             "Coût attendu": "Coût"})


def tableau_bootstrap() -> pd.DataFrame:
    b = pd.read_csv(TAB / "07_bootstrap_comparaisons.csv")
    b["comparaison"] = (b.comparaison.str.replace(" [coût R=10]", " (coût)", regex=False)
                        .str.replace(" [classique]", " (classique)", regex=False)
                        .str.replace("M5_sansFiLM", "M5 sans FiLM").str.replace("M5_sansCout", "M5 sans coût"))
    b["cell"] = [f"{d:+.3f}{' *' if s else ''}\n{ic}".replace(".", ",") for d, ic, s in
                 zip(b["différence"], b["IC95 %"], b["significatif"])]
    p = b.pivot(index="comparaison", columns="métrique", values="cell")
    p = p.reindex(b.comparaison.drop_duplicates())
    p = p[["F1 macro", "Exactitude équilibrée", "Sensibilité mel", "Coût attendu", "AUC mel"]]
    return p.reset_index().rename(columns={"comparaison": "comparaison (A − B)", "Exactitude équilibrée": "Exact. équil."})


def tableau_abstention() -> pd.DataFrame:
    t = pd.read_csv(TAB / "08_abstention_par_graine.csv").drop(columns="graine")
    t = t.groupby("modèle", sort=False).mean()
    keep = {"taux traité": ("cas traités", 3), "couverture conforme": ("couverture", 3),
            "couverture conforme mel": ("couverture mel", 3), "F1 macro (traités)": ("F1 macro traités", 3),
            "Exactitude (traités)": ("exactitude traités", 3),
            "mélanomes renvoyés au médecin": ("mel renvoyés", 1),
            "mélanomes manqués en silence": ("mel manqués en silence", 1),
            "mélanomes manqués (argmax, sans abstention)": ("mel manqués sans IA prudente (argmax)", 1)}
    out = pd.DataFrame({"modèle": t.index})
    for k, (name, nd) in keep.items():
        out[name] = [fr(v, nd) for v in t[k]]
    return out[out.modèle != "M2 clinique"]


def tableau_conforme_val() -> pd.DataFrame:
    t = pd.read_csv(TAB / "08_choix_conforme_validation.csv", index_col=0)
    t = t[["couverture", "couverture mel", "taille moyenne", "taux traité", "mel manqués en silence (val)"]]
    t.index = t.index.map({"lac": "LAC", "aps": "APS (randomisé)", "mondrian": "LAC par classe (Mondrian)"})
    return t.map(lambda v: fr(v, 3) if v < 5 else fr(v, 1)).reset_index(names="méthode")


def tableau_triage() -> pd.DataFrame:
    t = pd.read_csv(TAB / "08_triage_malin_benin.csv")
    t = t[t.modèle.isin(["M1", "M5"])]
    out = t[["modèle", "décision"]].copy()
    out["sensibilité malin"] = t["sensibilité malin"].map(fr)
    out["spécificité bénin"] = t["spécificité bénin"].map(fr)
    out["malins non renvoyés (/194)"] = t["malins non renvoyés"].map(lambda v: fr(v, 1))
    out["part des cas renvoyés"] = t["part des cas renvoyés"].map(lambda v: f"{100 * v:.0f} %")
    return out


def tableau_bonus() -> pd.DataFrame:
    t = pd.read_csv(TAB / "10_bonus_contexte_manquant_par_graine.csv")
    t = t[t.décision == "classique"].groupby(["modèle", "test"], sort=False).mean(numeric_only=True).reset_index()
    out = t[["modèle", "test"]].copy()
    out["modèle"] = out["modèle"].replace({"M5": "M5 proposé", "M5_dropClin": "M5 + dropout clinique",
                                           "M1": "M1 image", "M3": "M3 concat."})
    for c in ["F1 macro", "Exactitude équilibrée", "Sensibilité mel", "Coût attendu"]:
        out[c] = t[c].map(fr)
    return out.rename(columns={"Exactitude équilibrée": "Exact. équil.", "Sensibilité mel": "Sens. mel"})


def tableau_entrainements() -> pd.DataFrame:
    t = pd.read_csv(TAB / "04_entrainements.csv")
    t["best_val_f1"] = t["best_val_f1"].map(fr)
    t["train_time_s"] = (t["train_time_s"] / 60).map(lambda v: fr(v, 1))
    return t.rename(columns={"exp": "expérience", "seed": "graine", "best_val_f1": "meilleur F1 val",
                             "best_epoch": "meilleure époque", "epochs_run": "époques", "train_time_s": "durée (min)"})


def main() -> None:
    method = json.loads((TAB / "08_methode_conforme.json").read_text())["méthode"]
    assert method == "mondrian", "le texte du rapport décrit la méthode Mondrian retenue sur la validation"
    r = Rapport()
    d = r.doc

    # ------------------------------------------------------------------ page de titre
    for _ in range(5):
        d.add_paragraph()
    r.p("TP — Advanced Applications of Data Science in Medicine", align=WD_ALIGN_PARAGRAPH.CENTER, size=12)
    t = r.p("**Une IA prudente guidée par le contexte du patient pour la classification des lésions cutanées**",
            align=WD_ALIGN_PARAGRAPH.CENTER, size=20)
    t.paragraph_format.space_before = t.paragraph_format.space_after = 12
    r.p("Fusion FiLM image–clinique, décision sensible au coût et abstention par prédiction conforme sur HAM10000",
        align=WD_ALIGN_PARAGRAPH.CENTER, size=12.5, italic=True)
    for _ in range(4):
        d.add_paragraph()
    r.p("Groupe : [Nom Prénom 1] · [Nom Prénom 2] · [Nom Prénom 3]", align=WD_ALIGN_PARAGRAPH.CENTER, size=11.5)
    r.p("Université des Sciences et de la Technologie d'Oran Mohamed-Boudiaf (USTO-MB)",
        align=WD_ALIGN_PARAGRAPH.CENTER, size=11)
    r.p("Octobre 2026", align=WD_ALIGN_PARAGRAPH.CENTER, size=11)
    for _ in range(6):
        d.add_paragraph()
    r.p("Projet pédagogique — ce travail n'est pas un dispositif médical et ne doit pas servir au diagnostic.",
        align=WD_ALIGN_PARAGRAPH.CENTER, size=9, italic=True)
    r.page_break()

    # ------------------------------------------------------------------ résumé
    r.h("Résumé", 1)
    r.p("Nous étudions si une IA « prudente » — qui interprète l'image dermoscopique à la lumière du contexte du "
        "patient (âge, sexe, localisation), tient compte du coût d'un mélanome manqué et s'abstient quand elle est "
        "incertaine — est meilleure et plus sûre qu'un classifieur classique. Sur HAM10000 (10 015 images, 7 470 "
        "lésions, 7 classes), découpé par lésion en train / validation / calibration / test (70/10/10/10), nous "
        "comparons cinq modèles sur trois graines : un CNN image seul (EfficientNet-B0, M1), un modèle clinique seul "
        "(XGBoost, M2), une fusion par concaténation (M3), une fusion tardive (M4) et le modèle proposé M5, où le "
        "contexte module chaque canal de l'image (FiLM), avec un seuil de décision réglé pour un coût de mélanome "
        "manqué dix fois supérieur à une fausse alerte et une abstention par prédiction conforme conditionnelle par "
        "classe.")
    r.p("**Résultats (test).** L'image porte l'essentiel de l'information (F1 macro 0,646 pour M1 contre 0,165 "
        "pour M2) ; le contexte bien fusionné aide modestement (M3 : +0,038 de F1 macro, IC 95 % [+0,005 ; +0,074]). "
        "Le système complet est nettement **plus sûr** : sur 113 mélanomes, le classifieur classique en manque 46, "
        "l'IA prudente n'en classe que 6,7 comme bénins sans renvoi, tout en traitant seule 65,5 % des cas avec une "
        "exactitude de 0,90 ; le coût attendu passe de 0,595 à 0,389. Il n'est pas « meilleur » sur toutes les "
        "métriques : le F1 macro baisse (−0,037) et 45 % des cas sont renvoyés à un médecin. Les ablations montrent que "
        "le gain vient surtout de la couche de décision (seuil de coût et abstention) ; FiLM apporte un supplément "
        "modeste mais reproduit (sensibilité mélanome +0,065 dans deux comparaisons indépendantes), sans gain "
        "significatif d'AUC ; la perte pondérée est redondante avec le seuil.")
    r.p("**Mots-clés** : dermoscopie, mélanome, apprentissage multimodal, FiLM, apprentissage sensible au coût, "
        "prédiction conforme, abstention.", italic=False)

    # ------------------------------------------------------------------ 1. introduction
    r.h("1. Introduction", 1)
    r.p("Le mélanome est le plus meurtrier des cancers cutanés : environ 325 000 nouveaux cas dans le monde en 2020, "
        "et une projection de 510 000 cas et 96 000 décès par an en 2040 si les taux se maintiennent [1]. Détecté tôt, "
        "il se traite par exérèse. Le dermatologue l'évalue au dermoscope, mais la majorité des lésions pigmentées sont "
        "bénignes et certains mélanomes ressemblent à des nævus. Les réseaux convolutifs atteignent de bonnes "
        "performances sur ces images [2, 3], mais un classifieur standard présente trois défauts pour un usage "
        "clinique : il ignore le contexte que le médecin utilise (âge, localisation), il traite toutes les erreurs comme "
        "équivalentes alors qu'un mélanome manqué est bien plus grave qu'une fausse alerte, et il répond toujours, même "
        "quand il hésite.")
    r.p("Notre question de recherche est donc : **une IA prudente, qui utilise le contexte du patient pour interpréter "
        "l'image, tient compte du coût d'un mélanome manqué et sait s'abstenir quand elle est incertaine, est-elle "
        "meilleure et plus sûre qu'un classifieur classique ?** Pour y répondre, nous suivons les dix étapes de la "
        "fiche du TP et nous construisons un modèle original, M5, qui combine :")
    r.bullets([
        "une **fusion guidée par le patient** de type FiLM [4] : un petit réseau lit le contexte et produit, pour chaque "
        "canal de caractéristiques de l'image, un gain γ et un décalage β ;",
        "une **décision sensible au coût** : seuil sur la probabilité de mélanome réglé sur la validation pour une "
        "matrice de coût paramétrable (R = 5, 10, 20) ;",
        "une **abstention par prédiction conforme** [5, 6] : l'IA renvoie au médecin les cas dont l'ensemble de "
        "prédiction calibré n'est pas un singleton.",
    ])
    r.p("Moduler les caractéristiques visuelles par les métadonnées n'est pas une idée nouvelle en dermatologie : "
        "MetaNet [7] et MetaBlock [8] le font déjà. Notre contribution est l'**assemblage orienté sécurité** de ces "
        "trois ingrédients et son **évaluation rigoureuse** : même découpage pour tous les modèles, trois graines, "
        "études d'ablation, deux règles de décision par modèle et intervalles de confiance par bootstrap au niveau "
        "lésion. Tous les chiffres de ce rapport proviennent d'exécutions réelles ; les résultats défavorables au "
        "modèle proposé sont rapportés comme les autres.")

    # ------------------------------------------------------------------ 2. données
    r.h("2. Données", 1)
    r.p("HAM10000 [9] rassemble 10 015 images dermoscopiques (600 × 450 px) de 7 470 lésions, acquises à Vienne "
        "(Autriche) et dans le Queensland (Australie) ; c'est le jeu d'entraînement du défi ISIC 2018 [10]. Chaque "
        "image a un diagnostic (`dx`, 7 classes) et trois variables cliniques : `age`, `sex`, `localization`. La "
        "colonne `dx_type` indique comment le diagnostic a été confirmé ; elle n'est jamais utilisée comme entrée "
        "(voir 2.2). Les fichiers `hmnist_*` (images réduites aplaties) sont ignorés.")
    r.table(tableau_classes(), "Classes de HAM10000 (images, lésions distinctes, images par lésion).",
            col_widths_cm=[1.4, 5.2, 1.8, 1.8, 1.8, 2.4])
    r.h("2.1 Exploration", 2)
    r.p("**Déséquilibre.** Les nævus représentent 66,9 % des images et les dermatofibromes 1,1 % (rapport 58 : 1). "
        "Un modèle qui répondrait toujours « nævus » obtiendrait 67 % d'exactitude sans détecter aucun cancer : nous "
        "utilisons donc le F1 macro, l'exactitude équilibrée et la sensibilité au mélanome.")
    r.p("**Plusieurs images par lésion.** 26 % des lésions ont au moins deux images (jusqu'à six), et les mélanomes "
        "en ont 1,81 en moyenne contre 1,24 pour les nævus. Un découpage par image placerait des quasi-doublons dans "
        "le train et le test, surtout pour les mélanomes : nous découpons par lésion.")
    r.p("**Variables cliniques.** L'âge manque pour 57 images (0,6 %), est arrondi à 5 ans (100 % de multiples de 5, "
        "anonymisation) et vaut 0 pour 39 images (nævus congénitaux, hémangiomes — plausibles, conservés). Les "
        "mélanomes, carcinomes et kératoses concernent des patients plus âgés (médianes 60 à 70 ans) que les nævus "
        "(45 ans). Le sexe est très faiblement associé au diagnostic (V de Cramér 0,07), la localisation et l'âge "
        "modérément (0,22 et 0,25). Le visage est dominé par les kératoses et les carcinomes (zones photo-exposées) et "
        "71 % des dermatofibromes siègent sur le membre inférieur. La catégorie « trunk » contient 88 % de nævus alors "
        "que « back », « chest » et « abdomen » existent aussi : le codage de la localisation diffère probablement "
        "selon le centre.")
    r.figure(FIG / "02_localisation.png", "Répartition des diagnostics par localisation (pourcentage de la ligne).",
             width_cm=10)
    r.h("2.2 Une fuite d'information à éviter", 2)
    r.p("`dx_type` est fortement lié au diagnostic (V de Cramér 0,39) : le suivi (`follow_up`, 3 704 images) "
        "n'existe que pour des nævus et tous les mélanomes sont confirmés par histologie. Un modèle qui l'utiliserait "
        "obtiendrait des performances artificielles. Nous l'excluons des entrées et ne l'utilisons que pour l'analyse "
        "des limites (section 6).")

    # ------------------------------------------------------------------ 3. méthode
    r.h("3. Méthode", 1)
    r.h("3.1 Découpage et prétraitement", 2)
    r.p("Les lésions sont réparties, stratifiées par diagnostic, en **70 % entraînement, 10 % validation, 10 % "
        "calibration, 10 % test** (graine 42). La validation sert à l'arrêt de l'entraînement et au réglage des "
        "règles de décision (seuil de coût, poids de M4, variante de FiLM, méthode conforme) ; la calibration sert "
        "uniquement à la prédiction conforme ; le test n'est utilisé qu'une fois, pour l'évaluation. Aucune lésion "
        "n'apparaît dans deux jeux (vérifié par une assertion).")
    r.table(tableau_decoupage(), "Découpage par lésion : nombre de lésions (et d'images) par classe et par jeu.",
            col_widths_cm=[2.2, 3.2, 3.0, 3.0, 3.0])
    r.p("Les variables cliniques sont encodées sur le train uniquement : âge imputé par la médiane et accompagné d'un "
        "indicateur de valeur manquante, puis standardisé ; sexe et localisation en one-hot avec une catégorie "
        "« unknown » (20 variables au total). Les images sont redimensionnées une fois en 224 × 224 et normalisées "
        "selon ImageNet ; l'augmentation (retournements, rotation quelconque, zoom ×1–1,25, translation ±6 %, "
        "luminosité, contraste et saturation ±15 %) est appliquée au train seulement, par lot sur GPU.")
    r.h("3.2 Modèles", 2)
    r.bullets([
        "**M1 — image seule** : EfficientNet-B0 [11] pré-entraîné sur ImageNet (4,0 M paramètres), tête "
        "Dropout(0,3) puis linéaire.",
        "**M2 — clinique seule** : XGBoost [12] ; hyperparamètres et nombre d'arbres choisis par validation croisée à "
        "5 plis sur le train, groupée par lésion (profondeur 2, 400 arbres), comparé à une forêt aléatoire.",
        "**M3 — fusion précoce** : caractéristiques de l'image (1 280) concaténées à un encodage clinique (MLP "
        "20 → 64 → 64), puis tête linéaire.",
        "**M4 — fusion tardive** : p = w · p_M1 + (1 − w) · p_M2, w choisi sur la validation (F1 macro).",
        "**M5 — modèle proposé** : FiLM sur les 1 280 canaux finaux, h ← (1 + γ) ⊙ h + β, avec (γ, β) produits par "
        "le MLP clinique (4,25 M paramètres). Les générateurs sont initialisés à zéro : au départ, M5 est exactement "
        "le CNN pré-entraîné. La perte est pondérée par classe (poids ∝ (n_max / n_k)^0,5, ×2 pour le mélanome).",
    ])
    r.figure(FIG / "06_schema_M5.png", "Architecture et chaîne de décision du modèle proposé M5.", width_cm=16.5)
    r.p("Une variante appliquant FiLM à trois étages du réseau (192, 320 et 1 280 canaux) a été comparée sur la "
        "validation (graine 0) avec une règle fixée à l'avance (meilleur F1 macro de validation) : 0,662 contre 0,698 "
        "pour la modulation des seuls canaux finaux, qui est retenue.")
    r.h("3.3 Entraînement", 2)
    r.p("Tous les réseaux partagent la même recette ; seules la fusion et la perte changent : AdamW (taux 3·10⁻⁴ pour "
        "le tronc, 10⁻³ pour les couches nouvelles, décroissance 0,01), lots de 32, schéma cosinus avec une époque de "
        "chauffe, précision mixte, **15 époques au plus, meilleure époque et arrêt anticipé (patience 5) selon le F1 "
        "macro de validation**, prédiction finale moyennée sur quatre retournements. Chaque configuration est "
        "entraînée avec trois graines (0, 1, 2). Les 19 entraînements ont duré 2 h 17 sur une RTX 3050 Laptop "
        "(4 Go), soit environ 7 minutes chacun.")
    r.h("3.4 Décision sensible au coût", 2)
    r.p("La matrice de coût vaut 0 pour une bonne réponse, R pour un mélanome manqué et 1 pour toute autre erreur "
        "(dont la fausse alerte mélanome). La règle de décision prédit « mélanome » si p(mel) ≥ t, sinon la classe "
        "non-mélanome la plus probable ; t est choisi sur la validation pour minimiser le coût moyen (grille de 0,01 à "
        "0,99). R vaut 10 par défaut ; 5 et 20 sont étudiés. Pour une comparaison équitable, **cette règle est "
        "appliquée à tous les modèles**, en plus de la décision classique (classe la plus probable).")
    r.h("3.5 Abstention par prédiction conforme", 2)
    r.p("La prédiction conforme « split » [5, 6] fixe sur le jeu de calibration un seuil tel que l'ensemble de "
        "prédiction contienne la vraie classe avec une probabilité d'au moins 1 − α (α = 0,1), sans hypothèse sur le "
        "modèle, si calibration et test sont échangeables. Trois scores sont comparés : LAC [13], APS randomisé [14] "
        "et LAC conditionnel par classe (« Mondrian »), qui garantit la couverture pour chaque classe. La méthode est "
        "choisie **sur la validation** avec une règle fixée à l'avance : parmi celles qui couvrent le mélanome à au "
        "moins 90 %, celle qui traite le plus de cas. L'IA décide seule si l'ensemble est un singleton qui coïncide "
        "avec la décision au coût ; sinon le cas est renvoyé au médecin.")
    r.h("3.6 Évaluation et statistiques", 2)
    r.p("Sur le test : F1 macro, exactitude équilibrée, AUC un-contre-tous (macro), AUC mélanome, sensibilité et "
        "spécificité mélanome, coût attendu, matrices de confusion, couverture conforme, taux d'abstention et nombre de "
        "mélanomes « manqués en silence » (classés bénins sans renvoi). Les résultats sont donnés en moyenne ± "
        "écart-type sur trois graines. Les comparaisons clés ont un intervalle de confiance à 95 % par bootstrap "
        "apparié : 2 000 rééchantillonnages des **lésions** du test (les images d'une même lésion sont corrélées), la "
        "métrique étant moyennée sur les trois graines dans chaque rééchantillon.")

    # ------------------------------------------------------------------ 4. résultats
    r.h("4. Résultats", 1)
    r.h("4.1 Unimodal contre multimodal", 2)
    main_models = ["M1 image", "M2 clinique", "M3 concaténation", "M4 fusion tardive", "M5 FiLM + coût (proposé)"]
    r.table(tableau_comparaison(main_models),
            "Performances sur le test (moyenne ± écart-type, 3 graines) pour les deux règles de décision.",
            col_widths_cm=[2.0, 1.3] + [1.9] * 7, font_size=7)
    r.figure(FIG / "07_comparaison_modeles.png",
             "Comparaison des modèles (○ décision classique, ● décision au coût R = 10 ; barres : écart-type).")
    r.p("**L'image domine.** M1 atteint un F1 macro de 0,646 et une AUC macro de 0,956 ; M2, avec le seul contexte, "
        "plafonne à 0,165 et prédit presque toujours « nævus » (log-loss de validation 0,960 contre 1,166 pour une "
        "prédiction constante égale aux fréquences : le contexte est informatif, mais faiblement).")
    r.p("**Le contexte aide modestement, à condition d'être fusionné tôt.** M3 dépasse M1 en F1 macro (+0,038, "
        "IC [+0,005 ; +0,074]). La fusion tardive M4 n'apporte rien (exactitude équilibrée −0,011, IC "
        "[−0,022 ; −0,002]) : le poids appris donne 75 à 95 % à l'image.")
    r.p("**M5 en décision classique** dépasse M1 en exactitude équilibrée (+0,051, IC [+0,023 ; +0,084]) et en "
        "sensibilité mélanome (+0,080, IC [+0,025 ; +0,140]). **Le seuil de coût est le levier principal** : appliqué "
        "à M1 seul, il porte la sensibilité de 0,593 à 0,811. Le système proposé (M5 au coût) atteint 0,882 et réduit "
        "le coût attendu de 0,595 à 0,389 par rapport au classifieur classique (−0,206, IC [−0,330 ; −0,106]), au prix "
        "d'un F1 macro plus bas (−0,037, IC [−0,071 ; −0,004]) et d'une spécificité mélanome de 0,775 au lieu de 0,940.")
    r.table(tableau_bootstrap(),
            "Différences appariées (A − B) sur le test avec IC 95 % par bootstrap au niveau lésion (2 000 tirages, "
            "moyenne des 3 graines). * : intervalle excluant 0. Pour le coût, une valeur négative favorise A.",
            col_widths_cm=[4.6, 2.4, 2.4, 2.4, 2.4, 2.4], font_size=7)
    r.p("À règle de décision égale (tous au coût), M5 dépasse M1 en sensibilité (+0,071) et en exactitude "
        "équilibrée (+0,034), M3 et M4 en sensibilité. Mais **l'AUC mélanome, indépendante de tout seuil, ne diffère "
        "significativement entre aucun modèle** (M5 0,920 contre 0,909 pour M1, IC [−0,006 ; +0,029]) : une partie du "
        "gain de sensibilité correspond à un point de fonctionnement plus « alarmiste », pas à une meilleure "
        "discrimination.")
    r.h("4.2 Études d'ablation", 2)
    r.figure(FIG / "07_ablations.png", "Ablations de M5 (test, 3 graines).")
    r.bullets([
        "**Sans FiLM** (concaténation, même perte, même seuil) : M5 garde un avantage en sensibilité mélanome "
        "(+0,065, IC [+0,030 ; +0,102]) et en coût (−0,045, IC [−0,094 ; −0,002]) ; F1 macro et AUC mélanome ne "
        "diffèrent pas significativement.",
        "**Réplication** — FiLM contre concaténation avec la perte classique (M5 sans coût contre M3) : sensibilité "
        "+0,065 (IC [+0,026 ; +0,112]), coût −0,028 (non significatif). L'effet de FiLM va dans le même sens dans deux "
        "comparaisons indépendantes.",
        "**Sans perte de coût** : aucune différence significative (sensibilité −0,009, IC [−0,037 ; +0,020]). Une fois "
        "le seuil réglé sur la validation, la pondération de la perte est redondante.",
        "**Sans abstention** : voir 4.4 ; c'est l'ingrédient de sécurité le plus fort.",
    ])
    r.h("4.3 Sensibilité au rapport de coût", 2)
    r.figure(FIG / "08_sensibilite_cout.png", "Effet du rapport de coût R sur M1, M3, M4 et M5 (moyenne 3 graines).")
    r.p("M5 a le coût attendu le plus bas pour R = 10 (0,389) et R = 20 (0,438) ; pour R = 5, M3 et M5 sont à égalité "
        "(0,306 et 0,308). Quand R augmente, le seuil de M5 baisse (0,24 → 0,10 → 0,03), la sensibilité mélanome monte "
        "(0,79 → 0,88 → 0,94) et la spécificité baisse (0,87 → 0,78 → 0,70). Le seuil réglé sur une validation de 61 "
        "lésions de mélanome est instable d'une graine à l'autre (pour M5 et R = 10 : 0,05, 0,03 et 0,22).")
    r.figure(FIG / "08_matrices_confusion.png",
             "Matrices de confusion du test (3 graines cumulées) : M1 en décision classique et M5 au coût.")
    r.p("La confusion dominante est mélanome / nævus. M1 classique confond en moyenne 29,7 mélanomes avec des nævus "
        "et 28,7 nævus avec des mélanomes ; M5 au coût ramène les premiers à 11,3 mais déclenche 129 alertes sur des "
        "nævus (19 % d'entre eux). Les alertes de M5 portent aussi sur des carcinomes basocellulaires (30 %) et des "
        "kératoses actiniques (51 %), lésions elles-mêmes malignes ou pré-malignes qui justifient de toute façon un "
        "avis médical.")
    r.h("4.4 Abstention et sécurité", 2)
    r.table(tableau_conforme_val(),
            "Choix de la méthode conforme sur la validation (calibration → mesure sur la validation, M5, 3 graines).",
            col_widths_cm=[4.6, 2.2, 2.4, 2.4, 2.2, 3.0], font_size=8)
    r.p("En couverture moyenne, les trois méthodes sont proches de 0,88–0,89 ; mais LAC et APS ne couvrent le "
        "mélanome qu'à 0,846 et 0,877 sur la validation : la garantie « en moyenne » cache une sous-couverture de la "
        "classe la plus grave. **Mondrian** couvre le mélanome à 0,937 et est retenu. Sur le test, M5 avec Mondrian "
        "atteint une couverture de 0,889 (cible 0,90 ; écart compatible avec la variabilité d'un test de 747 lésions) "
        "et une couverture mélanome de 0,923.")
    r.table(tableau_abstention(),
            "Abstention conforme (Mondrian, α = 0,1) sur le test, moyenne de 3 graines ; 113 mélanomes au test.",
            col_widths_cm=[3.4, 1.5, 1.6, 1.6, 1.6, 1.6, 1.5, 1.7, 2.2], font_size=7)
    r.p("L'IA prudente traite seule **65,5 %** des cas (F1 macro 0,819, exactitude 0,901 sur ces cas). Sur les 113 "
        "mélanomes, 57 sont renvoyés au médecin, 49 détectés par l'IA et **6,7 seulement classés bénins sans renvoi**, "
        "contre 46 pour M1 en décision classique et 13,7 pour M1 avec la même abstention. Les modèles FiLM (M5 : 6,7 ; "
        "M5 sans coût : 7,0) font mieux que les modèles à concaténation (M3 : 10,3 ; M5 sans FiLM : 11,7).")
    r.figure(FIG / "08_risque_couverture.png",
             "Gauche : erreur sur les cas traités selon la part traitée. Droite : mélanomes manqués en silence.")
    r.p("À couverture égale, l'erreur globale de M5 n'est pas plus faible que celle de M1, et un simple classement par "
        "confiance maximale fait aussi bien que la prédiction conforme sur ce critère. **L'apport de la prédiction "
        "conforme n'est pas un meilleur taux d'erreur mais une garantie de couverture et une protection explicite du "
        "mélanome** ; l'apport de M5 se lit sur les mélanomes manqués en silence, environ deux fois moins nombreux "
        "qu'avec M1 à couverture égale.")
    r.table(tableau_triage(),
            "Lecture clinique « malin / bénin » (mel, bcc, akiec doivent voir un médecin ; abstention = renvoi).",
            col_widths_cm=[1.6, 3.4, 2.6, 2.6, 3.2, 2.8], font_size=8)
    r.p("Sur les 194 lésions malignes du test, M1 classique en laisse partir 70 (sensibilité 0,64) en renvoyant 17 % "
        "des cas ; M5 avec coût et abstention n'en laisse partir que 8,7 (sensibilité 0,955) mais renvoie 45 % des "
        "cas. **La sécurité se paie en charge de travail médical.**")
    r.h("4.5 Interprétation", 2)
    r.figure(FIG / "09_gradcam_melanome.png",
             "Grad-CAM (classe mélanome) de M1 et M5 sur des cas du test (graine 0).", width_cm=10.5)
    r.p("Sur les sept cas montrés, les deux modèles regardent la lésion elle-même et non les artefacts (règle, cercle "
        "du dermoscope). Pour les mélanomes détectés par M5 et manqués par M1, les cartes sont presque identiques "
        "alors que la probabilité change (0,19 → 0,68 ; 0,11 → 0,24) : c'est le contexte qui fait basculer la décision, "
        "pas une autre lecture spatiale. Grad-CAM [15] sert ici de contrôle qualitatif ; quelques exemples ne "
        "permettent pas de généraliser.")
    r.figure(FIG / "09_contrefactuels.png",
             "Contrefactuels : même image, âge ou localisation imposés ; p(mélanome) moyen sur le test (graine 0).")
    r.p("**L'âge domine l'effet du contexte.** Pour les mêmes images de mélanome, p(mel) moyen passe de 0,10 à 10 ans "
        "à 0,68 à 60 ans avec M5 (de 0,23 à 0,61 avec M3). C'est cliniquement plausible — le mélanome est rare chez "
        "l'enfant — mais c'est aussi un risque d'équité pour les patients jeunes (section 6). La localisation pèse "
        "moins ; chez M5, le pied augmente p(mel) (0,71 contre environ 0,57).")
    r.figure(FIG / "09_film_localisation.png",
             "Paramètres FiLM : intensité moyenne |γ| par localisation et γ moyen sur les 24 canaux les plus modulés.")
    r.p("γ suit un motif commun à toutes les localisations, d'intensité variable : la modulation est la plus forte pour "
        "le pied, la poitrine et le tronc, la plus faible pour le visage et le membre supérieur. Sur les canaux les plus "
        "modulés, le gain 1 + γ varie entre environ 0 et 2 : le contexte peut presque éteindre ou doubler un canal "
        "visuel.")
    r.figure(FIG / "09_shap_M2.png", "Importance SHAP des variables cliniques dans M2 (test, graine 0).")
    r.p("Les valeurs SHAP [16] du modèle clinique confirment l'exploration : l'âge est de loin la variable la plus "
        "importante ; « membre inférieur » pèse surtout pour le dermatofibrome, « visage » pour les kératoses "
        "actiniques et bénignes.")
    r.h("4.6 Robustesse au contexte manquant (bonus)", 2)
    r.table(tableau_bonus(), "Test avec contexte complet ou entièrement manquant (décision classique, 3 graines).",
            col_widths_cm=[3.0, 3.6, 2.4, 2.4, 2.4, 2.4], font_size=8)
    r.p("Privé de contexte, **M5 s'effondre** (F1 macro 0,515, sensibilité mélanome 0,189) : la modulation FiLM rend "
        "le modèle dépendant du contexte. Entraîné en masquant le contexte 25 % du temps (dropout de modalité), il "
        "reste robuste sans contexte (F1 0,629, sensibilité 0,625) pour un coût modéré avec contexte (F1 0,651 contre "
        "0,674). Un modèle FiLM déployé là où le contexte peut manquer doit être entraîné de cette façon.")

    # ------------------------------------------------------------------ 5. discussion
    r.h("5. Discussion", 1)
    r.p("**Plus sûre : oui.** Toutes les mesures de sécurité vont dans le même sens et la plupart sont "
        "significatives : sensibilité mélanome (0,593 → 0,882), coût attendu (0,595 → 0,389), mélanomes manqués en "
        "silence (46 → 6,7 sur 113), lésions malignes non renvoyées (70 → 8,7 sur 194).")
    r.p("**Meilleure : pas au sens des métriques habituelles.** Le F1 macro baisse, la spécificité aussi, et 45 % des "
        "cas sont renvoyés à un médecin. L'IA prudente n'est pas un meilleur classifieur ; c'est un meilleur **outil de "
        "tri**, à un point de fonctionnement choisi pour le coût clinique. Ce compromis doit être discuté avec les "
        "cliniciens : la valeur de R et la capacité d'accueil des consultations conditionnent le bon réglage.")
    r.p("**D'où vient le gain ?** Principalement de la couche de décision : le seuil de coût (qui rend la perte "
        "pondérée inutile) et l'abstention conforme conditionnelle au mélanome. FiLM apporte un supplément modeste "
        "mais reproduit dans deux comparaisons, sans amélioration significative de l'AUC. Ce résultat est cohérent avec "
        "la faiblesse des variables cliniques (V de Cramér ≤ 0,25) : le contexte ne peut corriger l'image qu'à la marge. "
        "La prédiction conforme n'améliore pas la courbe risque-couverture par rapport à la confiance maximale, mais "
        "elle donne une garantie interprétable et, dans sa version par classe, protège explicitement le mélanome — "
        "ce que la couverture marginale ne fait pas.")

    # ------------------------------------------------------------------ 6. limites
    r.h("6. Limites", 1)
    r.bullets([
        "**Déséquilibre et petits effectifs** : 8 lésions de dermatofibrome et 9 de lésions vasculaires au test ; "
        "seuils et quantiles conformes estimés sur environ 61 lésions de mélanome, d'où une instabilité entre graines.",
        "**Contexte clinique pauvre** : trois variables, âge arrondi à 5 ans, codage hétérogène de la localisation "
        "entre centres.",
        "**Deux centres seulement**, peaux majoritairement claires, appareils limités ; aucune validation externe.",
        "**Plusieurs images par lésion** : la garantie conforme suppose l'échangeabilité, vraie au niveau lésion mais "
        "pas entre images corrélées (couverture test 0,889 pour 0,90 visé).",
        "**Vérité terrain hétérogène** : histologie pour 53 % des images. Les fausses alertes de M5 au coût touchent "
        "41 % des lésions bénignes histologiques (lésions suspectes, retirées) contre 5 % des lésions suivies : les "
        "nævus suivis, « faciles », gonflent les performances globales.",
        "**Validation à double usage** : elle sert à l'arrêt de l'entraînement et au réglage des seuils, ce qui rend "
        "les seuils légèrement optimistes ; la calibration conforme reste, elle, indépendante.",
        "**Équité** : la sensibilité mélanome est faible chez les moins de 50 ans pour tous les modèles (M5 au coût "
        "0,59, M1 au coût 0,62, sur 22 mélanomes seulement) ; la forte dépendance à l'âge appelle une vigilance "
        "particulière.",
        "**Matrice de coût simplifiée** (une seule classe grave, R arbitraire) ; elle devrait être fixée avec des "
        "dermatologues.",
        "**Pas un dispositif médical** : aucune utilisation diagnostique réelle.",
    ])

    # ------------------------------------------------------------------ 7. conclusion
    r.h("7. Conclusion et perspectives", 1)
    r.p("Une IA qui utilise le contexte du patient, tient compte du coût d'un mélanome manqué et s'abstient quand elle "
        "doute est **nettement plus sûre** qu'un classifieur classique sur HAM10000, sans être meilleure sur les "
        "métriques de classification habituelles. Le gain vient surtout des règles de décision ; la fusion FiLM apporte "
        "un supplément modeste et reproductible, à condition d'être entraînée avec un dropout du contexte.")
    r.p("**Travaux à poursuivre** : validation externe (ISIC 2019/2020, autres phototypes) ; matrice de coût fixée avec "
        "des cliniciens ; seuils et calibration estimés sur des jeux plus grands ou par validation croisée ; prédiction "
        "conforme au niveau lésion ; résolution plus élevée et ensembles de modèles ; correction du biais lié à l'âge ; "
        "étude de la charge de travail induite par les renvois.")

    # ------------------------------------------------------------------ références
    r.h("Références", 1)
    refs = [
        "Arnold M, Singh D, Laversanne M, et al. Global burden of cutaneous melanoma in 2020 and projections to 2040. "
        "JAMA Dermatol. 2022;158(5):495-503.",
        "Esteva A, Kuprel B, Novoa RA, et al. Dermatologist-level classification of skin cancer with deep neural "
        "networks. Nature. 2017;542:115-118.",
        "Tschandl P, Codella N, Akay BN, et al. Comparison of the accuracy of human readers versus machine-learning "
        "algorithms for pigmented skin lesion classification. Lancet Oncol. 2019;20(7):938-947.",
        "Perez E, Strub F, de Vries H, Dumoulin V, Courville A. FiLM: Visual reasoning with a general conditioning "
        "layer. AAAI 2018:3942-3951. doi:10.1609/aaai.v32i1.11671.",
        "Vovk V, Gammerman A, Shafer G. Algorithmic Learning in a Random World. Springer, 2005.",
        "Angelopoulos AN, Bates S. A gentle introduction to conformal prediction and distribution-free uncertainty "
        "quantification. arXiv:2107.07511, 2021.",
        "Li W, Zhuang J, Wang R, Zhang J, Zheng WS. Fusing metadata and dermoscopy images for skin disease diagnosis. "
        "IEEE ISBI 2020.",
        "Pacheco AGC, Krohling RA. An attention-based mechanism to combine images and metadata in deep learning models "
        "applied to skin cancer classification. IEEE J Biomed Health Inform. 2021.",
        "Tschandl P, Rosendahl C, Kittler H. The HAM10000 dataset, a large collection of multi-source dermatoscopic "
        "images of common pigmented skin lesions. Sci Data. 2018;5:180161. doi:10.1038/sdata.2018.161.",
        "Codella N, Rotemberg V, Tschandl P, et al. Skin lesion analysis toward melanoma detection 2018: a challenge "
        "hosted by the International Skin Imaging Collaboration (ISIC). arXiv:1902.03368, 2019.",
        "Tan M, Le QV. EfficientNet: Rethinking model scaling for convolutional neural networks. ICML 2019.",
        "Chen T, Guestrin C. XGBoost: A scalable tree boosting system. KDD 2016.",
        "Sadinle M, Lei J, Wasserman L. Least ambiguous set-valued classifiers with bounded error levels. J Am Stat "
        "Assoc. 2019;114(525):223-234.",
        "Romano Y, Sesia M, Candès E. Classification with valid and adaptive coverage. NeurIPS 2020.",
        "Selvaraju RR, Cogswell M, Das A, et al. Grad-CAM: Visual explanations from deep networks via gradient-based "
        "localization. ICCV 2017.",
        "Lundberg SM, Lee SI. A unified approach to interpreting model predictions. NeurIPS 2017.",
    ]
    for i, ref in enumerate(refs, 1):
        r.p(f"[{i}] {ref}", size=9)

    # ------------------------------------------------------------------ annexes
    r.page_break()
    r.h("Annexe A — Reproductibilité", 1)
    r.p("Le code est dans `projet/src/` (README à la racine de `projet/`). `python -m src.run_all` relance toute la "
        "chaîne (prétraitement, 19 entraînements, résultats, analyses) en sautant ce qui est déjà fait ; "
        "`notebooks/projet_ham10000.ipynb` suit les dix étapes et relit les prédictions sauvegardées. Environnement : "
        "Python 3.13, PyTorch 2.11 (CUDA 12.8), scikit-learn 1.9, XGBoost 3.4 ; versions exactes dans "
        "`requirements.txt`. Le découpage utilisé est enregistré dans `resultats/split_lesions.csv`.")
    r.table(tableau_entrainements(), "Entraînements réalisés (meilleur F1 macro de validation, durée).",
            col_widths_cm=[3.4, 1.6, 2.6, 2.8, 1.8, 2.4], font_size=8)
    r.h("Annexe B — Figures complémentaires", 1)
    r.figure(FIG / "02_classes.png", "Images et lésions par classe.")
    r.figure(FIG / "02_age_par_classe.png", "Âge par diagnostic.", width_cm=12)
    r.figure(FIG / "02_exemples_images.png", "Exemples d'images par classe.", width_cm=13)
    r.figure(FIG / "03_augmentations.png", "Augmentations appliquées à l'entraînement.")
    r.figure(FIG / "04_courbes_apprentissage.png", "F1 macro de validation par époque.", width_cm=13)
    r.figure(FIG / "06_M4_poids.png", "Choix du poids de fusion de M4 sur la validation.", width_cm=11)
    r.figure(FIG / "09_mel_vs_nv.png", "Distribution de p(mélanome) pour les nævus et les mélanomes du test.")

    out = PROJ / "rapport" / "rapport_projet_ham10000.docx"
    r.save(out)
    print("écrit :", out, "| figures :", r.n_fig, "| tableaux :", r.n_tab)
    docx_to_pdf(out, out.with_suffix(".pdf"))
    print("PDF :", out.with_suffix(".pdf"))


if __name__ == "__main__":
    main()
