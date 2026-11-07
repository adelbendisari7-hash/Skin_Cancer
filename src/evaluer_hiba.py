"""Validation externe de la v2 et de la v3 sur HIBA (Buenos Aires), selon application/docs/plan_hiba.md.

Les deux paquets sont exécutés par le moteur de l'application (prétraitement, profil, seuils et ensembles conformes
d'origine, détecteur hors sujet) : aucun réglage sur HIBA. Deux contextes : réel (âge, sexe, localisation) et aucun.
Mesure unique ; intervalles de confiance par bootstrap sur les patients.

Usage : python -m src.evaluer_hiba
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.metrics import roc_auc_score

from . import config as C
from .analyses import MALIGNANT
from .donnees_v3 import CLASSES_BCN, ZONES_BCN
from .metrics import classification_metrics, lesion_bootstrap_indices

sys.path.insert(0, str(C.PROJECT_DIR / "application" / "backend"))
from dermia.engine import Contexte, Moteur  # noqa: E402

HIBA_DIR = Path(os.environ.get("HIBA_DIR", C.PROJECT_DIR.parent / "HIBA"))
PAQUETS = {"v2": "ham10000-m5-v2", "v3": "ham10000-bcn20000-m5-v3"}
LOC_V2 = {"Trunk": "trunk", "Upper extremity": "upper extremity", "Lower extremity": "lower extremity"}
SPECIAL_V2 = {"acral palms or soles": "acral", "oral or genital": "genital"}


def charger_hiba() -> pd.DataFrame:
    m = pd.read_csv(next(HIBA_DIR.glob("*metadata*.csv")), low_memory=False)
    m = m[m.image_type == "dermoscopic"].copy()
    dx = m.diagnosis_3.map({**CLASSES_BCN, "Lichen planus like keratosis": "bkl"})
    m["dx"] = dx.mask(m.diagnosis_2.eq("Benign soft tissue proliferations - Vascular"), "vasc")
    assert m.dx.notna().all(), m[m.dx.isna()].diagnosis_3.value_counts()
    m["y"] = m.dx.map({c: i for i, c in enumerate(C.CLASSES)})
    special = m.anatom_site_special.notna()
    m["loc_v3"] = m.anatom_site_1.map(ZONES_BCN).mask(special, "autre").fillna("unknown")
    m["loc_v2"] = m.anatom_site_1.map(LOC_V2).mask(special, m.anatom_site_special.map(SPECIAL_V2)).fillna("unknown")
    m["sex"] = m.sex.fillna("unknown")
    m["path"] = m.isic_id.map(lambda i: HIBA_DIR / "ISIC-images" / f"{i}.jpg")
    m["carcinome_epidermoide"] = m.diagnosis_3.eq("Squamous cell carcinoma, NOS")
    return m.reset_index(drop=True)


def analyser(df: pd.DataFrame) -> pd.DataFrame:
    lignes = []
    for version, paquet in PAQUETS.items():
        moteur = Moteur(C.PROJECT_DIR / "application" / "modeles" / paquet, device="cuda")
        moteur.prechauffer()
        for i, r in df.iterrows():
            with Image.open(r.path) as im:
                im.load()
                age = None if np.isnan(r.age_approx) else float(r.age_approx)
                for contexte, ctx in (("reel", Contexte(age, r.sex, r[f"loc_{version}"])), ("aucun", Contexte())):
                    res, _ = moteur.analyser(im, ctx)
                    lignes.append({"isic_id": r.isic_id, "version": version, "contexte": contexte, "profil": res.profil,
                                   **{f"p_{c}": res.probabilites[c] for c in C.CLASSES}, "decision": res.decision,
                                   "ensemble": "|".join(res.ensemble_conforme), "traite": res.traite,
                                   "hors_sujet": res.hors_sujet})
            if (i + 1) % 200 == 0:
                print(f"  {version} : {i + 1}/{len(df)}", flush=True)
    return pd.DataFrame(lignes)


def ic(v: list[float]) -> str:
    a = np.array([x for x in v if not np.isnan(x)])
    return f"[{np.percentile(a, 2.5):.3f} ; {np.percentile(a, 97.5):.3f}]"


def mesurer(t: pd.DataFrame) -> dict:
    p = t[[f"p_{c}" for c in C.CLASSES]].to_numpy()
    y = t.y.to_numpy()
    pred = t.decision.map({c: i for i, c in enumerate(C.CLASSES)}).to_numpy()
    traite = t.traite.to_numpy(bool)
    ens = t.ensemble.str.split("|")
    mel, malin = y == C.MEL, np.isin(y, MALIGNANT)
    alerte = pred == C.MEL
    renvoye = np.isin(pred, MALIGNANT) | ~traite
    jeunes = mel & (t.age_approx.to_numpy() < 50)
    m = classification_metrics(y, p.argmax(1), p)
    r = {"images": len(t), "patients": t.patient_id.nunique(), "mélanomes": int(mel.sum()),
         "F1 macro": m["F1 macro"], "Exactitude équilibrée": m["Exactitude équilibrée"], "AUC OvR macro": m["AUC OvR macro"],
         "AUC mel": m["AUC mel"], "Sensibilité mel (R=10)": float(alerte[mel].mean()),
         "Spécificité mel (R=10)": float((~alerte[~mel]).mean()), "VPP alerte mel": float(mel[alerte].mean()),
         "Mélanomes <50 ans": int(jeunes.sum()), "Sensibilité mel <50 ans": float(alerte[jeunes].mean()),
         "Couverture conforme": float(np.mean([C.CLASSES[k] in e for k, e in zip(y, ens)])),
         "Cas traités seuls": float(traite.mean()),
         "Mélanomes classés bénins sans renvoi": int((mel & traite & ~alerte).sum()),
         "Sensibilité malin (triage)": float(renvoye[malin].mean()), "Part des cas renvoyés": float(renvoye.mean()),
         "Images signalées hors sujet": float(t.hors_sujet.mean()),
         "Profil sans contexte utilisé": float((t.profil == "sans_contexte").mean())}
    b = {k: [] for k in ("sens", "spec", "auc", "jeunes", "silence")}
    for i in lesion_bootstrap_indices(t.patient_id.to_numpy()):
        mi, ai = mel[i], alerte[i]
        b["sens"].append(ai[mi].mean()); b["spec"].append((~ai[~mi]).mean())
        b["auc"].append(roc_auc_score(mi, p[i, C.MEL]))
        b["jeunes"].append(ai[jeunes[i]].mean() if jeunes[i].any() else np.nan)
        b["silence"].append(float((mi & traite[i] & ~ai).sum()))
    r.update({"IC95 AUC mel": ic(b["auc"]), "IC95 sensibilité mel": ic(b["sens"]),
              "IC95 spécificité mel": ic(b["spec"]), "IC95 sensibilité mel <50 ans": ic(b["jeunes"]),
              "IC95 mélanomes sans renvoi": ic(b["silence"])})
    return r


def main() -> None:
    df = charger_hiba()
    print(f"HIBA dermoscopie : {len(df)} images, {df.lesion_id.nunique()} lésions, {df.patient_id.nunique()} patients")
    sortie = C.PRED_DIR / "hiba_predictions.csv"
    if sortie.exists():
        pr = pd.read_csv(sortie)
    else:
        pr = analyser(df)
        pr.to_csv(sortie, index=False)
    t = pr.merge(df[["isic_id", "y", "age_approx", "patient_id", "carcinome_epidermoide"]], on="isic_id")
    lignes = []
    for jeu, masque in (("HIBA", slice(None)), ("HIBA sans carcinome épidermoïde", ~t.carcinome_epidermoide)):
        tt = t[masque]
        for contexte in ("reel", "aucun"):
            for version in PAQUETS:
                s = tt[(tt.version == version) & (tt.contexte == contexte)]
                lignes.append({"jeu": jeu, "contexte": contexte, "version": version, **mesurer(s)})
    res = pd.DataFrame(lignes)
    res.to_csv(C.TAB_DIR / "15_hiba_tests.csv", index=False, encoding="utf-8")
    with pd.option_context("display.max_columns", None, "display.width", 250):
        print(res.T.to_string())
    (C.TAB_DIR / "15_hiba_resume.json").write_text(json.dumps(
        {"images": len(df), "lesions": int(df.lesion_id.nunique()), "patients": int(df.patient_id.nunique()),
         "classes": df.dx.value_counts().to_dict()}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
