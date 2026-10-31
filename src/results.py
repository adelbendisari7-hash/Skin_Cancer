"""Étapes 4 à 8 — tous les tableaux et figures de résultats en une exécution.

Usage : python -m src.results   (après src.run_all)
Aucun réglage n'utilise le test : seuils et poids viennent de la validation,
la prédiction conforme de la calibration.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config as C
from . import figures, viz
from .analyses import abstention_table, conformal_choice_on_val
from .data import get_split
from .evaluate import bootstrap_compare, load_runs, metrics_table, summarize

COLS = ["F1 macro", "Exactitude équilibrée", "AUC OvR macro", "AUC mel", "Sensibilité mel",
        "Spécificité mel", "Coût attendu", "Exactitude"]
R = f"coût R={C.DEFAULT_COST_RATIO}"


def choose_conformal(runs: dict, df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """Règle fixée à l'avance : parmi les méthodes couvrant le mélanome à ≥ 1 − α sur la
    VALIDATION, prendre celle qui traite le plus de cas ; à défaut, la meilleure couverture mel."""
    val = conformal_choice_on_val(runs, df)
    ok = val[val["couverture mel"] >= 1 - C.ALPHA]
    method = ok["taux traité"].idxmax() if len(ok) else val["couverture mel"].idxmax()
    return method, val


def main() -> None:
    viz.setup()
    df = get_split()
    runs = load_runs(df)
    print("Runs :", sorted({e for e, _ in runs}), "\n")

    # Étape 4-6 : courbes d'apprentissage et poids de M4
    figures.learning_curves(["M1", "M3", "M5", "M5_sansFiLM", "M5_sansCout", "M5_dropClin"])
    figures.m4_weight_curves(runs)
    m4w = {s: runs[("M4", s)]["w"] for s in C.TRAIN_SEEDS if ("M4", s) in runs}
    (C.TAB_DIR / "06_M4_poids.json").write_text(json.dumps(m4w))
    print("Poids de l'image dans M4 (choisi sur la validation) :", m4w)
    meta = []
    for exp in ["M1", "M3", "M5", "M5_filmMulti", "M5_sansFiLM", "M5_sansCout", "M5_dropClin"]:
        for s in C.TRAIN_SEEDS:
            f = C.PRED_DIR / f"{exp}_s{s}.json"
            if f.exists():
                m = json.loads(f.read_text(encoding="utf-8"))
                meta.append({k: m.get(k) for k in ["exp", "seed", "best_val_f1", "best_epoch", "epochs_run",
                                                   "train_time_s"]})
    meta = pd.DataFrame(meta)
    meta.to_csv(C.TAB_DIR / "04_entrainements.csv", index=False)
    print(meta.round(4).to_string(index=False), "\n")

    # Étape 7 : tableau final (moyenne ± écart-type sur 3 graines)
    tab = metrics_table(runs, df)
    tab.to_csv(C.TAB_DIR / "07_metriques_par_graine.csv", index=False)
    final = summarize(tab[tab.décision != "coût + abstention"], COLS)
    final.to_csv(C.TAB_DIR / "07_comparaison_finale.csv", index=False)
    print(final.to_string(index=False), "\n")
    main_models = ["M1 image", "M2 clinique", "M3 concaténation", "M4 fusion tardive", "M5 FiLM + coût (proposé)"]
    figures.comparison_dots(tab, main_models, "07_comparaison_modeles",
                            "Unimodal vs multimodal sur le test (moyenne ± écart-type, 3 graines)")
    abl = ["M5 FiLM + coût (proposé)", "M5 sans FiLM (concat + coût)", "M5 sans coût (FiLM + CE)",
           "M3 concaténation", "M1 image"]
    figures.comparison_dots(tab, abl, "07_ablations", "Études d'ablation de M5 (test, moyenne ± écart-type, 3 graines)")

    # Bootstrap apparié par lésion pour les comparaisons clés
    pairs = [
        (("M5", R), ("M1", "classique")),        # IA prudente complète vs classifieur classique
        (("M5", R), ("M1", R)),                  # à règle de décision égale
        (("M5", R), ("M3", R)),
        (("M5", R), ("M4", R)),
        (("M5", R), ("M5_sansFiLM", R)),         # ablation FiLM
        (("M5", R), ("M5_sansCout", R)),         # ablation perte de coût
        (("M5_sansCout", R), ("M3", R)),         # FiLM vs concaténation, cette fois avec la perte classique
        (("M5", "classique"), ("M1", "classique")),
        (("M3", "classique"), ("M1", "classique")),   # apport du contexte (fusion simple)
        (("M4", "classique"), ("M1", "classique")),
    ]
    boot = bootstrap_compare(runs, df, pairs)
    boot.to_csv(C.TAB_DIR / "07_bootstrap_comparaisons.csv", index=False)
    print(boot.to_string(index=False), "\n")

    # Étape 8 : confusions, coût, abstention
    figures.confusion_pair(runs, df, ("M1", "classique", "M1 image — décision classique"),
                           ("M5", R, f"M5 proposé — décision au coût (R={C.DEFAULT_COST_RATIO})"))
    cs = figures.cost_sensitivity(runs, df, ["M1", "M3", "M4", "M5"])
    cs_sum = cs.groupby(["modèle", "R"]).agg(["mean", "std"]).drop(columns="graine")
    cs_sum.round(3).to_csv(C.TAB_DIR / "08_sensibilite_cout.csv")
    print(cs.groupby(["modèle", "R"]).mean(numeric_only=True).drop(columns="graine").round(3).to_string(), "\n")

    method, val = choose_conformal(runs, df)
    figures.pipeline_diagram(method)
    print("Choix de la méthode conforme sur la validation :\n", val.round(3).to_string())
    print(f"→ méthode retenue : {method}\n")
    (C.TAB_DIR / "08_methode_conforme.json").write_text(json.dumps({"méthode": method, "alpha": C.ALPHA}))
    ab = abstention_table(runs, df, method)
    summ = ab.drop(columns="graine").groupby("modèle", sort=False).mean().round(3)
    print(summ.T.to_string(), "\n")
    # Comparaison des trois méthodes conformes sur le test pour M5 (information, pas de choix)
    rows = []
    for m in ["lac", "aps", "mondrian"]:
        t = abstention_table(runs, df, m, write=False)
        t = t[t.modèle == "M5 FiLM + coût (proposé)"].drop(columns=["graine", "modèle"]).mean()
        rows.append({"méthode": m, **t.to_dict()})
    cmp = pd.DataFrame(rows).set_index("méthode")
    cmp.round(3).to_csv(C.TAB_DIR / "08_methodes_conformes_test_M5.csv")
    print(cmp.round(3).T.to_string(), "\n")
    rc = figures.risk_coverage(runs, df, ["M1", "M5"], method=method)
    rc.to_csv(C.TAB_DIR / "08_risque_couverture.csv", index=False)


if __name__ == "__main__":
    main()
