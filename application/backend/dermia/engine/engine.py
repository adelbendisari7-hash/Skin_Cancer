"""Moteur d'IA : charge un paquet de modèle et analyse une image avec son contexte clinique.

Chaîne identique à l'évaluation du rapport :
image → [recadrage du champ du dermoscope si le paquet le prévoit] → taille du modèle (LANCZOS)
→ normalisation ImageNet → 4 retournements (TTA) × 3 graines
→ probabilités moyennes → décision au coût (seuil sur p(mel)) → ensemble conforme Mondrian
→ abstention si l'ensemble n'est pas le singleton {décision} → orientation clinique.
En plus : score « hors sujet » (distance de Mahalanobis dans l'espace des caractéristiques de
l'image, Lee et al. 2018) et seuils recalibrés localement s'ils ont été activés.
"""
from __future__ import annotations

import hashlib
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

from .model import SkinNet
from .triage import triage

INCONNU = "unknown"
_NOM_FIL = "dermia-calcul"


def zone_utile(im: Image.Image, regle: dict) -> tuple[int, int, int, int] | None:
    """Carré inscrit dans le cercle du dermoscope quand les coins de l'image sont noirs, sinon None.

    Règle de la version 3 (projet/src/donnees_v3.py, appliquée à l'entraînement) : niveaux de gris réduits
    en 256 × 256 (bicubique), moyenne des 4 coins de 20 px < seuil → carré inscrit dans la zone claire."""
    n, s = regle["cote_analyse"], regle["coin"]
    g = np.asarray(im.convert("L").resize((n, n), Image.BICUBIC), dtype=np.float32)
    coins = np.mean([g[:s, :s].mean(), g[:s, -s:].mean(), g[-s:, :s].mean(), g[-s:, -s:].mean()])
    if coins >= regle["seuil_coins"]:
        return None
    m = g > regle["seuil_clair"]
    if m.mean() < regle["part_claire_min"]:
        return None
    ys, xs = np.nonzero(m)
    cy, cx = ys.mean() / n, xs.mean() / n
    c = np.sqrt(m.mean() / np.pi) * np.sqrt(2) * regle["marge"]
    W, H = im.size
    return (int(max(0.0, cx - c / 2) * W), int(max(0.0, cy - c / 2) * H),
            int(min(1.0, cx + c / 2) * W), int(min(1.0, cy + c / 2) * H))


class BundleError(RuntimeError):
    """Paquet de modèle absent, incomplet ou altéré."""


@dataclass
class Contexte:
    age: float | None = None
    sexe: str | None = None            # "male" | "female" | "unknown"
    localisation: str | None = None    # une des localisations du manifest, ou "unknown"

    @property
    def complet(self) -> bool:
        return (self.age is not None and self.sexe not in (None, INCONNU)
                and self.localisation not in (None, INCONNU))


@dataclass
class Resultat:
    profil: str
    probabilites: dict[str, float]
    decision: str
    p_melanome: float
    seuil_melanome: float
    rapport_cout: int
    ensemble_conforme: list[str]
    traite: bool
    statut: str
    niveau: str
    titre: str
    message: str
    modele: str
    version: str
    duree_ms: int
    avertissements: list[dict] = field(default_factory=list)   # codes traduits par l'interface
    hors_sujet: bool = False
    score_hors_sujet: float | None = None
    calibration: str = "origine"                                 # « origine » ou « locale:<id> »

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Palette séquentielle pour la carte Grad-CAM (sombre → clair), sans dépendre de matplotlib
_CAM_STOPS = np.array([[0, 0, 4], [87, 16, 110], [188, 55, 84], [249, 142, 9], [252, 255, 164]], float)


def _colormap(v: np.ndarray) -> np.ndarray:
    x = np.clip(v, 0, 1) * (len(_CAM_STOPS) - 1)
    i = np.minimum(x.astype(int), len(_CAM_STOPS) - 2)
    t = (x - i)[..., None]
    return (_CAM_STOPS[i] * (1 - t) + _CAM_STOPS[i + 1] * t).astype(np.uint8)


class Moteur:
    def __init__(self, bundle_dir: Path, device: str | None = None, verifier_empreintes: bool = True):
        self.dir = Path(bundle_dir)
        manifest = self.dir / "manifest.json"
        if not manifest.exists():
            raise BundleError(f"manifest introuvable : {manifest}")
        self.m = json.loads(manifest.read_text(encoding="utf-8"))
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.classes: list[str] = self.m["classes"]
        self.noms: dict[str, str] = self.m["noms_classes"]
        self.mel = self.m["indice_melanome"]
        enc = self.m["encodeur_clinique"]
        self.sexes, self.zones = enc["sexes"], enc["localisations"]
        # Paquets v3 : le réseau voit des zones communes (tronc, tête et cou…) ; l'interface garde les localisations
        # détaillées, ramenées à leur zone. Paquets antérieurs : localisation = zone.
        self.correspondance: dict[str, str] = enc.get("correspondance") or {z: z for z in self.zones}
        self.localisations: list[str] = list(self.correspondance)
        self.valeurs_et_si_localisation = [z for z in self.zones if z != INCONNU]
        pre = self.m["pretraitement"]
        self.recadrage: dict | None = pre.get("recadrage")
        self.taille = pre["taille"]
        self._mean = torch.tensor(pre["moyenne"]).view(1, 3, 1, 1).to(self.device)
        self._std = torch.tensor(pre["ecart_type"]).view(1, 3, 1, 1).to(self.device)
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix=_NOM_FIL)
        self.reseaux: dict[str, list[SkinNet]] = {}
        for nom, prof in self.m["profils"].items():
            nets = []
            for w in prof["poids"]:
                path = self.dir / w["fichier"]
                if not path.exists():
                    raise BundleError(f"poids manquants : {path}")
                if verifier_empreintes and _sha256(path) != w["sha256"]:
                    raise BundleError(f"empreinte SHA-256 invalide (fichier altéré ?) : {path.name}")
                net = SkinNet(prof["fusion"], prof["n_clin"], prof.get("film", "final"), len(self.classes),
                              backbone=prof.get("architecture", "efficientnet_b0"))
                net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
                nets.append(net.to(self.device).eval())
            self.reseaux[nom] = nets
        # Détection des images hors sujet (facultative selon le paquet de modèle)
        self.hors_sujet: dict | None = None
        hs = self.m.get("hors_sujet")
        if hs:
            chemin = self.dir / hs["fichier"]
            if not chemin.exists():
                raise BundleError(f"statistiques hors sujet manquantes : {chemin}")
            if verifier_empreintes and _sha256(chemin) != hs["sha256"]:
                raise BundleError(f"empreinte SHA-256 invalide (fichier altéré ?) : {chemin.name}")
            d = np.load(chemin)
            t = lambda a: torch.tensor(a, dtype=torch.float32, device=self.device)  # noqa: E731
            if "etages" in hs:     # plusieurs étapes du réseau (Lee et al. 2018), scores normalisés puis maximum
                self._hs_etages = tuple(hs["etages"])
                self._hs_couches = [(t(d[f"moyennes_{e}"]), t(d[f"precision_{e}"])) for e in self._hs_etages]
                self._hs_norm = (t(hs["normalisation"]["moyenne"]), t(hs["normalisation"]["ecart_type"]))
            else:                  # dernière étape seulement (paquets antérieurs)
                self._hs_etages = None
                self._hs_couches = [(t(d["moyennes"]), t(d["precision"]))]
            self.hors_sujet = {"seuil": float(hs["seuil"]), "profil": hs["profil"]}
        # Recalibrage local actif, par profil : {"id", "thresholds", "conformal_q"} (géré par le serveur)
        self.calibrations: dict[str, dict] = {}

    # ------------------------------------------------------------------ entrées
    @property
    def nom(self) -> str:
        return self.m["nom"]

    @property
    def version(self) -> str:
        return self.m["version"]

    def encoder_contexte(self, ctx: Contexte) -> torch.Tensor:
        """Même encodage que l'entraînement : âge standardisé + indicateur, sexe et localisation one-hot."""
        enc = self.m["encodeur_clinique"]
        manquant = ctx.age is None
        age = enc["age_mediane"] if manquant else float(ctx.age)
        age = (age - enc["age_moyenne"]) / enc["age_ecart_type"]
        sexe = ctx.sexe if ctx.sexe in self.sexes else INCONNU
        loc = self.zone(ctx.localisation)
        v = [age, float(manquant)] + [float(s == sexe) for s in self.sexes] + \
            [float(z == loc) for z in self.zones]
        return torch.tensor([v], dtype=torch.float32, device=self.device)

    def zone(self, localisation: str | None) -> str:
        """Localisation détaillée (ou zone) → zone vue par le réseau ; « unknown » si elle n'est pas reconnue."""
        z = self.correspondance.get(localisation, localisation)
        return z if z in self.zones else INCONNU

    def cadre(self, image: Image.Image) -> tuple[int, int, int, int] | None:
        """Partie de l'image (orientée) réellement analysée, ou None pour l'image entière."""
        if not self.recadrage:
            return None
        return zone_utile(ImageOps.exif_transpose(image).convert("RGB"), self.recadrage)

    def pretraiter(self, image: Image.Image) -> torch.Tensor:
        """Image PIL → tenseur normalisé (1, 3, taille, taille), comme le cache d'entraînement."""
        im = ImageOps.exif_transpose(image).convert("RGB")
        if self.recadrage and (b := zone_utile(im, self.recadrage)):
            im = im.crop(b)
        im = im.resize((self.taille, self.taille), Image.LANCZOS)
        # .contiguous() : format mémoire NCHW standard. Sans lui, le permute laisse l'image en NHWC,
        # ce qui fait choisir à cuDNN d'autres noyaux (plus lents ici et non couverts par le préchauffage).
        x = torch.from_numpy(np.asarray(im, dtype=np.uint8).copy()).permute(2, 0, 1).contiguous()[None].float().div(255)
        return (x.to(self.device) - self._mean) / self._std

    @staticmethod
    def ouvrir(data: bytes) -> Image.Image:
        im = Image.open(io.BytesIO(data))
        im.load()
        return im

    # ------------------------------------------------------------------ fil de calcul unique
    # Les plans cuDNN préparés au premier calcul d'une forme donnée sont propres au fil d'exécution :
    # si chaque requête HTTP tournait dans son propre fil, chacune repaierait ~3 s (mesuré). Tout le
    # calcul passe donc par UN fil dédié, préchauffé une fois ; il sérialise aussi l'accès au GPU.
    def _executer(self, fonction, *args):
        if threading.current_thread().name.startswith(_NOM_FIL):
            return fonction(*args)                     # déjà dans le fil de calcul (appel interne)
        return self._fil.submit(fonction, *args).result()

    def analyser(self, image: Image.Image, ctx: Contexte, rapport_cout: int | None = None) -> tuple[Resultat, torch.Tensor]:
        return self._executer(self._analyser, image, ctx, rapport_cout)

    def gradcam(self, x: torch.Tensor, ctx: Contexte, classe: str) -> np.ndarray:
        """Carte Grad-CAM (H, W) dans [0, 1], moyennée sur les graines du profil."""
        return self._executer(self._gradcam, x, ctx, classe)

    def et_si(self, image: Image.Image, ctx: Contexte, variable: str, valeurs: list) -> list[dict]:
        """Contrefactuel : p(mélanome) quand on remplace `variable` (age | localisation) par chaque valeur."""
        if variable not in ("age", "localisation"):
            raise ValueError("variable doit être 'age' ou 'localisation'")
        return self._executer(self._et_si, image, ctx, variable, valeurs)

    def caracteristiques_lot(self, images: list[Image.Image], etages: tuple[int, ...] | None = None):
        """Caractéristiques « image seule » d'un lot d'images (statistiques hors sujet) : une matrice (N, C),
        ou une matrice par étape demandée."""
        return self._executer(self._caracteristiques_lot, images, etages)

    def parametres(self, profil: str) -> tuple[dict, list[float], str]:
        """Seuils de coût, seuils conformes et origine (recalibrage local s'il est actif)."""
        loc = self.calibrations.get(profil)
        prof = self.m["profils"][profil]
        if loc:
            return loc["thresholds"], loc["conformal_q"], f"locale:{loc['id']}"
        return prof["thresholds"], prof["conformal_q"], "origine"

    def prechauffer(self, tailles_lot: tuple[int, ...] | None = None) -> float:
        """Exécute une fois, dans le fil de calcul, chaque forme de calcul utilisée par l'interface.

        Sur GPU, la première exécution d'une nouvelle taille de lot prépare les noyaux cuDNN
        (~3 à 4 s chacune). Tailles : 1 (analyse, en premier), 16 (« et si » âge), nombre de zones (« et si »
        localisation). Les deux profils partagent les mêmes noyaux (même architecture) : un seul suffit.
        """
        return self._executer(self._prechauffer, tailles_lot or (1, 16, len(self.valeurs_et_si_localisation)))

    # ------------------------------------------------------------------ inférence (dans le fil de calcul)
    def _profil(self, ctx: Contexte) -> str:
        return "complet" if ctx.complet else "sans_contexte"

    @torch.no_grad()
    def _probas(self, x: torch.Tensor, z: torch.Tensor, profil: str) -> np.ndarray:
        """Moyenne sur 3 graines × 4 retournements. x : (1,3,H,W), z : (n,20) → (n, classes)."""
        n = z.shape[0]
        xs = x.expand(n, -1, -1, -1)
        vues = [xs, xs.flip(3), xs.flip(2), xs.flip(2).flip(3)]
        out = torch.zeros(n, len(self.classes), device=self.device)
        with torch.autocast(device_type=self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"):
            for net in self.reseaux[profil]:
                for v in vues:
                    out += torch.softmax(net(v, z).float(), dim=1)
        return (out / (len(vues) * len(self.reseaux[profil]))).cpu().numpy()

    def _analyser(self, image: Image.Image, ctx: Contexte, rapport_cout: int | None) -> tuple[Resultat, torch.Tensor]:
        t0 = time.perf_counter()
        profil = self._profil(ctx)
        seuils, q_conf, origine = self.parametres(profil)
        R = int(rapport_cout or self.m["decision"]["rapport_defaut"])
        if str(R) not in seuils:
            raise ValueError(f"rapport de coût non calibré : {R} (disponibles : {list(seuils)})")
        seuil = float(seuils[str(R)])
        x = self.pretraiter(image)
        p = self._probas(x, self.encoder_contexte(ctx), profil)[0]
        score_hs = self._score_hors_sujet(x)
        # décision au coût
        autres = p.copy(); autres[self.mel] = -1
        k = self.mel if p[self.mel] >= seuil else int(autres.argmax())
        # ensemble conforme Mondrian (un seuil par classe) et abstention
        q = np.asarray(q_conf)
        ens = [self.classes[i] for i in np.flatnonzero(1.0 - p <= q)]
        traite = ens == [self.classes[k]]
        tri = triage(self.classes[k], traite, self.m["classes_malignes"], self.noms)
        avert: list[dict] = []
        if profil == "sans_contexte":
            avert.append({"code": "contexte_incomplet"})
        w, h = image.size
        if min(w, h) < 150:
            avert.append({"code": "faible_resolution", "largeur": w, "hauteur": h})
        res = Resultat(
            profil=profil, probabilites={c: float(v) for c, v in zip(self.classes, p)},
            decision=self.classes[k], p_melanome=float(p[self.mel]), seuil_melanome=seuil, rapport_cout=R,
            ensemble_conforme=ens, traite=bool(traite), statut=tri.statut, niveau=tri.niveau, titre=tri.titre,
            message=tri.message, modele=self.nom, version=self.version,
            duree_ms=int((time.perf_counter() - t0) * 1000), avertissements=avert,
            hors_sujet=bool(score_hs is not None and score_hs > self.hors_sujet["seuil"]),
            score_hors_sujet=None if score_hs is None else round(score_hs, 2), calibration=origine)
        return res, x

    @torch.no_grad()
    def _score_hors_sujet(self, x: torch.Tensor) -> float | None:
        """Atypie de l'image : distance de Mahalanobis (minimum sur les classes, covariance partagée) aux images
        d'entraînement, sur la dernière étape du réseau ou, si le paquet le prévoit, sur plusieurs étapes
        (log-distances centrées-réduites sur la validation, puis maximum)."""
        if self.hors_sujet is None:
            return None
        net = self.reseaux[self.hors_sujet["profil"]][0]
        if self._hs_etages is None:
            mu, prec = self._hs_couches[0]
            f = net.caracteristiques(x).float()
            diff = f[:, None, :] - mu[None]
            d2 = torch.einsum("nkd,de,nke->nk", diff, prec, diff)
            return float(d2.min())
        scores = []
        for f, (mu, prec) in zip(net.caracteristiques(x, self._hs_etages), self._hs_couches):
            diff = f.float()[:, None, :] - mu[None]
            scores.append(torch.einsum("nkd,de,nke->nk", diff, prec, diff).min(1).values)
        z = (torch.log(torch.stack(scores, 1)) - self._hs_norm[0]) / self._hs_norm[1]
        return float(z.max())

    @torch.no_grad()
    def _caracteristiques_lot(self, images: list[Image.Image], etages: tuple[int, ...] | None = None):
        net = self.reseaux[(self.hors_sujet or {}).get("profil", next(iter(self.reseaux)))][0]
        x = torch.cat([self.pretraiter(im) for im in images])
        if etages is None:
            return net.caracteristiques(x).float().cpu().numpy()
        return [f.float().cpu().numpy() for f in net.caracteristiques(x, etages)]

    def _gradcam(self, x: torch.Tensor, ctx: Contexte, classe: str) -> np.ndarray:
        profil, cible = self._profil(ctx), self.classes.index(classe)
        z = self.encoder_contexte(ctx)
        cams = []
        with torch.enable_grad():
            for net in self.reseaux[profil]:
                net.zero_grad(set_to_none=True)
                net(x, z, keep_map=True)[:, cible].sum().backward()
                a, g = net.feature_map, net.feature_map.grad
                cam = torch.relu((g.mean(dim=(2, 3), keepdim=True) * a).sum(1, keepdim=True))
                cam = torch.nn.functional.interpolate(cam, size=x.shape[-2:], mode="bilinear", align_corners=False)
                cams.append(cam[0, 0].detach().float().cpu().numpy())
                net.feature_map = None
        cam = np.mean(cams, axis=0)
        cam -= cam.min()
        return cam / max(cam.max(), 1e-8)

    def _et_si(self, image: Image.Image, ctx: Contexte, variable: str, valeurs: list) -> list[dict]:
        ctxs = []
        for v in valeurs:
            c = Contexte(ctx.age, ctx.sexe, ctx.localisation)
            setattr(c, variable, v)
            ctxs.append(c)
        x = self.pretraiter(image)
        z = torch.cat([self.encoder_contexte(c) for c in ctxs])
        p = self._probas(x, z, self._profil(ctx))
        return [{"valeur": v, "p_melanome": float(pi[self.mel])} for v, pi in zip(valeurs, p)]

    def _prechauffer(self, tailles_lot: tuple[int, ...]) -> float:
        t0 = time.perf_counter()
        x = self.pretraiter(Image.new("RGB", (64, 48), (180, 130, 120)))    # même chemin que les vraies images
        ctx = Contexte(50, "male", self.localisations[0])
        profil = next(iter(self.reseaux))
        for n in tailles_lot:
            self._probas(x, self.encoder_contexte(ctx).expand(n, -1).contiguous(), profil)
            if n == 1:
                self._gradcam(x, ctx, self.classes[0])          # Grad-CAM accompagne chaque analyse
                self._score_hors_sujet(x)                       # détection hors sujet (si disponible)
        return time.perf_counter() - t0

    def gradcam_png(self, image: Image.Image, cam: np.ndarray, opacite: float = 0.45, cote_max: int = 640) -> bytes:
        """Superpose la carte sur l'image d'ORIGINE (proportions conservées) pour qu'elle s'aligne avec elle."""
        im = ImageOps.exif_transpose(image).convert("RGB")
        echelle = min(1.0, cote_max / max(im.size))
        w, h = max(1, round(im.width * echelle)), max(1, round(im.height * echelle))
        base = np.asarray(im.resize((w, h), Image.LANCZOS), float)
        b = self.cadre(im)
        x0, y0, x1, y1 = (0, 0, w, h) if b is None else (round(b[0] * w / im.width), round(b[1] * h / im.height),
                                                         round(b[2] * w / im.width), round(b[3] * h / im.height))
        carte = np.zeros((h, w))                       # la carte couvre la partie analysée, nulle ailleurs
        carte[y0:y1, x0:x1] = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize(
            (max(1, x1 - x0), max(1, y1 - y0)), Image.BILINEAR), float)[:y1 - y0, :x1 - x0] / 255
        mix = (1 - opacite) * base + opacite * _colormap(carte)
        buf = io.BytesIO()
        Image.fromarray(mix.clip(0, 255).astype(np.uint8)).save(buf, "PNG")
        return buf.getvalue()

    def fiche(self) -> dict:
        """Manifest sans les chemins de fichiers (pour l'interface)."""
        m = json.loads(json.dumps(self.m))
        for prof in m["profils"].values():
            prof["poids"] = [{"sha256": w["sha256"][:12] + "…"} for w in prof["poids"]]
        m["peripherique"] = str(self.device)
        return m
