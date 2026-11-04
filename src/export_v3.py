"""Paquet de modèle v3 pour l'application (HAM10000 + BCN20000), après la décision de application/docs/plan_v3.md.

1. Réglages fixés par le plan : seuils de coût sur la validation combinée, seuils conformes Mondrian sur la
   calibration combinée (fonctions de la v1).
2. Fiche : mesures sur le test HAM et sur le test BCN, séparément (calculées une seule fois, comme src.evaluer_v3).
3. Prétraitement : recadrage du champ du dermoscope (même règle qu'à l'entraînement, vérifiée ici sur des images
   des deux bases) ; localisation détaillée de l'interface ramenée aux zones communes.
4. Détecteur d'images hors sujet recalculé sur les images d'entraînement v3 (même méthode que la v2).
5. Textes de la fiche en français, anglais et arabe ; référence de non-régression (images des deux tests).

Usage : python -m src.export_v3
"""
from __future__ import annotations

import json
import shutil
from datetime import date

import numpy as np
import pandas as pd
from PIL import Image

from . import config as C
from .analyses import MALIGNANT
from .conformal import Conformal
from .data import ClinicalEncoder
from .decision import decide, tune_mel_threshold
from .donnees_v3 import ZONES_HAM, get_split_v3, zone_utile
from .evaluer_v3 import P, ensemble
from .export import metriques_fiche, sha256
from .export_v2 import Moteur, _ouvrir, detecteur_hors_sujet

APP_DIR = C.PROJECT_DIR / "application"
BUNDLE = "ham10000-bcn20000-m5-v3"
PROFILS = {"complet": ("V3_M5_B2", "p"), "sans_contexte": ("V3_M5_dropClin_B2", "p_noclin")}
SOURCES = {"HAM10000": "metriques_test", "BCN20000": "metriques_test_bcn"}
RECADRAGE = {"cote_analyse": 256, "coin": 20, "seuil_coins": 30, "seuil_clair": 20, "part_claire_min": 0.15,
             "marge": 0.97}


def calibrer(t: pd.DataFrame) -> tuple[dict, Conformal]:
    v, c = t[t.split == "val"], t[t.split == "calib"]
    seuils = {str(R): tune_mel_threshold(P(v), v.y.to_numpy(), R)[0] for R in C.COST_RATIOS}
    return seuils, Conformal("mondrian", C.ALPHA).fit(P(c), c.y.to_numpy())


def sensibilite_par_age(t: pd.DataFrame, seuil: float) -> dict:
    mel = t.y.to_numpy() == C.MEL
    alerte = decide(P(t), seuil) == C.MEL
    age = t.age.to_numpy()
    jeune, ancien = mel & (age < 50), mel & (age >= 50)
    return {"jeunes": float(alerte[jeune].mean()), "n_jeunes": int(jeune.sum()),
            "ages": float(alerte[ancien].mean()), "n_ages": int(ancien.sum())}


def verifier_recadrage(df: pd.DataFrame, n: int = 60) -> None:
    """La règle du moteur (paramètres du manifest) = celle de l'entraînement, sur des images des deux bases."""
    import sys
    sys.path.insert(0, str(APP_DIR / "backend"))
    from dermia.engine.engine import zone_utile as zone_moteur
    rng = np.random.default_rng(0)
    recadrees = 0
    for src in ("HAM10000", "BCN20000"):
        for p in rng.choice(df[df.source == src].path.to_numpy(), n, replace=False):
            im = _ouvrir(p)
            a, b = zone_utile(im), zone_moteur(im, RECADRAGE)
            assert a == b, (p, a, b)
            recadrees += a is not None
    print(f"Recadrage : moteur = entraînement sur {2 * n} images ({recadrees} recadrées)")


def textes(sens: dict, n_mel_val: int, hs: dict, silence: dict) -> dict:
    ev = hs["evaluation"]
    sh, sb = sens["HAM10000"], sens["BCN20000"]
    pfr = lambda x: f"{100 * x:.0f} %"                   # noqa: E731
    pen = lambda x: f"{100 * x:.0f}%"                    # noqa: E731
    fr = {
        "description": "Classification de lésions dermoscopiques (7 classes) par EfficientNet-B2 (288 px) guidé par "
                       "le contexte patient (FiLM), entraîné sur HAM10000 et BCN20000 (trois centres), décision "
                       "sensible au coût, abstention conforme (Mondrian) et refus des images hors sujet. Le champ "
                       "circulaire du dermoscope est recadré avant l'analyse. Moyenne de 3 graines.",
        "usage_prevu": "Aide à la décision pour professionnels de santé, sur images dermoscopiques. Ne remplace pas "
                       "l'examen clinique ni l'histologie.",
        "statut": "RECHERCHE — usage non commercial — pas un dispositif médical",
        "consequence": "HAM10000 et BCN20000 sont publiés sous licence non commerciale : ce modèle ne peut pas être "
                       "vendu ni utilisé commercialement. Pour un usage commercial, réentraîner sur des données sous "
                       "licence adaptée et obtenir le marquage réglementaire.",
        "centres": "Vienne (Autriche), Queensland (Australie), Barcelone (Espagne)",
        "licence": "CC BY-NC 4.0 (Attribution - Pas d'utilisation commerciale)",
        "decision_regle": "mélanome si p(mel) ≥ seuil, sinon la classe non-mélanome la plus probable",
        "abstention_methode": "LAC conditionnel par classe (Mondrian)",
        "abstention_regle": "traité si l'ensemble conforme est un singleton égal à la décision au coût",
        "calibre_complet": "contexte complet", "calibre_sans": "contexte entièrement manquant",
        "limites": [
            "Trois centres, peaux majoritairement claires : performances inconnues ailleurs. Le test BCN20000 vient "
            "du même hôpital qu'une partie de l'entraînement : ce n'est pas une validation externe.",
            f"Sensibilité mélanome (test, R = 10) chez les moins de 50 ans : {pfr(sh['jeunes'])} sur HAM10000 "
            f"({sh['n_jeunes']} mélanomes), {pfr(sb['jeunes'])} sur BCN20000 ({sb['n_jeunes']} mélanomes).",
            f"Mélanomes classés bénins sans renvoi au médecin (test, contexte complet) : {silence['HAM10000']} sur "
            f"HAM10000, {silence['BCN20000']} sur BCN20000. Sur la validation et la calibration HAM, l'ordre de "
            "grandeur est le même que celui du modèle précédent (14 contre 15 mélanomes sur 227).",
            f"Seuils estimés sur la validation ({n_mel_val} images de mélanome, deux bases réunies).",
            f"Images hors sujet : {pfr(ev['rejet_hors_sujet'])} refusées sur {ev['n_hors_sujet']} images très "
            "différentes ; une photo de peau prise sans dermoscope n'a pas pu être testée et peut passer le contrôle.",
            "BCN20000 ne donne pas d'identifiant patient : un même patient peut figurer dans l'entraînement et le test.",
            "Critères ABCD automatiques : indicateurs au pouvoir discriminant modeste (AUC 0,66 à 0,73 entre "
            "mélanome et nævus sur le test HAM10000).",
        ],
    }
    en = {
        "description": "Classification of dermoscopic lesions (7 classes) by EfficientNet-B2 (288 px) guided by the "
                       "patient context (FiLM), trained on HAM10000 and BCN20000 (three centres), cost-sensitive "
                       "decision, conformal abstention (Mondrian) and refusal of out-of-scope images. The circular "
                       "field of the dermatoscope is cropped before analysis. Average of 3 seeds.",
        "usage_prevu": "Decision support for healthcare professionals, on dermoscopic images. Does not replace "
                       "clinical examination or histology.",
        "statut": "RESEARCH — non-commercial use — not a medical device",
        "consequence": "HAM10000 and BCN20000 are released under a non-commercial licence: this model cannot be sold "
                       "or used commercially. For commercial use, retrain on suitably licensed data and obtain "
                       "regulatory approval.",
        "centres": "Vienna (Austria), Queensland (Australia), Barcelona (Spain)",
        "licence": "CC BY-NC 4.0 (Attribution - NonCommercial)",
        "decision_regle": "melanoma if p(mel) ≥ threshold, otherwise the most probable non-melanoma class",
        "abstention_methode": "Class-conditional LAC (Mondrian)",
        "abstention_regle": "handled if the conformal set is a singleton equal to the cost-based decision",
        "calibre_complet": "complete context", "calibre_sans": "entirely missing context",
        "limites": [
            "Three centres, mostly fair skin: performance unknown elsewhere. The BCN20000 test comes from the same "
            "hospital as part of the training data: it is not an external validation.",
            f"Melanoma sensitivity (test, R = 10) under 50 years: {pen(sh['jeunes'])} on HAM10000 "
            f"({sh['n_jeunes']} melanomas), {pen(sb['jeunes'])} on BCN20000 ({sb['n_jeunes']} melanomas).",
            f"Melanomas classified benign without referral (test, complete context): {silence['HAM10000']} on "
            f"HAM10000, {silence['BCN20000']} on BCN20000. On the HAM validation and calibration sets, the order of "
            "magnitude matches the previous model (14 versus 15 melanomas out of 227).",
            f"Thresholds estimated on the validation set ({n_mel_val} melanoma images, both datasets).",
            f"Out-of-scope images: {pen(ev['rejet_hors_sujet'])} refused out of {ev['n_hors_sujet']} very different "
            "images; a skin photo taken without a dermatoscope could not be tested and may pass the check.",
            "BCN20000 provides no patient identifier: the same patient may appear in training and test sets.",
            "Automatic ABCD criteria: indicators with modest discriminative power (AUC 0.66 to 0.73 between "
            "melanoma and nevus on the HAM10000 test set).",
        ],
    }
    par = lambda x: f"{100 * x:.0f}%"                    # noqa: E731
    ar = {
        "description": "تصنيف آفات المنظار الجلدي (7 فئات) بواسطة EfficientNet-B2 (288 بكسل) موجَّه بسياق المريض "
                       "(FiLM)، مُدرَّب على HAM10000 وBCN20000 (ثلاثة مراكز)، مع قرار حساس للتكلفة، وامتناع مطابِق "
                       "(موندريان)، ورفض الصور خارج النطاق. يُقتطع الحقل الدائري للمنظار قبل التحليل. متوسط 3 نماذج.",
        "usage_prevu": "أداة مساعدة على اتخاذ القرار لمهنيي الصحة، على صور المنظار الجلدي. لا تُغني عن الفحص "
                       "السريري ولا عن الفحص النسيجي.",
        "statut": "بحث — استخدام غير تجاري — ليس جهازًا طبيًا",
        "consequence": "نُشرت HAM10000 وBCN20000 بترخيص غير تجاري: لا يجوز بيع هذا النموذج ولا استخدامه تجاريًا. "
                       "للاستخدام التجاري يجب إعادة تدريبه على بيانات بترخيص مناسب والحصول على الاعتماد التنظيمي.",
        "centres": "فيينا (النمسا)، كوينزلاند (أستراليا)، برشلونة (إسبانيا)",
        "licence": "CC BY-NC 4.0 (نسب المصنَّف - غير تجاري)",
        "decision_regle": "ورم ميلانيني إذا كان احتماله ≥ العتبة، وإلا فالفئة غير الميلانينية الأكثر احتمالًا",
        "abstention_methode": "LAC مشروط بالفئة (موندريان)",
        "abstention_regle": "تُعالَج الحالة إذا كانت المجموعة المطابِقة عنصرًا واحدًا مطابقًا لقرار التكلفة",
        "calibre_complet": "سياق كامل", "calibre_sans": "سياق مفقود كليًا",
        "limites": [
            "ثلاثة مراكز، وأغلب البشرات فاتحة: الأداء غير معروف في غيرها. اختبار BCN20000 من المستشفى نفسه الذي جاء "
            "منه جزء من بيانات التدريب: فهو ليس تحققًا خارجيًا.",
            f"حساسية الورم الميلانيني (الاختبار، R = 10) لدى من هم دون 50 سنة: {par(sh['jeunes'])} على HAM10000 "
            f"({sh['n_jeunes']} ورمًا)، و{par(sb['jeunes'])} على BCN20000 ({sb['n_jeunes']} ورمًا).",
            f"أورام ميلانينية صُنّفت حميدة دون إحالة إلى الطبيب (الاختبار، سياق كامل): {silence['HAM10000']} على "
            f"HAM10000، و{silence['BCN20000']} على BCN20000. على مجموعتي التحقق والمعايرة من HAM، الرتبة نفسها "
            "تقريبًا كالنموذج السابق (14 مقابل 15 ورمًا من 227).",
            f"قُدِّرت العتبات على مجموعة التحقق ({n_mel_val} صورة ورم ميلانيني، من القاعدتين معًا).",
            f"الصور خارج النطاق: رُفض {par(ev['rejet_hors_sujet'])} من أصل {ev['n_hors_sujet']} صورة مختلفة تمامًا؛ "
            "لم يكن ممكنًا اختبار صورة جلد ملتقطة دون منظار، وقد تجتاز الفحص.",
            "لا توفر BCN20000 معرّفًا للمريض: قد يظهر المريض نفسه في التدريب والاختبار.",
            "معايير ABCD الآلية: مؤشرات ذات قدرة تمييز محدودة (AUC من 0,66 إلى 0,73 بين الورم الميلانيني والوحمة "
            "على اختبار HAM10000).",
        ],
    }
    return {"fr": fr, "en": en, "ar": ar}


def ecrire_reference(df: pd.DataFrame, n_par_classe: int = 2) -> None:
    """Probabilités attendues (ensemble des graines, clé « p » = contexte réel) pour des images des deux tests ;
    contexte complet → profil complet, sinon profil sans_contexte avec le contexte partiel réel."""
    attendus = {p: ensemble(PROFILS[p][0], "p", df) for p in PROFILS}
    test = attendus["complet"].query("split == 'test'")
    rng = np.random.default_rng(0)
    cas = []
    for src in SOURCES:
        t = test[test.source == src]
        complet = (t.age.notna() & (t.sex != "unknown") & (t.localization != "unknown")).to_numpy()
        for c in C.CLASSES:
            cand = np.flatnonzero(t.dx.to_numpy() == c)
            choix = list(rng.choice(cand, min(n_par_classe, len(cand)), replace=False))
            incomplets = np.flatnonzero((t.dx.to_numpy() == c) & ~complet)
            if len(incomplets) and not any(i in incomplets for i in choix):
                choix[-1] = int(incomplets[0])
            for i in choix:
                r = t.iloc[i]
                prof = "complet" if complet[i] else "sans_contexte"
                pa = attendus[prof]
                p = pa[(pa.image_id == r.image_id) & (pa.split == "test")].p.iloc[0]
                loc = r.localization
                if src == "HAM10000":                   # localisation détaillée d'origine (correspondance testée)
                    loc = df.loc[df.image_id == r.image_id, "loc_detaillee"].iloc[0]
                cas.append({"image_id": r.image_id, "source": src, "fichier": f"{r.path.parent.name}/{r.path.name}",
                            "age": None if np.isnan(r.age) else float(r.age), "sexe": r.sex, "localisation": loc,
                            "dx": r.dx, "profil": prof, "probabilites": [round(float(v), 6) for v in p]})
    ref = APP_DIR / "tests" / "reference_v3.json"
    ref.write_text(json.dumps({"description": f"Probabilités attendues (projet/resultats/predictions, {BUNDLE}), "
                                              "images des jeux de test HAM10000 et BCN20000", "cas": cas},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Référence de non-régression : {len(cas)} cas → {ref}")


def main() -> None:
    from .data import get_split
    df = get_split_v3()
    ham = get_split().set_index("image_id").localization
    df["loc_detaillee"] = df.image_id.map(ham)              # HAM : localisation d'origine (avant les zones)
    verifier_recadrage(df)
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    out = APP_DIR / "modeles" / BUNDLE
    if out.exists():
        shutil.rmtree(out)
    (out / "poids").mkdir(parents=True)

    profils, tables, sens, silence = {}, {}, {}, {}
    for nom, (exp, cle) in PROFILS.items():
        t = ensemble(exp, cle, df)
        tables[nom] = t
        seuils, cf = calibrer(t)
        fiche = {}
        for src, champ in SOURCES.items():
            te = t[(t.split == "test") & (t.source == src)]
            fiche[champ] = metriques_fiche(P(te), te.y.to_numpy(), seuils, cf)
            fiche[champ]["jeu"] = f"test {src}"
            if nom == "complet":
                sens[src] = sensibilite_par_age(te, seuils[str(C.DEFAULT_COST_RATIO)])
                silence[src] = fiche[champ]["abstention"]["melanomes_manques_en_silence"]
        meta = json.loads((C.PRED_DIR / f"{exp}_s0.json").read_text(encoding="utf-8"))
        poids = []
        for s in C.TRAIN_SEEDS:
            dst = out / "poids" / f"{exp}_s{s}.pt"
            shutil.copy2(C.CKPT_DIR / f"{exp}_s{s}.pt", dst)
            poids.append({"fichier": f"poids/{dst.name}", "sha256": sha256(dst)})
        profils[nom] = {"experience": exp, "architecture": "efficientnet_b2", "fusion": meta["fusion"],
                        "film": meta.get("film", "final"), "n_clin": enc.n_features, "poids": poids,
                        "calibre_sur": "contexte complet" if cle == "p" else "contexte entièrement manquant",
                        "thresholds": seuils, "conformal_q": [float(q) for q in cf.q], **fiche}
        print(f"{nom}: seuils {seuils} | q {np.round(cf.q, 3).tolist()}")
        for champ in SOURCES.values():
            print(f"   {fiche[champ]['jeu']} : {json.dumps(fiche[champ]['abstention'], ensure_ascii=False)}")

    manifest = {
        "nom": BUNDLE, "version": "3.0.0", "date": date.today().isoformat(),
        "description": "", "statut": "",
        "donnees_entrainement": {
            "jeu": "HAM10000 (Tschandl et al., Sci Data 2018, doi:10.1038/sdata.2018.161) + BCN20000 "
                   "(Hernández-Pérez et al., Sci Data 2024, doi:10.1038/s41597-024-03387-w)",
            "licence": "", "consequence": "", "centres": ""},
        "usage_prevu": "", "classes": C.CLASSES, "noms_classes": C.CLASS_NAMES_FR,
        "classes_malignes": [C.CLASSES[i] for i in MALIGNANT], "indice_melanome": C.MEL,
        "pretraitement": {"taille": 288, "redimensionnement": "LANCZOS, sans conserver le ratio",
                          "recadrage": RECADRAGE, "moyenne": C.IMAGENET_MEAN, "ecart_type": C.IMAGENET_STD,
                          "tta": ["identite", "flip_h", "flip_v", "flip_hv"]},
        "encodeur_clinique": {"age_mediane": enc.age_median, "age_moyenne": enc.age_mean,
                              "age_ecart_type": enc.age_std, "sexes": enc.sex_cats,
                              "localisations": enc.loc_cats, "correspondance": ZONES_HAM,
                              "variables": enc.feature_names},
        "decision": {"rapports_cout": C.COST_RATIOS, "rapport_defaut": C.DEFAULT_COST_RATIO, "regle": ""},
        "abstention": {"methode": "", "alpha": C.ALPHA, "regle": ""},
        "profils": profils, "limites": [],
    }
    assert set(ZONES_HAM.values()) <= set(enc.loc_cats), (ZONES_HAM, enc.loc_cats)
    ecrire = lambda: (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),  # noqa: E731
                                                       encoding="utf-8")
    ecrire()

    moteur = Moteur(out, device="cuda")
    hs = detecteur_hors_sujet(moteur, df, out, prefixe="14_v3", nom_test="tests HAM10000 + BCN20000 (dermoscopie)")
    manifest["hors_sujet"] = hs
    n_mel_val = int(((df.split == "val") & (df.y == C.MEL)).sum())
    tx = textes(sens, n_mel_val, hs, silence)
    fr = tx["fr"]
    manifest.update(description=fr["description"], usage_prevu=fr["usage_prevu"], statut=fr["statut"],
                    limites=fr["limites"], statut_i18n={lg: tx[lg]["statut"] for lg in tx})
    manifest["donnees_entrainement"].update(consequence=fr["consequence"], licence=fr["licence"], centres=fr["centres"])
    manifest["decision"]["regle"] = fr["decision_regle"]
    manifest["abstention"].update(methode=fr["abstention_methode"], regle=fr["abstention_regle"])
    manifest["i18n"] = {lg: {k: v for k, v in tx[lg].items() if k not in ("calibre_complet", "calibre_sans")}
                        for lg in ("en", "ar")}
    for lg in ("en", "ar"):
        manifest["i18n"][lg]["calibre_sur_complet"] = tx[lg]["calibre_complet"]
        manifest["i18n"][lg]["calibre_sur_sans_contexte"] = tx[lg]["calibre_sans"]
    ecrire()

    m2 = Moteur(out, device="cuda", verifier_empreintes=True)
    chemins, attendus = detecteur_hors_sujet.controle
    for chemin, attendu in zip(chemins, attendus):
        obtenu = m2._score_hors_sujet(m2.pretraiter(_ouvrir(chemin)))
        assert abs(obtenu - attendu) <= 5e-3 * max(1.0, abs(attendu)), (chemin, obtenu, attendu)
    print("Moteur relu : scores hors sujet reproduits.")
    ecrire_reference(df)
    print("Paquet de modèle écrit :", out)


if __name__ == "__main__":
    main()
