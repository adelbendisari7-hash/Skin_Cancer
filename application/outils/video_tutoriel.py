"""Tourne la vidéo tutoriel de l'application (navigateur piloté, curseur visible, sous-titres).

Prérequis : l'instance de démonstration tourne (lancer_demo.bat), Playwright installé, Google Chrome présent.
Usage : python outils/video_tutoriel.py   → docs/video/tutoriel_dermia.mp4

Le scénario crée un patient et une analyse dans l'instance de démonstration (pas dans les données réelles).
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from playwright.sync_api import Page, sync_playwright

URL = os.environ.get("DERMIA_URL", "http://127.0.0.1:8765")         # instance de démonstration
ICI = Path(__file__).resolve().parent
HAM = ICI.parents[2] / "HAM10000"
IMAGE = HAM / "HAM10000_images_part_1" / "ISIC_0026811.jpg"     # mélanome du jeu de test : visage, homme, 55 ans
ANNEE_NAISSANCE, LOCALISATION = "1971", "Visage"
SORTIE = ICI.parent / "docs" / "video" / "tutoriel_dermia.mp4"
L, H = 1280, 800

SUPERPOSITION = r"""
(() => {
  const css = `
  #tuto-curseur{position:fixed;left:-40px;top:-40px;width:24px;height:24px;margin:-12px 0 0 -12px;border-radius:50%;
    background:rgba(14,106,100,.22);border:2.5px solid #0e6a64;z-index:2147483647;pointer-events:none;
    transition:transform .12s, background .12s}
  #tuto-curseur.clic{transform:scale(.65);background:rgba(14,106,100,.6)}
  #tuto-legende{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);width:max-content;direction:ltr;max-width:min(980px,90vw);
    background:rgba(43,33,28,.95);color:#fff;font:700 21px/1.35 "Atkinson Hyperlegible Next","Segoe UI",sans-serif;
    padding:14px 24px 15px;border-radius:8px;z-index:2147483646;pointer-events:none;opacity:0;transition:opacity .3s;
    box-shadow:0 8px 28px rgba(0,0,0,.28)}
  #tuto-legende.visible{opacity:1}
  #tuto-legende small{display:block;font-weight:400;font-size:17px;opacity:.9;margin-top:3px}
  #tuto-legende b{color:#9fd8d0;font-weight:700;margin-right:8px}`;
  function installer() {
    if (document.getElementById('tuto-curseur') || !document.body) return;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement('div'); c.id = 'tuto-curseur'; document.body.appendChild(c);
    const l = document.createElement('div'); l.id = 'tuto-legende'; document.body.appendChild(l);
  }
  const curseur = () => document.getElementById('tuto-curseur');
  addEventListener('mousemove', e => { installer(); const c = curseur(); if (c) { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; } }, true);
  addEventListener('mousedown', () => curseur()?.classList.add('clic'), true);
  addEventListener('mouseup', () => curseur()?.classList.remove('clic'), true);
  window.__legende = (etape, titre, detail) => {
    installer(); const l = document.getElementById('tuto-legende');
    if (!titre) { l.classList.remove('visible'); return; }
    l.innerHTML = (etape ? '<b>' + etape + '</b>' : '') + titre + (detail ? '<small>' + detail + '</small>' : '');
    l.classList.add('visible');
  };
  if (document.readyState !== 'loading') installer(); else addEventListener('DOMContentLoaded', installer);
})();
"""

CARTE = """<!doctype html><html lang="fr"><meta charset="utf-8"><body style="margin:0;height:100vh;display:grid;place-items:center;
background:linear-gradient(180deg,#0f5f5a,#083d3a);color:#fff;font-family:'Segoe UI',system-ui,sans-serif">
<div style="text-align:center;max-width:820px;padding:0 40px">
<svg width="96" height="96" viewBox="-14 -14 28 28"><circle r="13" fill="#e8cfc6"/><circle r="9.6" fill="#2b211c"/>
<path d="M-4.5 -3 C-2.5 -6 3 -5.5 4.2 -2.4 C5.4 0.6 3.6 4 0.4 4.4 C-2.8 4.8 -5.6 2.6 -5.4 -0.4 Z" fill="#7a4a35"/>
<path d="M-2 -1.4 C-0.6 -3 2 -2.4 2.2 -0.6 C2.4 1.2 0.6 2.2 -0.8 1.8 C-2.2 1.4 -2.8 -0.2 -2 -1.4 Z" fill="#3b2219"/></svg>
<h1 style="font-size:46px;margin:22px 0 10px">{titre}</h1>
<p style="font-size:24px;line-height:1.45;color:#d5e8e6;margin:0">{texte}</p>
<p style="font-size:17px;color:#a9cdc9;margin-top:26px">{note}</p></div></body></html>"""


class Tournage:
    def __init__(self, page: Page):
        self.p = page

    def legende(self, etape: str, titre: str, detail: str = "", duree: float = 3.0):
        self.p.evaluate("([e, t, d]) => window.__legende(e, t, d)", [etape, titre, detail])
        self.p.wait_for_timeout(int(duree * 1000))

    def vers(self, cible, etapes: int = 22):
        cible.scroll_into_view_if_needed()
        b = cible.bounding_box()
        self.p.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=etapes)
        self.p.wait_for_timeout(220)

    def clic(self, cible, etapes: int = 22):
        self.vers(cible, etapes)
        self.p.mouse.down(); self.p.wait_for_timeout(90); self.p.mouse.up()
        self.p.wait_for_timeout(350)

    def taper(self, cible, texte: str):
        self.clic(cible)
        cible.press_sequentially(texte, delay=75)
        self.p.wait_for_timeout(250)

    def defiler(self, dy: int, pas: int = 18):
        for _ in range(pas):
            self.p.mouse.wheel(0, dy / pas)
            self.p.wait_for_timeout(22)
        self.p.wait_for_timeout(400)


def carte(page: Page, titre: str, texte: str, note: str, duree: float):
    page.set_content(CARTE.format(titre=titre, texte=texte, note=note))
    page.wait_for_timeout(int(duree * 1000))


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tuto_"))
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": L, "height": H}, device_scale_factor=1, locale="fr-FR",
                              record_video_dir=str(tmp), record_video_size={"width": L, "height": H})
        ctx.add_init_script(SUPERPOSITION)
        page = ctx.new_page()
        t = Tournage(page)

        carte(page, "dermIA", "Analyser une lésion cutanée, de la connexion au compte rendu",
              "Tutoriel de deux minutes, sur des données de démonstration", 4)

        # 1. Connexion ---------------------------------------------------------------------------
        page.goto(URL + "/connexion"); page.wait_for_load_state("networkidle")
        page.mouse.move(L * 0.7, H * 0.3)
        t.legende("Étape 1", "Se connecter", "Chaque médecin a son propre compte, créé par l'administrateur.", 1.5)
        t.taper(page.get_by_label("Identifiant"), "k.haddad")
        t.taper(page.get_by_label("Mot de passe", exact=True), "Demo2026medecin")
        t.clic(page.get_by_role("button", name="Se connecter"))
        page.wait_for_url(URL + "/"); page.wait_for_load_state("networkidle")

        # 2. File de travail ------------------------------------------------------------------------
        t.legende("Étape 2", "La file de travail", "Les analyses à valider, les suspicions de mélanome en premier.", 1.5)
        t.vers(page.locator("main li").first)
        t.vers(page.locator("main li").nth(3), 30)
        page.wait_for_timeout(1500)

        # 3. Nouvelle analyse -----------------------------------------------------------------------
        t.clic(page.locator("main").get_by_role("button", name="Nouvelle analyse"))
        page.wait_for_url("**/analyses/nouvelle")
        t.legende("Étape 3", "Nouvelle analyse", "Le patient, l'image, la localisation : l'analyse prend moins d'une seconde.", 2.5)
        t.clic(page.get_by_role("button", name="Nouveau patient"))
        t.legende("Étape 3", "Créer le patient", "Aucun nom n'est enregistré : le patient reçoit un code anonyme.", 0.8)
        t.taper(page.get_by_label("Année de naissance"), ANNEE_NAISSANCE)
        t.vers(page.get_by_label("Sexe").first)
        page.get_by_label("Sexe").first.select_option("male"); page.wait_for_timeout(500)
        t.taper(page.get_by_label("N° de dossier (facultatif)"), f"DOS-{datetime.now():%m%d%H%M}")   # unique à chaque tournage
        t.clic(page.get_by_role("button", name="Créer le patient"))
        page.wait_for_timeout(800)

        t.legende("Étape 3", "Ajouter l'image dermoscopique", "Glisser-déposer, ou bouton « Choisir une image ».", 0.6)
        t.vers(page.get_by_role("button", name="Choisir une image"))
        page.locator("input[type=file]").set_input_files(str(IMAGE))
        page.wait_for_timeout(2200)

        t.legende("Étape 3", "Indiquer la localisation", "Un clic sur la carte du corps (ou dans la liste).", 0.6)
        t.clic(page.locator(f'g[role=button][aria-label="{LOCALISATION}"]'), 30)
        page.wait_for_timeout(900)
        t.defiler(420)
        t.legende("Étape 3", "Vérifier le contexte", "L'âge et le sexe sont repris du dossier du patient.", 2.4)
        t.clic(page.get_by_role("button", name="Analyser la lésion"), 30)
        page.wait_for_url(re.compile(r".*/analyses/\d+\?nouvelle=1")); page.wait_for_load_state("networkidle")
        aid = int(page.url.split("/analyses/")[1].split("?")[0])
        a = page.request.get(f"{URL}/api/analyses/{aid}").json()

        # 4. Résultat --------------------------------------------------------------------------------
        page.mouse.move(L * 0.62, H * 0.32, steps=15)
        detail = {"urgent": "Avis dermatologique rapide recommandé.",
                  "renvoi": "L'IA n'est pas assez sûre : elle renvoie le cas au médecin.",
                  "eleve": "Lésion maligne ou pré-maligne probable : avis spécialisé.",
                  "faible": "Lésion bénigne probable."}[a["niveau"]]
        t.legende("Étape 4", f"Le résultat : {a['titre'].lower()}", detail, 4)
        t.clic(page.get_by_role("button", name="Zones regardées par l'IA"))
        t.legende("Étape 4", "Où l'IA a regardé", "Les zones qui ont le plus pesé dans sa proposition (Grad-CAM).", 3.2)
        t.clic(page.get_by_role("button", name="Image", exact=True))
        t.vers(page.get_by_text("Probabilités estimées"))
        t.legende("Étape 4", "Les probabilités", "Le trait rouge marque le seuil d'alerte mélanome, réglé pour ne pas en manquer.", 3.6)

        t.defiler(560)
        graphe = page.locator("svg[role=img]")
        b = graphe.bounding_box()
        page.mouse.move(b["x"] + 30, b["y"] + b["height"] * 0.5, steps=12)
        t.legende("Étape 4", "Et si le patient avait un autre âge ?", "Même image : on voit combien le contexte pèse sur le risque estimé.", 0.3)
        page.mouse.move(b["x"] + b["width"] - 20, b["y"] + b["height"] * 0.5, steps=70)
        page.wait_for_timeout(900)
        t.clic(page.get_by_role("button", name="Localisation", exact=True))
        page.wait_for_selector("text=(actuelle)", timeout=30000)
        t.legende("Étape 4", "… ou une autre localisation", "", 2.8)

        # 5. Validation médicale ---------------------------------------------------------------------
        t.legende("Étape 5", "Le médecin valide ou corrige", "Sa décision est enregistrée dans le dossier et dans le journal d'audit.", 0.6)
        t.clic(page.get_by_role("radio", name="Je confirme"))
        t.taper(page.get_by_label("Commentaire (facultatif)"), "Exérèse programmée.")
        t.clic(page.get_by_role("button", name="Enregistrer la validation"))
        page.wait_for_timeout(1800)

        # 6. Compte rendu PDF ------------------------------------------------------------------------
        t.defiler(-900)
        t.vers(page.get_by_role("button", name="Compte rendu PDF"))
        t.legende("Étape 6", "Le compte rendu PDF", "Prêt à imprimer, à signer et à joindre au dossier.", 1.2)
        pdf = page.request.get(f"{URL}/api/analyses/{aid}/compte-rendu.pdf").body()
        png = pymupdf.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=96).tobytes("png")
        page.set_content(f"""<body style="margin:0;background:#5e534d;display:flex;justify-content:center;align-items:flex-start;
            height:100vh;overflow:hidden"><img id="cr" src="data:image/png;base64,{base64.b64encode(png).decode()}"
            style="width:640px;margin-top:24px;box-shadow:0 10px 40px rgba(0,0,0,.4);transition:transform 6s ease-in-out"></body>""")
        page.add_script_tag(content=SUPERPOSITION)
        t.legende("Étape 6", "Le compte rendu PDF", "Orientation, image, zones regardées, probabilités, validation et signature.", 0.5)
        page.evaluate("document.getElementById('cr').style.transform='translateY(-330px)'")
        page.wait_for_timeout(5600)

        # 7. Dossier patient et fiche du modèle ------------------------------------------------------
        page.goto(f"{URL}/patients/{a['patient_id']}"); page.wait_for_load_state("networkidle")
        page.mouse.move(L * 0.55, H * 0.45, steps=10)
        t.legende("Étape 7", "Le dossier du patient", "Il garde l'historique de toutes ses lésions analysées.", 3.2)
        t.clic(page.get_by_role("link", name="Modèle d'IA"))
        page.wait_for_load_state("networkidle")
        t.legende("Étape 8", "La fiche du modèle", "Performances mesurées, limites connues, statut : tout est affiché, rien n'est caché.", 1.5)
        t.defiler(520, 30)
        page.wait_for_timeout(1800)

        carte(page, "C'est tout.", "Pour commencer : double-cliquez sur <b>lancer_application.bat</b>,<br>"
              "créez le compte administrateur, puis les comptes des médecins.",
              "Outil d'aide à la décision, pas un dispositif médical. Modèle de démonstration à usage non commercial.", 4.5)
        video = page.video.path()
        ctx.close(); nav.close()

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    webm = SORTIE.with_suffix(".webm")
    shutil.copy(video, webm)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "22", "-preset", "medium", "-movflags", "+faststart", "-r", "25", str(SORTIE)], check=True)
    webm.unlink()
    print("Vidéo :", SORTIE)


if __name__ == "__main__":
    main()
