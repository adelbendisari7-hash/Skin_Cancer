"""Vérifie que le moteur du navigateur reproduit le moteur Python sur de vraies images.

Lance la version Vercel construite dans un vrai Chrome (COOP/COEP comme en production), analyse des images du jeu de
test HAM10000 et des images hors sujet, puis compare aux résultats du moteur PyTorch (CPU, float32) : probabilités,
décision, orientation, ensemble conforme, refus hors sujet, critères ABCD. Écrit docs/verification_navigateur.json.

Usage : python outils/verifier_navigateur.py <dossier dist construit avec VITE_DEMO_STATIQUE=1> [--n 70]
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import io
import json
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ICI = Path(__file__).resolve().parent
APP = ICI.parent
sys.path.insert(0, str(APP / "backend"))
sys.path.insert(0, str(APP.parent))
from dermia.engine import Contexte, Moteur, abcd  # noqa: E402

BUNDLE = APP / "modeles" / "ham10000-m5-v2"


class Serveur(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *a):
        pass

    def do_GET(self):
        racine = Path(self.directory)
        if not (racine / self.path.split("?")[0].lstrip("/")).is_file():
            self.path = "/index.html"
        super().do_GET()


def document() -> bytes:
    im = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 900, 56], fill=(33, 115, 70))
    for i in range(15):
        d.rectangle([70, 98 + 30 * i, 500 + (37 * i) % 300, 108 + 30 * i], fill=(40, 40, 40))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--n", type=int, default=70)
    args = ap.parse_args()
    from src.data import get_split
    df = get_split()
    test = df[df.split == "test"].copy()
    par_classe = max(3, args.n // 7)
    cas = test.groupby("dx", group_keys=False).apply(lambda g: g.sample(min(len(g), par_classe), random_state=0)).head(args.n + 7)

    moteur = Moteur(BUNDLE, device="cpu")
    attendus = []
    for _, r in cas.iterrows():
        age = None if np.isnan(r.age) else float(r.age)
        ctx = Contexte(age, r.sex, r.localization)
        im = Image.open(r.path)
        res, _ = moteur.analyser(im, ctx)
        m = abcd.publiable(abcd.mesurer(im, 15.0))
        attendus.append({"image": r.image_id, "chemin": str(r.path), "ctx": {"age": age, "sexe": r.sex, "localisation": r.localization},
                         "res": res, "abcd": m})
    print(f"Moteur Python : {len(attendus)} images")

    gestion = functools.partial(Serveur, directory=args.dist)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 4180), gestion)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ecarts, temps, lignes, reseau = [], [], [], []
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="chrome", headless=True)
        p = nav.new_context(viewport={"width": 1280, "height": 800}).new_page()
        p.on("request", lambda q: reseau.append((q.method, q.url)) if q.method != "GET" else None)
        p.on("pageerror", lambda e: print("erreur page :", e))
        p.goto("http://127.0.0.1:4180/connexion")
        p.wait_for_load_state("networkidle")
        print("crossOriginIsolated :", p.evaluate("crossOriginIsolated"), "| fils :", p.evaluate("navigator.hardwareConcurrency"))
        p.evaluate("async () => { window.m = await window.__dermiaTest() }")
        appel = """async ([b64, type, ctx, forcer, cle]) => {
          const o = atob(b64), a = new Uint8Array(o.length);
          for (let i = 0; i < o.length; i++) a[i] = o.charCodeAt(i);
          const blob = new Blob([a], {type});
          const t0 = performance.now();
          const r = await window.m.analyserImage(blob, ctx, 10, forcer, cle);
          const d = performance.now() - t0;
          const ab = await window.m.abcdImage(blob, 15);
          delete r.images;
          return {...r, ms: d, abcd15: ab};
        }"""
        for i, a in enumerate(attendus):
            b = base64.b64encode(Path(a["chemin"]).read_bytes()).decode()
            r = p.evaluate(appel, [b, "image/jpeg", a["ctx"], True, f"t{i}"])
            e = a["res"]
            dp = max(abs(r["probabilites"][c] - e.probabilites[c]) for c in moteur.classes)
            ecarts.append(dp)
            temps.append(r["ms"])
            ab, ae = r["abcd15"], a["abcd"]
            lignes.append({
                "image": a["image"], "ecart_p": dp, "decision": r["decision"] == e.decision, "statut": r["statut"] == e.statut,
                "ensemble": sorted(r["ensemble_conforme"]) == sorted(e.ensemble_conforme), "profil": r["profil"] == e.profil,
                "hors_sujet": r["hors_sujet"] == e.hors_sujet, "ecart_score_hs": abs(r["score_hors_sujet"] - e.score_hors_sujet),
                "A": (ab["A"] or {}).get("score") == (ae["A"] or {}).get("score"), "B": (ab["B"] or {}).get("score") == (ae["B"] or {}).get("score"),
                "C": sorted((ab["C"] or {}).get("couleurs", [])) == sorted((ae["C"] or {}).get("couleurs", [])),
                "ecart_D": abs(((ab["D"] or {}).get("mm") or 0) - ((ae["D"] or {}).get("mm") or 0)),
                "surface": abs(ab["surface_relative"] - ae["surface_relative"]),
            })
            if (i + 1) % 20 == 0:
                print(f"  navigateur : {i + 1}/{len(attendus)}, écart max {max(ecarts):.4f}")
        b = base64.b64encode(document()).decode()
        hs = p.evaluate(appel, [b, "image/png", {"age": 40, "sexe": "male", "localisation": "back"}, False, "hs"])
        nav.close()
    srv.shutdown()

    t = {k: float(np.mean([l[k] for l in lignes])) for k in ("decision", "statut", "ensemble", "profil", "hors_sujet", "A", "B", "C")}
    bilan = {"n_images": len(lignes), "ecart_probabilite_max": float(np.max(ecarts)), "ecart_probabilite_median": float(np.median(ecarts)),
             "accord": {k: round(v, 4) for k, v in t.items()}, "ecart_score_hors_sujet_max": float(max(l["ecart_score_hs"] for l in lignes)),
             "ecart_diametre_mm_max": float(max(l["ecart_D"] for l in lignes)), "ecart_surface_max": float(max(l["surface"] for l in lignes)),
             "temps_ms_median": float(np.median(temps[1:])), "document_refuse": bool(hs.get("refus")),
             "requetes_non_GET_pendant_les_analyses": len(reseau)}
    print(json.dumps(bilan, ensure_ascii=False, indent=1))
    pires = sorted(lignes, key=lambda l: -l["ecart_p"])[:3]
    print("pires :", [(l["image"], round(l["ecart_p"], 4)) for l in pires])
    for k in ("A", "B", "C", "decision"):
        print(k, "différents :", [l["image"] for l in lignes if not l[k]][:6])
    (APP / "docs" / "verification_navigateur.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
