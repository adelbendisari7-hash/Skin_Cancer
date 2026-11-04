"""Exporte le modèle déployé sous forme de « paquet de modèle » autonome pour l'application.

Modèle déployé = moyenne des 3 graines :
- profil « complet »        : M5 (FiLM + coût), utilisé quand l'âge, le sexe et la localisation sont connus ;
- profil « sans_contexte »  : M5 + dropout clinique, utilisé dès qu'une donnée clinique manque
                              (M5 s'effondre sans contexte : sensibilité mélanome 0,19).

La moyenne des graines est un nouveau modèle : on la RECALIBRE (seuils de coût sur la validation,
seuils conformes Mondrian sur la calibration) puis on la mesure UNE fois sur le test pour la fiche.
Le profil « sans_contexte » est calibré sur des prédictions SANS aucun contexte (cas le plus défavorable).

Usage : python -m src.export
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date

import numpy as np

from . import config as C
from .analyses import MALIGNANT
from .conformal import Conformal, abstain_rule, set_stats
from .data import ClinicalEncoder, get_split
from .decision import decide, tune_mel_threshold
from .metrics import classification_metrics

APP_DIR = C.PROJECT_DIR / "application"
BUNDLE_NAME = "ham10000-m5-v1"
PROFILES = {"complet": ("M5", "p"), "sans_contexte": ("M5_dropClin", "p_noclin")}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensemble(exp: str, key: str, df) -> dict:
    """Probabilités moyennes des 3 graines, séparées par jeu."""
    ps, idx = [], None
    for s in C.TRAIN_SEEDS:
        d = np.load(C.PRED_DIR / f"{exp}_s{s}.npz")
        ps.append(d[key])
        idx = d["idx"] if idx is None else idx
        assert (d["idx"] == idx).all()
    p = np.mean(ps, axis=0)
    split = df.split.to_numpy()[idx]
    y = df.y.to_numpy()[idx]
    return {s: (p[split == s], y[split == s], idx[split == s]) for s in ["val", "calib", "test"]}


def profile_card(exp: str, key: str, df) -> tuple[dict, dict]:
    e = ensemble(exp, key, df)
    (pv, yv, _), (pc, yc, _), (pt, yt, _) = e["val"], e["calib"], e["test"]
    thresholds = {str(R): tune_mel_threshold(pv, yv, R)[0] for R in C.COST_RATIOS}
    cf = Conformal("mondrian", C.ALPHA).fit(pc, yc)
    calib = {"thresholds": thresholds, "conformal_q": [float(q) for q in cf.q]}
    return calib, metriques_fiche(pt, yt, thresholds, cf)


def metriques_fiche(pt: np.ndarray, yt: np.ndarray, thresholds: dict, cf: Conformal) -> dict:
    """Mesures d'un jeu de test pour la fiche du modèle (calculées une seule fois)."""
    R = C.DEFAULT_COST_RATIO
    pred = decide(pt, thresholds[str(R)])
    sets = cf.sets(pt)
    treated = abstain_rule(sets, pred)
    mel = yt == C.MEL
    malin = np.isin(yt, MALIGNANT)
    referred = np.isin(pred, MALIGNANT) | ~treated
    m_cls = classification_metrics(yt, pt.argmax(1), pt)
    m_cost = classification_metrics(yt, pred, pt)
    metrics = {
        "decision_classique": {k: round(v, 4) for k, v in m_cls.items()},
        f"decision_cout_R{R}": {k: round(v, 4) for k, v in m_cost.items()},
        "abstention": {
            **{k: round(v, 4) for k, v in set_stats(sets, yt).items()},
            "taux_traite": round(float(treated.mean()), 4),
            "melanomes_test": int(mel.sum()),
            "melanomes_manques_en_silence": int((mel & treated & (pred != C.MEL)).sum()),
            "melanomes_renvoyes": int((mel & ~treated).sum()),
            "sensibilite_malin_triage": round(float(referred[malin].mean()), 4),
            "part_cas_renvoyes": round(float(referred.mean()), 4),
        },
        "n_images_test": int(len(yt)),
    }
    return metrics


def write_reference(df, n_per_class: int = 4) -> None:
    """Jeu de référence pour le test de non-régression de l'application (images du test).

    Contexte complet → probabilités attendues = moyenne des graines de M5 ;
    contexte incomplet → moyenne des graines de M5_dropClin (avec le contexte partiel réel).
    """
    exps = {"complet": ensemble("M5", "p", df)["test"], "sans_contexte": ensemble("M5_dropClin", "p", df)["test"]}
    test = df.iloc[exps["complet"][2]].reset_index(drop=True)
    complet = test.age.notna() & (test.sex != "unknown") & (test.localization != "unknown")
    rng = np.random.default_rng(0)
    rows = []
    for c in C.CLASSES:
        cand = np.flatnonzero(test.dx.to_numpy() == c)
        pick = list(rng.choice(cand, min(n_per_class, len(cand)), replace=False))
        incomplets = np.flatnonzero((test.dx.to_numpy() == c) & ~complet.to_numpy())
        if len(incomplets) and not any(i in incomplets for i in pick):
            pick[-1] = int(incomplets[0])          # au moins un contexte incomplet quand il en existe
        for i in pick:
            r = test.iloc[i]
            prof = "complet" if complet.iloc[i] else "sans_contexte"
            rows.append({"image_id": r.image_id, "fichier": f"{r.path.parent.name}/{r.path.name}",
                         "age": None if np.isnan(r.age) else float(r.age), "sexe": r.sex,
                         "localisation": r.localization, "dx": r.dx, "profil": prof,
                         "probabilites": [round(float(v), 6) for v in exps[prof][0][i]]})
    ref = C.PROJECT_DIR / "application" / "tests" / "reference_ham10000.json"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(json.dumps({"description": "Probabilités attendues (projet/resultats/predictions), "
                                              "images HAM10000 du jeu de test", "cas": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Référence de non-régression : {len(rows)} cas ({sum(r['profil'] == 'sans_contexte' for r in rows)} "
          f"à contexte incomplet) → {ref}")


def main() -> None:
    df = get_split()
    write_reference(df)
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    out = APP_DIR / "modeles" / BUNDLE_NAME
    (out / "poids").mkdir(parents=True, exist_ok=True)

    profiles = {}
    for name, (exp, key) in PROFILES.items():
        calib, metrics = profile_card(exp, key, df)
        meta = json.loads((C.PRED_DIR / f"{exp}_s0.json").read_text(encoding="utf-8"))
        weights = []
        for s in C.TRAIN_SEEDS:
            dst = out / "poids" / f"{exp}_s{s}.pt"
            shutil.copy2(C.CKPT_DIR / f"{exp}_s{s}.pt", dst)
            weights.append({"fichier": f"poids/{dst.name}", "sha256": sha256(dst)})
        profiles[name] = {
            "experience": exp, "architecture": "efficientnet_b0", "fusion": meta["fusion"],
            "film": meta.get("film", "final"), "n_clin": enc.n_features, "poids": weights,
            "calibre_sur": "contexte complet" if key == "p" else "contexte entièrement manquant",
            **calib, "metriques_test": metrics,
        }
        print(f"{name}: seuils {calib['thresholds']} | q {np.round(calib['conformal_q'], 3).tolist()}")
        print(f"   test : {json.dumps(metrics['abstention'], ensure_ascii=False)}")

    manifest = {
        "nom": BUNDLE_NAME, "version": "1.0.0", "date": date.today().isoformat(),
        "description": "Classification de lésions dermoscopiques (7 classes) guidée par le contexte patient "
                       "(FiLM), décision sensible au coût et abstention conforme (Mondrian). Moyenne de 3 graines.",
        "statut": "DÉMONSTRATION — usage non commercial — pas un dispositif médical",
        "donnees_entrainement": {
            "jeu": "HAM10000 (Tschandl et al., Sci Data 2018, doi:10.1038/sdata.2018.161)",
            "licence": "CC BY-NC 4.0 (Attribution - Pas d'utilisation commerciale)",
            "consequence": "Ce modèle ne peut pas être vendu ni utilisé commercialement. Pour un usage "
                           "commercial, réentraîner sur des données sous licence adaptée.",
            "centres": "Vienne (Autriche), Queensland (Australie)",
        },
        "usage_prevu": "Aide à la décision pour professionnels de santé, sur images dermoscopiques. "
                       "Ne remplace pas l'examen clinique ni l'histologie.",
        "classes": C.CLASSES, "noms_classes": C.CLASS_NAMES_FR,
        "classes_malignes": [C.CLASSES[i] for i in MALIGNANT], "indice_melanome": C.MEL,
        "pretraitement": {"taille": C.IMG_SIZE, "redimensionnement": "LANCZOS, sans conserver le ratio",
                          "moyenne": C.IMAGENET_MEAN, "ecart_type": C.IMAGENET_STD,
                          "tta": ["identite", "flip_h", "flip_v", "flip_hv"]},
        "encodeur_clinique": {"age_mediane": enc.age_median, "age_moyenne": enc.age_mean,
                              "age_ecart_type": enc.age_std, "sexes": enc.sex_cats,
                              "localisations": enc.loc_cats, "variables": enc.feature_names},
        "decision": {"rapports_cout": C.COST_RATIOS, "rapport_defaut": C.DEFAULT_COST_RATIO,
                     "regle": "mélanome si p(mel) ≥ seuil, sinon la classe non-mélanome la plus probable"},
        "abstention": {"methode": "LAC conditionnel par classe (Mondrian)", "alpha": C.ALPHA,
                       "regle": "traité si l'ensemble conforme est un singleton égal à la décision au coût"},
        "profils": profiles,
        "limites": [
            "Entraîné sur deux centres, peaux majoritairement claires : performances inconnues ailleurs.",
            "Sensibilité mélanome plus faible chez les moins de 50 ans (forte dépendance à l'âge).",
            "Une image qui n'est pas une dermoscopie recevra quand même une réponse.",
            "Seuils estimés sur un petit jeu de validation (61 lésions de mélanome).",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Paquet de modèle écrit :", out)


if __name__ == "__main__":
    main()
