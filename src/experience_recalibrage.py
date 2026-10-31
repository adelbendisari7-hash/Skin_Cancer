"""Expérience : le recalibrage local restaure-t-il les garanties quand l'appareil change ?

On simule un « autre dermoscope » sur les images du TEST HAM10000 (dominante chaude, gamma, léger flou,
compression JPEG forte), on calcule les probabilités avec le moteur de l'application (paquet v2, profil
« contexte complet »), puis, 20 fois :
- on coupe les lésions du test en deux moitiés (par lésion, jamais une même lésion des deux côtés) ;
- moitié « établissement » : cas validés servant à recalibrer (module de l'application, mêmes garde-fous) ;
- moitié « futurs patients » : on compare les seuils d'origine et les seuils recalibrés.
Témoin : la même procédure sur les images non modifiées (le recalibrage ne doit alors presque rien changer).

Les images de test ne servent à régler aucun modèle du projet : elles jouent ici le rôle des patients d'un
établissement. Usage : python -m src.experience_recalibrage
"""
from __future__ import annotations

import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from . import config as C
from .data import get_split

sys.path.insert(0, str(C.PROJECT_DIR / "application" / "backend"))
from dermia.engine import Contexte, Moteur  # noqa: E402
from dermia.engine import recalibrage as R  # noqa: E402

BUNDLE = C.PROJECT_DIR / "application" / "modeles" / "ham10000-m5-v2"
N_REPETITIONS = 20


def autre_dermoscope(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    a = np.clip(a ** 1.25 * np.array([1.10, 0.98, 0.82]), 0, 1)          # gamma + dominante chaude
    im2 = Image.fromarray((a * 255).round().astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    buf = io.BytesIO()
    im2.save(buf, "JPEG", quality=40)                                      # compression forte
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def probabilites(m: Moteur, df: pd.DataFrame, transformer: bool) -> np.ndarray:
    def charger(chemin):
        with Image.open(chemin) as im:
            im.load()
            return autre_dermoscope(im) if transformer else im.convert("RGB")
    sorties = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        images = ex.map(charger, df.path)
        for (_, r), im in zip(df.iterrows(), images):
            res, _ = m.analyser(im, Contexte(float(r.age), r.sex, r.localization))
            sorties.append([res.probabilites[c] for c in m.classes])
    return np.array(sorties)


def sensibilite_mel(p: np.ndarray, y: np.ndarray, seuil: float, mel: int) -> float:
    est = y == mel
    return float((R.decider(p[est], seuil, mel) == mel).mean()) if est.any() else float("nan")


def comparer(p: np.ndarray, y: np.ndarray, lesions: np.ndarray, m: Moteur, condition: str) -> list[dict]:
    prof = m.m["profils"]["complet"]
    origine = {"thresholds": prof["thresholds"], "conformal_q": prof["conformal_q"]}
    alpha, rapports = m.m["abstention"]["alpha"], m.m["decision"]["rapports_cout"]
    Rd = m.m["decision"]["rapport_defaut"]
    uniques = np.unique(lesions)
    lignes = []
    for rep in range(N_REPETITIONS):
        rng = np.random.default_rng(rep)
        local = np.isin(lesions, rng.choice(uniques, len(uniques) // 2, replace=False))
        prop = R.proposer(p[local], y[local], origine, alpha, rapports, Rd, m.mel, m.classes)
        reco = prop["resume"]["recommandation"]["decision"] == "appliquer"
        for nom, params in (("seuils d'origine", origine), ("seuils recalibrés", prop["parametres"]),
                            ("recommandation suivie", prop["parametres"] if reco else origine)):
            ev = R._evaluer(p[~local], y[~local], params, Rd, m.mel)
            lignes.append({"condition": condition, "repetition": rep, "seuils": nom, **ev,
                           "sensibilite_mel": sensibilite_mel(p[~local], y[~local], params["thresholds"][str(Rd)], m.mel),
                           "n_local": int(local.sum()), "n_evaluation": int((~local).sum()),
                           "recommande_appliquer": reco})
    return lignes


def main() -> None:
    df = get_split()
    test = df[(df.split == "test") & df.age.notna() & (df.sex != "unknown") & (df.localization != "unknown")]
    m = Moteur(BUNDLE, device="cuda")
    y, lesions = test.y.to_numpy(), test.lesion_id.to_numpy()
    lignes = []
    for condition, transformer in (("images d'origine", False), ("autre dermoscope (simulé)", True)):
        print(f"{condition} : {len(test)} images…")
        p = probabilites(m, test, transformer)
        lignes += comparer(p, y, lesions, m, condition)
    t = pd.DataFrame(lignes)
    t.to_csv(C.TAB_DIR / "13_recalibrage_decalage_detail.csv", index=False, encoding="utf-8")
    cols = ["couverture", "couverture_mel", "taux_traite", "mel_manques_en_silence", "sensibilite_mel",
            "recommande_appliquer"]
    res = t.groupby(["condition", "seuils"], sort=False)[cols].agg(["mean", "std"]).round(4)
    res.columns = [f"{a} ({b})" for a, b in res.columns]
    res.to_csv(C.TAB_DIR / "13_recalibrage_decalage.csv", encoding="utf-8")
    print(res.to_string())
    print(json.dumps({"n_images": int(len(test)), "repetitions": N_REPETITIONS}, ensure_ascii=False))


if __name__ == "__main__":
    main()
