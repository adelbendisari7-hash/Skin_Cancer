"""Captures d'écran de tous les écrans, en français, anglais et arabe (revue visuelle avant livraison).

Usage : python outils/captures_revue.py [--url http://127.0.0.1:8765] [--sortie docs/captures/v2]
Prérequis : instance de démonstration lancée (comptes admin / Demo2026admin).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ICI = Path(__file__).resolve().parent
LANGUES = ("fr", "en", "ar")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--sortie", default=str(ICI.parent / "docs" / "captures" / "v2"))
    ap.add_argument("--langues", default=",".join(LANGUES))
    args = ap.parse_args()
    url, sortie = args.url, Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="chrome", headless=True)
        for lg in args.langues.split(","):
            ctx = nav.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            ctx.add_init_script(f"try {{ localStorage.setItem('dermia.langue', '{lg}') }} catch (e) {{}}")
            page = ctx.new_page()
            page.goto(url + "/connexion")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(sortie / f"{lg}_01_connexion.png"))
            r = page.request.post(url + "/api/connexion", data={"identifiant": "admin", "mot_de_passe": "Demo2026admin"})
            assert r.ok, r.text()
            analyses = page.request.get(url + "/api/analyses?taille=200").json()["elements"]
            # lésion suivie mise en scène : la plus inquiétante des analyses avec une évolution notable
            suivi = max((a for a in analyses if (a.get("evolution") or {}).get("notable")), key=lambda a: a["p_melanome"])
            ecrans = [
                ("02_file_de_travail", "/"),
                ("03_nouvelle_analyse", f"/analyses/nouvelle?patient={suivi['patient_id']}&lesion={suivi['lesion_id']}"),
                ("04_resultat", f"/analyses/{suivi['id']}"),
                ("05_lesion_suivie", f"/lesions/{suivi['lesion_id']}"),
                ("06_patient", f"/patients/{suivi['patient_id']}"),
                ("07_patients", "/patients"),
                ("08_analyses", "/analyses"),
                ("09_admin_comptes", "/administration?onglet=comptes"),
                ("10_admin_recalibrage", "/administration?onglet=recalibrage"),
                ("11_admin_sauvegardes", "/administration?onglet=sauvegardes"),
                ("12_admin_journal", "/administration?onglet=journal"),
                ("13_modele", "/modele"),
            ]
            for nom, chemin in ecrans:
                page.goto(url + chemin)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(500)
                page.screenshot(path=str(sortie / f"{lg}_{nom}.png"), full_page=True)
            # vue « contour ABCD » de l'oculaire
            page.goto(url + f"/analyses/{suivi['id']}")
            page.wait_for_load_state("networkidle")
            page.locator("figure [role=group] button").nth(2).click()
            page.wait_for_timeout(600)
            page.screenshot(path=str(sortie / f"{lg}_04b_resultat_abcd.png"))
            # téléphone
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(url + f"/analyses/{suivi['id']}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(sortie / f"{lg}_14_mobile_resultat.png"), full_page=True)
            ctx.close()
            print("captures", lg, "ok")
        nav.close()


if __name__ == "__main__":
    main()
