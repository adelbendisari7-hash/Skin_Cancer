"""Entraînement commun des réseaux (M1, M3, M5 et ablations).

Même tronc, mêmes augmentations, même optimiseur, même critère d'arrêt pour tous :
seules la fusion et la perte changent, ce qui rend les comparaisons équitables.

Usage :
    python -m src.train --exp M1 --seeds 0 1 2
    python -m src.train --exp M5 --seeds 0 --epochs 1 --subset 600   # test rapide
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import balanced_accuracy_score, f1_score

from . import config as C
from .data import ClinicalEncoder, build_image_cache, get_split, gpu_augment, normalize, to_device_batch
from .models import SkinNet

# Chaque expérience = (type de fusion, perte, options). Les ablations de M5 n'enlèvent qu'un ingrédient.
EXPERIMENTS: dict[str, dict] = {
    "M1": dict(fusion="none", loss="ce"),                        # image seule, classique
    "M3": dict(fusion="concat", loss="ce"),                      # fusion précoce, classique
    "M5": dict(fusion="film", loss="cost", film="final"),        # modèle proposé
    # Variante pilote (graine 0) : FiLM sur 3 étages. Écartée sur la validation
    # (meilleur F1 macro val 0,662 contre 0,698 pour FiLM final seul).
    "M5_filmMulti": dict(fusion="film", loss="cost", film="multi"),
    "M5_sansFiLM": dict(fusion="concat", loss="cost"),           # ablation : concaténation au lieu de FiLM
    "M5_sansCout": dict(fusion="film", loss="ce", film="final"), # ablation : perte classique
    "M5_dropClin": dict(fusion="film", loss="cost", film="final", clin_dropout=C.CLINICAL_DROPOUT_P),
    # Version 2 (proposition 12) : tronc plus puissant et résolution plus élevée, même recette.
    "M5_B2": dict(fusion="film", loss="cost", film="final", backbone="efficientnet_b2", taille=288),
    "M5_dropClin_B2": dict(fusion="film", loss="cost", film="final", backbone="efficientnet_b2", taille=288,
                           clin_dropout=C.CLINICAL_DROPOUT_P),
}


def set_seed(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)


def class_weights(y_train: np.ndarray) -> np.ndarray:
    """Poids ∝ (n_max / n_k)^p, renforcés pour le mélanome, puis normalisés (poids moyen par image = 1)."""
    n = np.bincount(y_train, minlength=C.N_CLASSES).astype(float)
    w = (n.max() / n) ** C.CLASS_WEIGHT_POWER
    w[C.MEL] *= C.MEL_WEIGHT_BOOST
    return w / (w * n).sum() * n.sum()


@torch.no_grad()
def predict(model: SkinNet, bank: np.ndarray, idx: np.ndarray, clin: torch.Tensor | None,
            device: torch.device, tta: bool = True, batch: int = 128) -> np.ndarray:
    """Probabilités (n, 7). TTA : moyenne sur 4 retournements (l'orientation n'a pas de sens)."""
    model.eval()
    out = []
    for s in range(0, len(idx), batch):
        b = idx[s:s + batch]
        x = normalize(to_device_batch(bank, b, device))
        z = clin[b] if clin is not None else None
        views = [x, x.flip(3), x.flip(2), x.flip(2).flip(3)] if tta else [x]
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            p = sum(F.softmax(model(v, z).float(), dim=1) for v in views) / len(views)
        out.append(p.cpu().numpy())
    return np.concatenate(out)


def train(exp: str, seed: int, epochs: int = C.EPOCHS, subset: int | None = None,
          verbose: bool = True) -> dict:
    cfg = EXPERIMENTS[exp]
    set_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.backends.cudnn.benchmark = False   # l'auto-réglage coûte ~90 s par forme de lot ici

    df = get_split()
    enc = ClinicalEncoder().fit(df[df.split == "train"])
    clin_np = enc.transform(df)
    clin = torch.from_numpy(clin_np).to(device)
    missing = torch.from_numpy(enc.missing_context(1)).to(device)       # contexte « inconnu »
    taille = cfg.get("taille", C.IMG_SIZE)
    bank = np.array(build_image_cache(df, taille))                        # copie en RAM (1,5 à 2,5 Go)
    y_all = df.y.to_numpy().copy()
    split = df.split.to_numpy()
    idx = {s: np.flatnonzero(split == s) for s in ["train", "val", "calib", "test"]}
    rng = np.random.default_rng(seed)
    if subset:                                                            # test rapide uniquement
        idx = {s: rng.choice(v, min(subset, len(v)), replace=False) for s, v in idx.items()}
    y_t = torch.from_numpy(y_all).to(device)

    model = SkinNet(fusion=cfg["fusion"], n_clin=enc.n_features, film=cfg.get("film", "multi"),
                    backbone=cfg.get("backbone", "efficientnet_b0"))
    model = model.to(device)   # NB : channels_last est 7× plus lent sur ce GPU (mesuré)
    use_clin = cfg["fusion"] != "none"

    w = class_weights(y_all[idx["train"]]) if cfg["loss"] == "cost" else np.ones(C.N_CLASSES)
    w_t = torch.tensor(w, dtype=torch.float32, device=device)
    opt = torch.optim.AdamW(model.param_groups(C.LR_BACKBONE, C.LR_HEAD), weight_decay=C.WEIGHT_DECAY)
    steps_per_epoch = len(idx["train"]) // C.BATCH_SIZE
    assert steps_per_epoch > 0, "jeu d'entraînement plus petit qu'un lot (--subset trop petit)"
    total, warm = epochs * steps_per_epoch, steps_per_epoch
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda t: min(1.0, (t + 1) / warm) * 0.5 * (1 + np.cos(np.pi * min(t, total) / total)))
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    gen = torch.Generator(device=device).manual_seed(seed)
    p_drop = cfg.get("clin_dropout", 0.0)

    best, best_state, history, wait = -1.0, None, [], 0
    t0 = time.time()
    for ep in range(1, epochs + 1):
        model.train()
        perm = rng.permutation(idx["train"])
        losses = []
        for s in range(steps_per_epoch):
            b = perm[s * C.BATCH_SIZE:(s + 1) * C.BATCH_SIZE]
            x = normalize(gpu_augment(to_device_batch(bank, b, device), gen))
            z = clin[b] if use_clin else None
            if use_clin and p_drop > 0:                                     # dropout de modalité
                mask = torch.rand(len(b), generator=gen, device=device) < p_drop
                z = torch.where(mask[:, None], missing.expand_as(z), z)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                loss = F.cross_entropy(model(x, z).float(), y_t[b], weight=w_t)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update(); sched.step()
            losses.append(loss.item())
        p_val = predict(model, bank, idx["val"], clin if use_clin else None, device, tta=False)
        pred = p_val.argmax(1)
        f1 = f1_score(y_all[idx["val"]], pred, average="macro", labels=list(range(C.N_CLASSES)),
                      zero_division=0)
        bacc = balanced_accuracy_score(y_all[idx["val"]], pred)
        history.append({"époque": ep, "perte train": float(np.mean(losses)), "F1 macro val": f1,
                        "exactitude équilibrée val": bacc, "temps (s)": round(time.time() - t0, 1)})
        if verbose:
            print(f"[{exp} s{seed}] ép {ep:2d}  perte {np.mean(losses):.3f}  F1 val {f1:.3f}  "
                  f"bAcc val {bacc:.3f}  {time.time() - t0:.0f}s", flush=True)
        if f1 > best:
            best, best_state, wait = f1, copy.deepcopy(model.state_dict()), 0
        else:
            wait += 1
            if wait >= C.PATIENCE:
                break

    # Meilleure époque (selon le F1 macro de validation) → prédictions finales avec TTA
    model.load_state_dict(best_state)
    eval_idx = np.concatenate([idx["val"], idx["calib"], idx["test"]])
    p = predict(model, bank, eval_idx, clin if use_clin else None, device)
    res = {"idx": eval_idx, "p": p}
    if use_clin:   # même modèle, contexte patient entièrement manquant (bonus robustesse)
        res["p_noclin"] = predict(model, bank, eval_idx, missing.expand(len(df), -1), device)
    tag = f"{exp}_s{seed}" + (f"_sub{subset}" if subset else "")
    if not subset:
        np.savez_compressed(C.PRED_DIR / f"{tag}.npz", **res)
        torch.save(best_state, C.CKPT_DIR / f"{tag}.pt")
        pd.DataFrame(history).to_csv(C.PRED_DIR / f"{tag}_history.csv", index=False)
        meta = {"exp": exp, "seed": seed, **cfg, "best_val_f1": best,
                "best_epoch": int(np.argmax([h["F1 macro val"] for h in history]) + 1),
                "epochs_run": len(history), "train_time_s": round(time.time() - t0, 1),
                "class_weights": [round(float(v), 4) for v in w]}
        (C.PRED_DIR / f"{tag}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return {"tag": tag, "best_val_f1": best, "history": history, **res}


def load_predictions(exp: str, seed: int) -> dict:
    """Recharge les probabilités sauvegardées d'une expérience."""
    d = np.load(C.PRED_DIR / f"{exp}_s{seed}.npz")
    return {k: d[k] for k in d.files}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, choices=list(EXPERIMENTS))
    ap.add_argument("--seeds", type=int, nargs="+", default=C.TRAIN_SEEDS)
    ap.add_argument("--epochs", type=int, default=C.EPOCHS)
    ap.add_argument("--subset", type=int, default=None)
    a = ap.parse_args()
    for sd in a.seeds:
        r = train(a.exp, sd, a.epochs, a.subset)
        print(f"==> {r['tag']} meilleur F1 macro val = {r['best_val_f1']:.4f}", flush=True)
