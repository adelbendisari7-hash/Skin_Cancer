"""Paquet de modèle v2 pour l'application.

1. Choix de l'architecture SUR LA VALIDATION, selon la règle fixée avant l'entraînement
   (application/docs/plan_v2.md) : EfficientNet-B2 (288 px) est retenu si, pour chacun des deux profils,
   l'ensemble des 3 graines atteint au moins le F1 macro ET l'AUC macro de l'ensemble EfficientNet-B0.
   Un paquet n'a qu'une taille d'image : la règle s'applique donc aux deux profils à la fois.
2. Recalibrage de l'ensemble retenu (seuils de coût sur la validation, seuils conformes sur la calibration),
   puis mesure UNE fois sur le test pour la fiche (fonction `profile_card` de la v1).
3. Détecteur d'images hors sujet (Lee et al., NeurIPS 2018) : moyennes par classe et covariance partagée
   (Ledoit-Wolf) des caractéristiques « image seule » du réseau sur le jeu d'entraînement ; score = distance
   de Mahalanobis minimale ; seuil = 99,5e centile des images de VALIDATION. Évalué ensuite sur le test et
   sur des images hors sujet (fonds d'écran, captures d'écran, images de scikit-image, images synthétiques).
4. Fiche du modèle en français, anglais et arabe ; nouvelle référence de non-régression.

Les caractéristiques sont calculées par le moteur de l'application lui-même (même prétraitement qu'en
production). Usage : python -m src.export_v2
"""
from __future__ import annotations

import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from sklearn.covariance import LedoitWolf

from . import config as C
from .analyses import MALIGNANT
from .data import ClinicalEncoder, get_split
from .decision import decide
from .export import ensemble, profile_card, sha256
from .metrics import classification_metrics

sys.path.insert(0, str(C.PROJECT_DIR / "application" / "backend"))
from dermia.engine import Moteur  # noqa: E402  (moteur de l'application)

APP_DIR = C.PROJECT_DIR / "application"
BUNDLE = "ham10000-m5-v2"
CANDIDATS = {
    "efficientnet_b0": {"taille": 224, "complet": ("M5", "p"), "sans_contexte": ("M5_dropClin", "p_noclin")},
    "efficientnet_b2": {"taille": 288, "complet": ("M5_B2", "p"), "sans_contexte": ("M5_dropClin_B2", "p_noclin")},
}
PROFILS = ("complet", "sans_contexte")
CENTILE_SEUIL = 99.5


# ---------------------------------------------------------------- 1. choix de l'architecture
def choisir_architecture(df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    lignes = []
    for profil in PROFILS:
        for arch, c in CANDIDATS.items():
            exp, cle = c[profil]
            pv, yv, _ = ensemble(exp, cle, df)["val"]
            m = classification_metrics(yv, pv.argmax(1), pv)
            lignes.append({"profil": profil, "architecture": arch, "experience": exp,
                           "F1 macro": round(m["F1 macro"], 4), "AUC OvR macro": round(m["AUC OvR macro"], 4),
                           "AUC mel": round(m["AUC mel"], 4), "Exactitude équilibrée": round(m["Exactitude équilibrée"], 4)})
    t = pd.DataFrame(lignes)
    ok = []
    for profil in PROFILS:
        b0 = t[(t.profil == profil) & (t.architecture == "efficientnet_b0")].iloc[0]
        b2 = t[(t.profil == profil) & (t.architecture == "efficientnet_b2")].iloc[0]
        ok.append(b2["F1 macro"] >= b0["F1 macro"] and b2["AUC OvR macro"] >= b0["AUC OvR macro"])
    choix = "efficientnet_b2" if all(ok) else "efficientnet_b0"
    t["regle_satisfaite_par_b2"] = t.profil.map(dict(zip(PROFILS, ok)))
    t.to_csv(C.TAB_DIR / "12_choix_architecture_validation.csv", index=False, encoding="utf-8")
    print(t.to_string(index=False))
    print(f"→ architecture retenue (règle pré-enregistrée, validation) : {choix}")
    return choix, t


def mesures_test_apres_choix(df: pd.DataFrame) -> pd.DataFrame:
    """Test des deux architectures, calculé APRÈS le choix (information, ne sert à aucune décision)."""
    lignes = []
    for profil in PROFILS:
        for arch, c in CANDIDATS.items():
            exp, cle = c[profil]
            pt, yt, _ = ensemble(exp, cle, df)["test"]
            m = classification_metrics(yt, pt.argmax(1), pt)
            lignes.append({"profil": profil, "architecture": arch, "F1 macro": round(m["F1 macro"], 4),
                           "AUC OvR macro": round(m["AUC OvR macro"], 4), "AUC mel": round(m["AUC mel"], 4),
                           "Exactitude équilibrée": round(m["Exactitude équilibrée"], 4)})
    t = pd.DataFrame(lignes)
    t.to_csv(C.TAB_DIR / "12_architecture_test_apres_choix.csv", index=False, encoding="utf-8")
    print("Test (après le choix, pour information) :\n" + t.to_string(index=False))
    return t


# ---------------------------------------------------------------- 3. images hors sujet
def _ouvrir(chemin: Path) -> Image.Image:
    with Image.open(chemin) as im:
        im.load()
        return im.convert("RGB")


def caracteristiques(moteur: Moteur, images, etages: tuple[int, ...], lot: int = 32) -> list[np.ndarray]:
    """images : chemins ou images PIL. Chargement parallèle, calcul par le moteur (fil unique) ;
    renvoie une matrice (N, C_e) par étape du réseau."""
    par_etage: list[list[np.ndarray]] = [[] for _ in etages]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i in range(0, len(images), lot):
            bloc = images[i:i + lot]
            ims = list(ex.map(lambda x: _ouvrir(x) if isinstance(x, (str, Path)) else x.convert("RGB"), bloc))
            for liste, f in zip(par_etage, moteur.caracteristiques_lot(ims, etages)):
                liste.append(f)
    return [np.concatenate(x).astype(np.float64) for x in par_etage]


def score_mahalanobis(f: np.ndarray, mu: np.ndarray, prec: np.ndarray) -> np.ndarray:
    d = f[:, None, :] - mu[None]
    return np.einsum("nkd,de,nke->nk", d, prec, d).min(1)


def images_hors_sujet() -> dict[str, list]:
    """Jeux d'images manifestement non dermoscopiques (aucune ne sert à fixer le seuil)."""
    jeux: dict[str, list] = {}
    web = sorted(p for p in Path("C:/Windows/Web").rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if web:
        jeux["fonds d'écran Windows"] = web
    vus, interface = set(), []
    for p in sorted(Path("C:/Windows/SystemApps").rglob("*.jpg")):
        if p.name not in vus and p.stat().st_size > 20_000:
            vus.add(p.name)
            interface.append(p)
    if interface:
        jeux["illustrations de Windows"] = interface
    captures = sorted((APP_DIR / "docs" / "captures").glob("*.png"))
    if captures:
        jeux["captures d'écran de l'application"] = captures
    import matplotlib
    import skimage.data as sd
    nat = sorted((Path(matplotlib.get_data_path()) / "sample_data").glob("*.[jp][pn]g"))
    for nom in ("astronaut", "brick", "camera", "chelsea", "clock", "coffee", "coins", "colorwheel", "grass",
                "gravel", "horse", "hubble_deep_field", "immunohistochemistry", "logo", "moon", "page", "retina",
                "rocket", "text", "microaneurysms"):
        try:
            a = getattr(sd, nom)()
        except Exception:               # image non embarquée (téléchargement requis) : ignorée
            continue
        a = np.asarray(a)
        if a.dtype == bool:
            a = a.astype(np.uint8) * 255
        if a.dtype != np.uint8:
            a = (255 * (a - a.min()) / max(np.ptp(a), 1e-9)).astype(np.uint8)
        if a.ndim == 2:
            a = np.stack([a] * 3, -1)
        nat.append(Image.fromarray(a[..., :3]))
    jeux["photos et images scientifiques (scikit-image, matplotlib)"] = nat
    rng = np.random.default_rng(0)
    synth = []
    for i in range(10):                                   # documents
        im = Image.new("RGB", (800, 1000), "white")
        d = ImageDraw.Draw(im)
        for j in range(25):
            d.rectangle([60, 80 + 34 * j, 60 + int(rng.integers(200, 680)), 94 + 34 * j], fill=(25, 25, 25))
        synth.append(im)
    for i in range(10):                                   # aplats de couleur
        synth.append(Image.new("RGB", (600, 450), tuple(int(v) for v in rng.integers(0, 256, 3))))
    for i in range(10):                                   # bruit
        synth.append(Image.fromarray(rng.integers(0, 256, (450, 600, 3), dtype=np.uint8)))
    for i in range(5):                                    # dégradés
        g = np.linspace(0, 255, 600, dtype=np.float64)[None, :, None] * rng.uniform(0.3, 1, 3)[None, None]
        synth.append(Image.fromarray(np.repeat(g, 450, 0).astype(np.uint8)))
    jeux["images synthétiques (documents, aplats, bruit, dégradés)"] = synth
    return jeux


def detecteur_hors_sujet(moteur: Moteur, df: pd.DataFrame, out: Path) -> dict:
    """Deux variantes, seuil fixé dans les deux cas au 99,5e centile de la VALIDATION (images dermoscopiques) :
    - « dernière étape » : Mahalanobis sur les caractéristiques finales du réseau ;
    - « toutes les étapes » (Lee et al. 2018) : Mahalanobis à chaque étape, log-distances centrées-réduites
      sur la validation, score = maximum.
    Les images hors sujet sont coupées en deux moitiés : « développement » (choix de la variante) et
    « évaluation » (chiffres rapportés), pour que le choix ne gonfle pas les résultats annoncés."""
    net = moteur.reseaux["complet"][0]
    etages = tuple(range(len(net.features)))
    tr, va, te = (df[df.split == s] for s in ("train", "val", "test"))
    print(f"Caractéristiques ({len(etages)} étapes) : entraînement {len(tr)}, validation {len(va)}, test {len(te)}…")
    f_tr = caracteristiques(moteur, list(tr.path), etages)
    y_tr = tr.y.to_numpy()
    gauss = []
    for f in f_tr:
        mu = np.stack([f[y_tr == k].mean(0) for k in range(C.N_CLASSES)])
        gauss.append((mu, LedoitWolf(assume_centered=True).fit(f - mu[y_tr]).precision_))
    del f_tr

    def scores_bruts(f_etages):                     # (N, nombre d'étapes)
        return np.stack([score_mahalanobis(f, mu, prec) for f, (mu, prec) in zip(f_etages, gauss)], 1)

    b_va, b_te = scores_bruts(caracteristiques(moteur, list(va.path), etages)), \
        scores_bruts(caracteristiques(moteur, list(te.path), etages))
    log_va = np.log(b_va)
    m, s = log_va.mean(0), log_va.std(0)
    variantes = {"derniere": lambda b: b[:, -1], "toutes": lambda b: ((np.log(b) - m) / s).max(1)}
    seuils = {v: float(np.percentile(f(b_va), CENTILE_SEUIL)) for v, f in variantes.items()}

    lignes, ood = [], {}
    for nom, ims in images_hors_sujet().items():
        ood[nom] = scores_bruts(caracteristiques(moteur, ims, etages))
    for v, f in variantes.items():
        lignes.append({"variante": v, "jeu": "validation (fixe le seuil)", "moitie": "", "n": len(va),
                       "rejet": float((f(b_va) > seuils[v]).mean())})
        lignes.append({"variante": v, "jeu": "test HAM10000 (dermoscopie)", "moitie": "", "n": len(te),
                       "rejet": float((f(b_te) > seuils[v]).mean())})
        for nom, b in ood.items():
            for moitie, sel in (("développement", slice(0, None, 2)), ("évaluation", slice(1, None, 2))):
                lignes.append({"variante": v, "jeu": nom, "moitie": moitie, "n": len(b[sel]),
                               "rejet": float((f(b[sel]) > seuils[v]).mean())})
    t = pd.DataFrame(lignes)
    t["rejet"] = t.rejet.round(4)
    t.to_csv(C.TAB_DIR / "12_hors_sujet_evaluation.csv", index=False, encoding="utf-8")

    def rejet_global(v, moitie):
        sel = slice(0, None, 2) if moitie == "développement" else slice(1, None, 2)
        b = np.concatenate([x[sel] for x in ood.values()])
        return float((variantes[v](b) > seuils[v]).mean()), len(b)

    dev = {v: rejet_global(v, "développement")[0] for v in variantes}
    choix = "toutes" if dev["toutes"] > dev["derniere"] else "derniere"
    print(t.to_string(index=False))
    print(f"Rejet des images hors sujet (moitié développement) : {dev} → variante retenue : {choix}")
    r_eval, n_eval = rejet_global(choix, "évaluation")
    f = variantes[choix]
    evaluation = {
        "variante": choix, "rejet_validation": round(float((f(b_va) > seuils[choix]).mean()), 4),
        "rejet_test": round(float((f(b_te) > seuils[choix]).mean()), 4),
        "rejet_hors_sujet": round(r_eval, 4), "n_hors_sujet": n_eval,
        "rejet_hors_sujet_autre_variante": round(rejet_global("derniere" if choix == "toutes" else "toutes",
                                                              "évaluation")[0], 4),
        "par_source": {nom: {"n": int(len(b[1::2])), "rejet": round(float((f(b[1::2]) > seuils[choix]).mean()), 4)}
                       for nom, b in ood.items()}}

    fichier = out / "hors_sujet.npz"
    if choix == "toutes":
        np.savez_compressed(fichier, **{f"moyennes_{e}": g[0].astype(np.float32) for e, g in zip(etages, gauss)},
                            **{f"precision_{e}": g[1].astype(np.float32) for e, g in zip(etages, gauss)})
    else:
        np.savez_compressed(fichier, moyennes=gauss[-1][0].astype(np.float32), precision=gauss[-1][1].astype(np.float32))
    _figure_scores(f(b_te), np.concatenate([f(b[1::2]) for b in ood.values()]), seuils[choix], choix)
    print(f"Hors sujet : {json.dumps(evaluation, ensure_ascii=False)}")
    detecteur_hors_sujet.controle = (list(va.path[:6]), f(b_va)[:6])     # pour la vérification finale
    info = {"fichier": fichier.name, "sha256": sha256(fichier), "seuil": round(seuils[choix], 4), "profil": "complet",
            "methode": ("distance de Mahalanobis minimale aux classes (covariance partagée Ledoit-Wolf) à chaque étape "
                        "du réseau, log-distances centrées-réduites sur la validation, maximum sur les étapes"
                        if choix == "toutes" else "distance de Mahalanobis minimale aux classes (covariance partagée "
                        "Ledoit-Wolf), caractéristiques finales du réseau")
            + f" ; seuil = {CENTILE_SEUIL}e centile de la validation", "evaluation": evaluation}
    if choix == "toutes":
        info["etages"] = list(etages)
        info["normalisation"] = {"moyenne": [round(float(x), 6) for x in m], "ecart_type": [round(float(x), 6) for x in s]}
    return info


def _figure_scores(s_te, s_hs, seuil, variante) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    log = variante == "derniere"
    tous = np.concatenate([s_te, s_hs])
    bins = np.logspace(np.log10(max(tous.min(), 1e-3)), np.log10(tous.max()), 60) if log else np.linspace(tous.min(), tous.max(), 60)
    ax.hist(s_te, bins=bins, alpha=0.6, label="test HAM10000 (dermoscopie)", color="#0e6a64")
    ax.hist(s_hs, bins=bins, alpha=0.6, label="images hors sujet (moitié évaluation)", color="#b54708")
    ax.axvline(seuil, color="#b42318", lw=1.5, label=f"seuil ({CENTILE_SEUIL}e centile de la validation)")
    if log:
        ax.set_xscale("log")
    ax.set_xlabel("score d'atypie" + (" (Mahalanobis, échelle log)" if log else " (maximum des étapes, écarts-types)"))
    ax.set_ylabel("nombre d'images")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(C.FIG_DIR / "12_hors_sujet_scores.png")
    plt.close(fig)


# ---------------------------------------------------------------- 4. textes de la fiche
def sensibilite_par_age(exp: str, cle: str, df: pd.DataFrame, seuil: float) -> tuple[float, float, int, int]:
    pt, yt, idx = ensemble(exp, cle, df)["test"]
    age = df.age.to_numpy()[idx]
    mel = yt == C.MEL
    pred = decide(pt, seuil) == C.MEL
    jeune, age_ok = mel & (age < 50), mel & (age >= 50)
    return float(pred[jeune].mean()), float(pred[age_ok].mean()), int(jeune.sum()), int(age_ok.sum())


def textes(arch: str, taille: int, sens: tuple, n_mel_val: int, hs: dict) -> dict:
    sj, sa, nj, na = sens
    reseau = {"efficientnet_b0": "EfficientNet-B0", "efficientnet_b2": "EfficientNet-B2"}[arch]
    ev = hs["evaluation"]
    pfr = lambda x: f"{100 * x:.0f} %"                   # noqa: E731
    pen = lambda x: f"{100 * x:.0f}%"                    # noqa: E731
    fr = {
        "description": f"Classification de lésions dermoscopiques (7 classes) par {reseau} ({taille} px) guidé par "
                       "le contexte patient (FiLM), décision sensible au coût, abstention conforme (Mondrian) et "
                       "refus des images hors sujet. Moyenne de 3 graines.",
        "usage_prevu": "Aide à la décision pour professionnels de santé, sur images dermoscopiques. Ne remplace pas "
                       "l'examen clinique ni l'histologie.",
        "statut": "DÉMONSTRATION — usage non commercial — pas un dispositif médical",
        "consequence": "Ce modèle ne peut pas être vendu ni utilisé commercialement. Pour un usage commercial, "
                       "réentraîner sur des données sous licence adaptée et obtenir le marquage réglementaire.",
        "centres": "Vienne (Autriche), Queensland (Australie)",
        "licence": "CC BY-NC 4.0 (Attribution - Pas d'utilisation commerciale)",
        "decision_regle": "mélanome si p(mel) ≥ seuil, sinon la classe non-mélanome la plus probable",
        "abstention_methode": "LAC conditionnel par classe (Mondrian)",
        "abstention_regle": "traité si l'ensemble conforme est un singleton égal à la décision au coût",
        "calibre_complet": "contexte complet", "calibre_sans": "contexte entièrement manquant",
        "limites": [
            "Entraîné sur deux centres, peaux majoritairement claires : performances inconnues ailleurs.",
            f"Sensibilité mélanome (test, R = 10) : {pfr(sj)} chez les moins de 50 ans ({nj} mélanomes) contre "
            f"{pfr(sa)} à partir de 50 ans ({na} mélanomes).",
            f"Seuils estimés sur un petit jeu de validation ({n_mel_val} images de mélanome).",
            f"Images hors sujet : {pfr(ev['rejet_hors_sujet'])} refusées sur {ev['n_hors_sujet']} images très "
            "différentes ; une photo de peau prise sans dermoscope n'a pas pu être testée et peut passer le contrôle.",
            "Critères ABCD automatiques : indicateurs au pouvoir discriminant modeste (AUC 0,66 à 0,73 entre "
            "mélanome et nævus sur le test).",
        ],
    }
    en = {
        "description": f"Classification of dermoscopic lesions (7 classes) by {reseau} ({taille} px) guided by the "
                       "patient context (FiLM), cost-sensitive decision, conformal abstention (Mondrian) and refusal "
                       "of out-of-scope images. Average of 3 seeds.",
        "usage_prevu": "Decision support for healthcare professionals, on dermoscopic images. Does not replace "
                       "clinical examination or histology.",
        "statut": "DEMONSTRATION — non-commercial use — not a medical device",
        "consequence": "This model cannot be sold or used commercially. For commercial use, retrain on suitably "
                       "licensed data and obtain regulatory approval.",
        "centres": "Vienna (Austria), Queensland (Australia)",
        "licence": "CC BY-NC 4.0 (Attribution - NonCommercial)",
        "decision_regle": "melanoma if p(mel) ≥ threshold, otherwise the most probable non-melanoma class",
        "abstention_methode": "Class-conditional LAC (Mondrian)",
        "abstention_regle": "handled if the conformal set is a singleton equal to the cost-based decision",
        "calibre_complet": "complete context", "calibre_sans": "entirely missing context",
        "limites": [
            "Trained on two centres, mostly fair skin: performance unknown elsewhere.",
            f"Melanoma sensitivity (test, R = 10): {pen(sj)} under 50 years ({nj} melanomas) versus {pen(sa)} "
            f"from 50 years ({na} melanomas).",
            f"Thresholds estimated on a small validation set ({n_mel_val} melanoma images).",
            f"Out-of-scope images: {pen(ev['rejet_hors_sujet'])} refused out of {ev['n_hors_sujet']} very different "
            "images; a skin photo taken without a dermatoscope could not be tested and may pass the check.",
            "Automatic ABCD criteria: indicators with modest discriminative power (AUC 0.66 to 0.73 between "
            "melanoma and nevus on the test set).",
        ],
    }
    par = lambda x: f"{100 * x:.0f}%"                    # noqa: E731
    ar = {
        "description": f"تصنيف آفات المنظار الجلدي (7 فئات) بواسطة {reseau} ({taille} بكسل) موجَّه بسياق المريض "
                       "(FiLM)، مع قرار حساس للتكلفة، وامتناع مطابِق (موندريان)، ورفض الصور خارج النطاق. متوسط 3 نماذج.",
        "usage_prevu": "أداة مساعدة على اتخاذ القرار لمهنيي الصحة، على صور المنظار الجلدي. لا تُغني عن الفحص "
                       "السريري ولا عن الفحص النسيجي.",
        "statut": "عرض توضيحي — استخدام غير تجاري — ليس جهازًا طبيًا",
        "consequence": "لا يجوز بيع هذا النموذج ولا استخدامه تجاريًا. للاستخدام التجاري يجب إعادة تدريبه على بيانات "
                       "بترخيص مناسب والحصول على الاعتماد التنظيمي.",
        "centres": "فيينا (النمسا)، كوينزلاند (أستراليا)",
        "licence": "CC BY-NC 4.0 (نسب المصنَّف - غير تجاري)",
        "decision_regle": "ورم ميلانيني إذا كان احتماله ≥ العتبة، وإلا فالفئة غير الميلانينية الأكثر احتمالًا",
        "abstention_methode": "LAC مشروط بالفئة (موندريان)",
        "abstention_regle": "تُعالَج الحالة إذا كانت المجموعة المطابِقة عنصرًا واحدًا مطابقًا لقرار التكلفة",
        "calibre_complet": "سياق كامل", "calibre_sans": "سياق مفقود كليًا",
        "limites": [
            "دُرِّب على بيانات مركزين، وأغلب البشرات فاتحة: الأداء غير معروف في غيرهما.",
            f"حساسية الورم الميلانيني (الاختبار، R = 10): {par(sj)} لدى من هم دون 50 سنة ({nj} ورمًا) مقابل "
            f"{par(sa)} ابتداءً من 50 سنة ({na} ورمًا).",
            f"قُدِّرت العتبات على مجموعة تحقق صغيرة ({n_mel_val} صورة ورم ميلانيني).",
            f"الصور خارج النطاق: رُفض {par(ev['rejet_hors_sujet'])} من أصل {ev['n_hors_sujet']} صورة مختلفة تمامًا؛ "
            "لم يكن ممكنًا اختبار صورة جلد ملتقطة دون منظار، وقد تجتاز الفحص.",
            "معايير ABCD الآلية: مؤشرات ذات قدرة تمييز محدودة (AUC من 0,66 إلى 0,73 بين الورم الميلانيني والوحمة "
            "على مجموعة الاختبار).",
        ],
    }
    return {"fr": fr, "en": en, "ar": ar}


# ---------------------------------------------------------------- référence de non-régression
def ecrire_reference(df: pd.DataFrame, exps: dict, n_par_classe: int = 4) -> None:
    """Probabilités attendues (ensemble des graines du projet) pour des images du test : le moteur de
    l'application doit les reproduire (contexte complet → profil complet, sinon profil sans_contexte
    avec le contexte partiel réel, clé « p »)."""
    attendus = {p: ensemble(exps[p][0], "p", df)["test"] for p in PROFILS}
    test = df.iloc[attendus["complet"][2]].reset_index(drop=True)
    complet = (test.age.notna() & (test.sex != "unknown") & (test.localization != "unknown")).to_numpy()
    rng = np.random.default_rng(0)
    cas = []
    for c in C.CLASSES:
        cand = np.flatnonzero(test.dx.to_numpy() == c)
        choix = list(rng.choice(cand, min(n_par_classe, len(cand)), replace=False))
        incomplets = np.flatnonzero((test.dx.to_numpy() == c) & ~complet)
        if len(incomplets) and not any(i in incomplets for i in choix):
            choix[-1] = int(incomplets[0])
        for i in choix:
            r = test.iloc[i]
            prof = "complet" if complet[i] else "sans_contexte"
            cas.append({"image_id": r.image_id, "fichier": f"{r.path.parent.name}/{r.path.name}",
                        "age": None if np.isnan(r.age) else float(r.age), "sexe": r.sex,
                        "localisation": r.localization, "dx": r.dx, "profil": prof,
                        "probabilites": [round(float(v), 6) for v in attendus[prof][0][i]]})
    ref = APP_DIR / "tests" / "reference_ham10000.json"
    ref.write_text(json.dumps({"description": f"Probabilités attendues (projet/resultats/predictions, {BUNDLE}), "
                                              "images HAM10000 du jeu de test", "cas": cas},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Référence de non-régression : {len(cas)} cas → {ref}")


# ---------------------------------------------------------------- assemblage
def main() -> None:
    df = get_split()
    arch, _ = choisir_architecture(df)
    mesures_test_apres_choix(df)
    cand = CANDIDATS[arch]
    taille = cand["taille"]
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    out = APP_DIR / "modeles" / BUNDLE
    if out.exists():
        shutil.rmtree(out)
    (out / "poids").mkdir(parents=True)

    profils = {}
    for nom in PROFILS:
        exp, cle = cand[nom]
        calib, metrics = profile_card(exp, cle, df)
        meta = json.loads((C.PRED_DIR / f"{exp}_s0.json").read_text(encoding="utf-8"))
        poids = []
        for s in C.TRAIN_SEEDS:
            dst = out / "poids" / f"{exp}_s{s}.pt"
            shutil.copy2(C.CKPT_DIR / f"{exp}_s{s}.pt", dst)
            poids.append({"fichier": f"poids/{dst.name}", "sha256": sha256(dst)})
        profils[nom] = {"experience": exp, "architecture": arch, "fusion": meta["fusion"],
                        "film": meta.get("film", "final"), "n_clin": enc.n_features, "poids": poids,
                        "calibre_sur": "contexte complet" if cle == "p" else "contexte entièrement manquant",
                        **calib, "metriques_test": metrics}
        print(f"{nom}: seuils {calib['thresholds']} | q {np.round(calib['conformal_q'], 3).tolist()}")

    manifest = {
        "nom": BUNDLE, "version": "2.0.0", "date": date.today().isoformat(),
        "description": "", "statut": "DÉMONSTRATION — usage non commercial — pas un dispositif médical",
        "donnees_entrainement": {
            "jeu": "HAM10000 (Tschandl et al., Sci Data 2018, doi:10.1038/sdata.2018.161)",
            "licence": "CC BY-NC 4.0 (Attribution - Pas d'utilisation commerciale)", "consequence": "",
            "centres": "Vienne (Autriche), Queensland (Australie)"},
        "usage_prevu": "", "classes": C.CLASSES, "noms_classes": C.CLASS_NAMES_FR,
        "classes_malignes": [C.CLASSES[i] for i in MALIGNANT], "indice_melanome": C.MEL,
        "pretraitement": {"taille": taille, "redimensionnement": "LANCZOS, sans conserver le ratio",
                          "moyenne": C.IMAGENET_MEAN, "ecart_type": C.IMAGENET_STD,
                          "tta": ["identite", "flip_h", "flip_v", "flip_hv"]},
        "encodeur_clinique": {"age_mediane": enc.age_median, "age_moyenne": enc.age_mean,
                              "age_ecart_type": enc.age_std, "sexes": enc.sex_cats,
                              "localisations": enc.loc_cats, "variables": enc.feature_names},
        "decision": {"rapports_cout": C.COST_RATIOS, "rapport_defaut": C.DEFAULT_COST_RATIO, "regle": ""},
        "abstention": {"methode": "", "alpha": C.ALPHA, "regle": ""},
        "profils": profils, "limites": [],
    }
    ecrire = lambda: (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),  # noqa: E731
                                                       encoding="utf-8")
    ecrire()

    # Détecteur hors sujet, calculé par le moteur de l'application chargé sur ce paquet
    moteur = Moteur(out, device="cuda")
    hs = detecteur_hors_sujet(moteur, df, out)
    manifest["hors_sujet"] = hs

    # Textes de la fiche (français dans les champs d'origine, traductions dans « i18n »)
    seuil_r10 = profils["complet"]["thresholds"][str(C.DEFAULT_COST_RATIO)]
    sens = sensibilite_par_age(*cand["complet"], df, seuil_r10)
    n_mel_val = int(((df.split == "val") & (df.y == C.MEL)).sum())
    tx = textes(arch, taille, sens, n_mel_val, hs)
    fr = tx["fr"]
    manifest.update(description=fr["description"], usage_prevu=fr["usage_prevu"], statut=fr["statut"],
                    limites=fr["limites"], statut_i18n={lg: tx[lg]["statut"] for lg in tx})
    manifest["donnees_entrainement"]["consequence"] = fr["consequence"]
    manifest["decision"]["regle"] = fr["decision_regle"]
    manifest["abstention"].update(methode=fr["abstention_methode"], regle=fr["abstention_regle"])
    manifest["i18n"] = {lg: {k: v for k, v in tx[lg].items() if k not in ("calibre_complet", "calibre_sans")}
                        for lg in ("en", "ar")}
    for lg in ("en", "ar"):                              # « calibré sur », par profil
        manifest["i18n"][lg]["calibre_sur_complet"] = tx[lg]["calibre_complet"]
        manifest["i18n"][lg]["calibre_sur_sans_contexte"] = tx[lg]["calibre_sans"]
    ecrire()

    # Vérification : le moteur relu (empreintes vérifiées) reproduit les scores hors sujet du script
    m2 = Moteur(out, device="cuda", verifier_empreintes=True)
    chemins, attendus = detecteur_hors_sujet.controle
    for chemin, attendu in zip(chemins, attendus):
        obtenu = m2._score_hors_sujet(m2.pretraiter(_ouvrir(chemin)))
        assert abs(obtenu - attendu) <= 5e-3 * max(1.0, abs(attendu)), (chemin, obtenu, attendu)
    print("Moteur relu : scores hors sujet reproduits.")
    ecrire_reference(df, cand)
    print("Paquet de modèle écrit :", out)


if __name__ == "__main__":
    main()
