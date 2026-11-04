"""Évaluation de la version 3 (HAM10000 + BCN20000), selon application/docs/plan_v3.md.

1. Règle de retenue, SUR LA VALIDATION HAM (1 023 images) : pour chacun des deux profils, l'ensemble des 3 graines
   v3 doit atteindre au moins la v2 en F1 macro, AUC macro et AUC mélanome.
2. Mesure, une seule fois, après la décision : test HAM (mêmes 1 009 images, v2 et v3) et test BCN (jamais vu).
   Seuil de coût sur la validation propre à chaque version (HAM pour v2, combinée pour v3), conforme Mondrian sur
   la calibration propre à chaque version. Intervalles de confiance par bootstrap sur les lésions.
3. Analyse ajoutée (information, aucune décision) : la v2 appliquée au test BCN, c'est-à-dire une validation externe
   de la v2 sur un hôpital qu'elle n'a jamais vu (profil sans contexte, localisation inconnue, âge et sexe réels).

Usage : python -m src.evaluer_v3
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score

from . import config as C
from .analyses import MALIGNANT
from .conformal import Conformal, abstain_rule
from .data import ClinicalEncoder, get_split
from .decision import decide, tune_mel_threshold
from .donnees_v3 import get_split_v3
from .metrics import classification_metrics, lesion_bootstrap_indices

PROFILS = {"complet": {"v2": ("M5_B2", "p"), "v3": ("V3_M5_B2", "p")},
           "sans_contexte": {"v2": ("M5_dropClin_B2", "p_noclin"), "v3": ("V3_M5_dropClin_B2", "p_noclin")}}
R = C.DEFAULT_COST_RATIO


def ensemble(exp: str, cle: str, df: pd.DataFrame) -> pd.DataFrame:
    """Probabilités moyennes des 3 graines, une ligne par image évaluée (val, calib, test)."""
    ps, idx = [], None
    for s in C.TRAIN_SEEDS:
        d = np.load(C.PRED_DIR / f"{exp}_s{s}.npz")
        idx = d["idx"] if idx is None else idx
        assert (d["idx"] == idx).all()
        ps.append(d[cle])
    out = df.iloc[idx].reset_index(drop=True).copy()
    out["p"] = list(np.mean(ps, axis=0))
    return out


def P(t: pd.DataFrame) -> np.ndarray:
    return np.stack(t.p.to_numpy())


def mesures_argmax(t: pd.DataFrame) -> dict:
    m = classification_metrics(t.y.to_numpy(), P(t).argmax(1), P(t))
    return {k: m[k] for k in ("F1 macro", "AUC OvR macro", "AUC mel", "Exactitude équilibrée")}


# ---------------------------------------------------------------- 1. règle de retenue
def regle(v2: dict, v3: dict) -> tuple[bool, pd.DataFrame]:
    lignes, ok = [], []
    for profil in PROFILS:
        a = mesures_argmax(v2[profil].query("split == 'val'"))
        b = mesures_argmax(v3[profil].query("split == 'val' and source == 'HAM10000'"))
        assert len(v2[profil].query("split == 'val'")) == len(v3[profil].query("split == 'val' and source == 'HAM10000'")) == 1023
        bon = all(b[k] >= a[k] for k in ("F1 macro", "AUC OvR macro", "AUC mel"))
        ok.append(bon)
        for version, m in (("v2", a), ("v3", b)):
            lignes.append({"profil": profil, "version": version, **{k: round(v, 4) for k, v in m.items()}, "regle_satisfaite_par_v3": bon})
    t = pd.DataFrame(lignes)
    t.to_csv(C.TAB_DIR / "14_v3_regle_validation_ham.csv", index=False, encoding="utf-8")
    print(t.to_string(index=False))
    retenue = all(ok)
    print(f"→ règle fixée avant l'entraînement, validation HAM : {'v3 RETENUE' if retenue else 'v2 CONSERVÉE'}")
    return retenue, t


# ---------------------------------------------------------------- 2. mesure sur les tests
def reglages(t: pd.DataFrame, val_masque) -> tuple[float, Conformal]:
    v, c = t[val_masque(t, "val")], t[val_masque(t, "calib")]
    seuil = tune_mel_threshold(P(v), v.y.to_numpy(), R)[0]
    return seuil, Conformal("mondrian", C.ALPHA).fit(P(c), c.y.to_numpy())


def ic(valeurs: list[float]) -> str:
    a = np.array([v for v in valeurs if not np.isnan(v)])
    return f"[{np.percentile(a, 2.5):.3f} ; {np.percentile(a, 97.5):.3f}]"


def mesurer(t: pd.DataFrame, seuil: float, cf: Conformal, nom: str, boot: bool = True) -> dict:
    p, y = P(t), t.y.to_numpy()
    pred = decide(p, seuil)
    sets = cf.sets(p)
    traite = abstain_rule(sets, pred)
    mel, malin = y == C.MEL, np.isin(y, MALIGNANT)
    renvoye = np.isin(pred, MALIGNANT) | ~traite
    jeunes = mel & (t.age.to_numpy() < 50)
    m_arg, m_cout = classification_metrics(y, p.argmax(1), p), classification_metrics(y, pred, p)
    alerte = pred == C.MEL
    r = {"jeu": nom, "images": len(t), "lésions": t.lesion_id.nunique(), "mélanomes": int(mel.sum()),
         "F1 macro": m_arg["F1 macro"], "Exactitude équilibrée": m_arg["Exactitude équilibrée"],
         "AUC OvR macro": m_arg["AUC OvR macro"], "AUC mel": m_arg["AUC mel"],
         "seuil mel (R=10)": seuil, "Sensibilité mel": m_cout["Sensibilité mel"], "Spécificité mel": m_cout["Spécificité mel"],
         "VPP alerte mel": float(mel[alerte].mean()) if alerte.any() else np.nan,
         "Mélanomes <50 ans": int(jeunes.sum()),
         "Sensibilité mel <50 ans": float(alerte[jeunes].mean()) if jeunes.any() else np.nan,
         "Couverture conforme": float(sets[np.arange(len(y)), y].mean()),
         "Cas traités seuls": float(traite.mean()),
         "Mélanomes classés bénins sans renvoi": int((mel & traite & ~alerte).sum()),
         "Sensibilité malin (triage)": float(renvoye[malin].mean()), "Part des cas renvoyés": float(renvoye.mean())}
    if boot:
        b = {k: [] for k in ("sens", "spec", "auc", "jeunes")}
        for i in lesion_bootstrap_indices(t.lesion_id.to_numpy()):
            mi, ai, ji = mel[i], alerte[i], jeunes[i]
            b["sens"].append(ai[mi].mean()); b["spec"].append((~ai[~mi]).mean())
            b["auc"].append(roc_auc_score(mi, p[i, C.MEL])); b["jeunes"].append(ai[ji].mean() if ji.any() else np.nan)
        r.update({"IC95 sensibilité mel": ic(b["sens"]), "IC95 spécificité mel": ic(b["spec"]),
                  "IC95 AUC mel": ic(b["auc"]), "IC95 sensibilité mel <50 ans": ic(b["jeunes"])})
    return r


def masque_v2(t: pd.DataFrame, s: str) -> pd.Series:
    return t.split == s


def masque_v3(t: pd.DataFrame, s: str) -> pd.Series:
    return t.split == s                                   # validation et calibration combinées (HAM + BCN)


# ---------------------------------------------------------------- 3. v2 sur le test BCN (analyse ajoutée)
@torch.no_grad()
def v2_sur_bcn(test_bcn: pd.DataFrame) -> pd.DataFrame:
    """Prédictions de la v2 (profil sans contexte) sur le test BCN, avec le prétraitement de la v2 (pas de recadrage)."""
    from .data import _load_resized, normalize
    from .models import SkinNet
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ham = get_split()
    enc = ClinicalEncoder().fit(ham[ham.split == "train"])
    ctx = test_bcn[["age", "sex"]].assign(localization="unknown")
    z = torch.from_numpy(enc.transform(ctx)).to(dev)
    x_all = np.stack([_load_resized(p, 288) for p in test_bcn.path])
    ps = []
    for s in C.TRAIN_SEEDS:
        net = SkinNet(fusion="film", n_clin=enc.n_features, film="final", backbone="efficientnet_b2", pretrained=False)
        net.load_state_dict(torch.load(C.CKPT_DIR / f"M5_dropClin_B2_s{s}.pt", map_location=dev))
        net.to(dev).eval()
        out = []
        for d in range(0, len(x_all), 64):
            x = torch.from_numpy(x_all[d:d + 64]).to(dev).permute(0, 3, 1, 2).float().div(255)
            x = normalize(x)
            zz = z[d:d + 64]
            with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                v = [x, x.flip(3), x.flip(2), x.flip(2).flip(3)]
                out.append((sum(torch.softmax(net(u, zz).float(), 1) for u in v) / 4).cpu().numpy())
        ps.append(np.concatenate(out))
    t = test_bcn.copy()
    t["p"] = list(np.mean(ps, axis=0))
    return t


def main() -> None:
    ham, v3df = get_split(), get_split_v3()
    v2 = {pr: ensemble(*PROFILS[pr]["v2"], ham) for pr in PROFILS}
    v3 = {pr: ensemble(*PROFILS[pr]["v3"], v3df) for pr in PROFILS}
    retenue, _ = regle(v2, v3)

    lignes = []
    s2, cf2 = reglages(v2["complet"], masque_v2)
    s3, cf3 = reglages(v3["complet"], masque_v3)
    t3 = v3["complet"]
    lignes.append({"version": "v2", "profil": "complet", **mesurer(v2["complet"].query("split == 'test'"), s2, cf2, "test HAM")})
    lignes.append({"version": "v3", "profil": "complet", **mesurer(t3.query("split == 'test' and source == 'HAM10000'"), s3, cf3, "test HAM")})
    lignes.append({"version": "v3", "profil": "complet", **mesurer(t3.query("split == 'test' and source == 'BCN20000'"), s3, cf3, "test BCN")})

    # analyse ajoutée : v2 et v3 sur le test BCN, profil sans contexte, localisation inconnue
    s2n, cf2n = reglages(v2["sans_contexte"], masque_v2)
    s3n, cf3n = reglages(v3["sans_contexte"], masque_v3)
    bcn_test = v3df.query("split == 'test' and source == 'BCN20000'").reset_index(drop=True)
    lignes.append({"version": "v2", "profil": "sans contexte (loc. inconnue, âge et sexe réels)",
                   **mesurer(v2_sur_bcn(bcn_test), s2n, cf2n, "test BCN (externe pour v2)")})
    lignes.append({"version": "v3", "profil": "sans contexte (contexte absent)",
                   **mesurer(v3["sans_contexte"].query("split == 'test' and source == 'BCN20000'"), s3n, cf3n, "test BCN")})

    t = pd.DataFrame(lignes)
    t.to_csv(C.TAB_DIR / "14_v3_tests.csv", index=False, encoding="utf-8")
    with pd.option_context("display.max_columns", None, "display.width", 250):
        print(t.T.to_string())
    (C.TAB_DIR / "14_v3_decision.json").write_text(json.dumps({"v3_retenue": bool(retenue)}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
