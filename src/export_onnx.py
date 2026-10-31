"""Exporte le paquet de modèle v2 pour l'analyse DANS LE NAVIGATEUR (ONNX Runtime Web).

Chaque réseau est coupé en deux graphes :
- tronc : image → carte de caractéristiques finale (avant FiLM) + moyennes de chaque étape (détecteur hors sujet) ;
- tête  : (carte, contexte clinique) → logits + carte de classe par diagnostic (FiLM + couche finale).
Ainsi le contexte peut changer (« et si ») sans repasser l'image dans le tronc. La tête donne aussi Grad-CAM sans
gradient : pour une moyenne spatiale suivie d'une couche linéaire, Grad-CAM vaut Σ w_ck · F_k à un facteur près.

Les poids sont stockés en float16 (taille divisée par deux) et reconvertis en float32 au chargement.
Le script vérifie l'équivalence avec le moteur PyTorch de l'application avant d'écrire la configuration.

Usage : python -m src.export_onnx
"""
from __future__ import annotations

import hashlib
import json
import sys

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn as nn
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from . import config as C
from .data import get_split

APP = C.PROJECT_DIR / "application"
sys.path.insert(0, str(APP / "backend"))
from dermia.engine import Contexte, Moteur  # noqa: E402

BUNDLE = APP / "modeles" / "ham10000-m5-v2"
SORTIE = APP / "frontend" / "demo-statique" / "modele"
OPSET = 18


class Tronc(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.features = net.features

    def forward(self, x):
        moyennes = []
        for block in self.features:
            x = block(x)
            moyennes.append(x.mean((2, 3)))
        return (x, *moyennes)


class Tete(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.clin, self.film = net.clin, net.film["8"]
        self.lineaire = net.head[1]

    def forward(self, f, z):
        gamma, beta = self.film(self.clin(z)).chunk(2, dim=1)
        x = f * (1 + gamma[:, :, None, None]) + beta[:, :, None, None]
        logits = self.lineaire(x.mean((2, 3)))
        cartes = torch.einsum("kc,ncij->nkij", self.lineaire.weight, x)
        return logits, cartes


def demi_precision(chemin) -> None:
    """Initialiseurs float32 → float16 + Cast vers float32 (constant-folding au chargement de la session)."""
    m = onnx.load(str(chemin))
    nouveaux, casts = [], []
    for init in list(m.graph.initializer):
        if init.data_type == TensorProto.FLOAT and np.prod(init.dims or [1]) > 8:
            a = numpy_helper.to_array(init)
            nom = init.name
            nouveaux.append(numpy_helper.from_array(a.astype(np.float16), f"{nom}__f16"))
            casts.append(helper.make_node("Cast", [f"{nom}__f16"], [nom], to=TensorProto.FLOAT))
            m.graph.initializer.remove(init)
    m.graph.initializer.extend(nouveaux)
    noeuds = casts + list(m.graph.node)
    del m.graph.node[:]
    m.graph.node.extend(noeuds)
    onnx.checker.check_model(m)
    onnx.save(m, str(chemin))


def exporter(net, profil: str, s: int, taille: int, n_clin: int, canaux: int) -> dict:
    tronc, tete = SORTIE / f"{profil}_s{s}_tronc.onnx", SORTIE / f"{profil}_s{s}_tete.onnx"
    x = torch.zeros(2, 3, taille, taille)
    f = torch.zeros(2, canaux, taille // 32, taille // 32)
    z = torch.zeros(2, n_clin)
    noms = ["carte"] + [f"e{i}" for i in range(len(net.features))]
    torch.onnx.export(Tronc(net).eval(), (x,), str(tronc), opset_version=OPSET, dynamo=False, input_names=["image"],
                      output_names=noms, dynamic_axes={"image": {0: "n"}, **{k: {0: "n"} for k in noms}})
    torch.onnx.export(Tete(net).eval(), (f, z), str(tete), opset_version=OPSET, dynamo=False,
                      input_names=["carte", "contexte"], output_names=["logits", "cartes"],
                      dynamic_axes={k: {0: "n"} for k in ("carte", "contexte", "logits", "cartes")})
    demi_precision(tronc)
    demi_precision(tete)
    sortie = {}
    for nom, chemin in (("tronc", tronc), ("tete", tete)):
        sortie[nom] = {"fichier": chemin.name, "octets": chemin.stat().st_size,
                       "sha256": hashlib.sha256(chemin.read_bytes()).hexdigest()}
    return sortie


def verifier(moteur: Moteur, df) -> None:
    """Mêmes probabilités, mêmes cartes et même score hors sujet que le moteur PyTorch (CPU, float32)."""
    opt = ort.SessionOptions()
    opt.log_severity_level = 3
    sessions = {p: [(ort.InferenceSession(str(SORTIE / f"{p}_s{s}_tronc.onnx"), opt, providers=["CPUExecutionProvider"]),
                     ort.InferenceSession(str(SORTIE / f"{p}_s{s}_tete.onnx"), opt, providers=["CPUExecutionProvider"]))
                    for s in C.TRAIN_SEEDS] for p in ("complet", "sans_contexte")}
    cas = df[(df.split == "test") & df.age.notna() & (df.sex != "unknown") & (df.localization != "unknown")].iloc[:24]
    ecart_max = 0.0
    for _, r in cas.iterrows():
        im = Image.open(r.path).convert("RGB")
        for ctx in (Contexte(float(r.age), r.sex, r.localization), Contexte(None, None, None)):
            res, x = moteur.analyser(im, ctx)
            z = moteur.encoder_contexte(ctx).cpu().numpy()
            xn = x.cpu().numpy()
            vues = [xn, xn[..., ::-1], xn[..., ::-1, :], xn[..., ::-1, ::-1]]
            lot = np.concatenate(vues).copy()
            zs = np.repeat(z, 4, axis=0)
            p = np.zeros(7)
            for tr, te in sessions[res.profil]:
                carte = tr.run(["carte"], {"image": lot})[0]
                logits = te.run(["logits"], {"carte": carte, "contexte": zs})[0]
                e = np.exp(logits - logits.max(1, keepdims=True))
                p += (e / e.sum(1, keepdims=True)).sum(0)
            p /= 12
            ecart_max = max(ecart_max, float(np.abs(p - np.array([res.probabilites[c] for c in moteur.classes])).max()))
    print(f"Écart maximal ONNX float16 / PyTorch : {ecart_max:.2e} sur {len(cas) * 2} analyses")
    assert ecart_max < 2e-3, ecart_max


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    moteur = Moteur(BUNDLE, device="cpu")
    m = moteur.m
    taille = m["pretraitement"]["taille"]
    fichiers = {}
    for profil, nets in moteur.reseaux.items():
        fichiers[profil] = []
        for s, net in enumerate(nets):
            canaux = net.canaux[-1]
            fichiers[profil].append(exporter(net, profil, s, taille, m["profils"][profil]["n_clin"], canaux))
            print(profil, s, {k: f"{v['octets'] / 1e6:.1f} Mo" for k, v in fichiers[profil][-1].items()})

    # Détecteur hors sujet : tableaux float32 concaténés, décrits dans config.json
    hs = m["hors_sujet"]
    d = np.load(BUNDLE / hs["fichier"])
    morceaux, couches = [], []
    for e in hs["etages"]:
        mu, prec = d[f"moyennes_{e}"].astype(np.float32), d[f"precision_{e}"].astype(np.float32)
        couches.append({"etage": e, "dim": int(mu.shape[1])})
        morceaux += [mu.tobytes(), prec.tobytes()]
    (SORTIE / "hors_sujet.bin").write_bytes(b"".join(morceaux))

    seuils_abcd = json.loads((APP / "backend" / "dermia" / "engine" / "seuils_abcd.json").read_text(encoding="utf-8"))
    config = {
        "nom": m["nom"], "version": m["version"], "taille": taille, "moyenne": m["pretraitement"]["moyenne"],
        "ecart_type": m["pretraitement"]["ecart_type"], "classes": m["classes"], "mel": m["indice_melanome"],
        "classes_malignes": m["classes_malignes"], "encodeur": m["encodeur_clinique"],
        "rapport_defaut": m["decision"]["rapport_defaut"], "rapports_cout": m["decision"]["rapports_cout"],
        "profils": {p: {"thresholds": v["thresholds"], "conformal_q": v["conformal_q"], "reseaux": fichiers[p]}
                    for p, v in m["profils"].items()},
        "hors_sujet": {"seuil": hs["seuil"], "profil": hs["profil"], "couches": couches, "normalisation": hs["normalisation"],
                       "n_classes": len(m["classes"]), "octets": sum(len(b) for b in morceaux)},
        "seuils_abcd": seuils_abcd,
    }
    (SORTIE / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    verifier(moteur, get_split())
    total = sum(f.stat().st_size for f in SORTIE.iterdir()) / 1e6
    print(f"Modèle pour le navigateur : {SORTIE} — {total:.1f} Mo")


if __name__ == "__main__":
    main()
