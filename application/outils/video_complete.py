"""Tourne la vidéo de présentation complète de l'application (version 2), curseur visible et sous-titres.

Prérequis : l'instance de démonstration v2 tourne (outils/creer_demo.py puis lancer_demo.bat),
Playwright et Google Chrome installés, ffmpeg disponible.
Usage : python outils/video_complete.py [--url http://127.0.0.1:8765] → docs/video/visite_complete_dermia.mp4

Le scénario agit sur l'instance de démonstration (nouvelle analyse, validation, recalibrage appliqué,
sauvegarde restaurée) : ne jamais le lancer sur des données réelles.
"""
from __future__ import annotations

import argparse
import base64
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw
from playwright.sync_api import Page, sync_playwright

from video_tutoriel import SUPERPOSITION, Tournage, carte

ICI = Path(__file__).resolve().parent
HAM = ICI.parents[2] / "HAM10000"
IMAGE = HAM / "HAM10000_images_part_1" / "ISIC_0026811.jpg"     # mélanome du jeu de test
SORTIE = ICI.parent / "docs" / "video" / "visite_complete_dermia.mp4"
L, H = 1280, 800


def capture_tableur(chemin: Path) -> None:
    im = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 900, 56], fill=(33, 115, 70))
    for i in range(16):
        d.line([(0, 90 + 30 * i), (900, 90 + 30 * i)], fill=(210, 210, 210))
    for j in range(6):
        d.line([(60 + 140 * j, 60), (60 + 140 * j, 600)], fill=(210, 210, 210))
        for i in range(15):
            d.rectangle([70 + 140 * j, 98 + 30 * i, 70 + 140 * j + (37 * (i + j)) % 100, 108 + 30 * i], fill=(40, 40, 40))
    im.save(chemin)


def montrer_pdf(page: Page, t: Tournage, pdf: bytes, titre: str, detail: str) -> None:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pngs = [base64.b64encode(p.get_pixmap(dpi=96).tobytes("png")).decode() for p in doc][:2]
    imgs = "".join(f'<img src="data:image/png;base64,{b}" style="width:600px;box-shadow:0 10px 40px rgba(0,0,0,.4);margin:0 14px">'
                   for b in pngs)
    page.set_content(f"""<body style="margin:0;background:#5e534d;height:100vh;overflow:hidden">
        <div id="cr" style="display:flex;justify-content:center;align-items:flex-start;padding-top:24px;
        transition:transform 7s ease-in-out">{imgs}</div></body>""")
    page.add_script_tag(content=SUPERPOSITION)
    t.legende("", titre, detail, 0.6)
    page.evaluate("document.getElementById('cr').style.transform='translateY(-300px)'")
    page.wait_for_timeout(7200)


def segments_utiles(video: Path, seuil_s: float = 12.0, debut_s: float = 5.0, fin_s: float = 4.0) -> list[tuple]:
    """Écrans figés trop longs (attente d'une restauration volumineuse…) : on garde le début et la fin."""
    sortie = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "freezedetect=n=0.003:d=6",
                             "-map", "0:v", "-f", "null", "-"], capture_output=True, text=True).stderr
    debuts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", sortie)]
    fins = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", sortie)]
    garder, t = [], 0.0
    for a, b in zip(debuts, fins):
        if b - a > seuil_s:
            garder.append((round(t, 2), round(a + debut_s, 2)))
            t = b - fin_s
    garder.append((round(t, 2), None))
    return [(a, b if b is not None else 10_000) for a, b in garder]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    URL = ap.parse_args().url
    tmp = Path(tempfile.mkdtemp(prefix="visite_"))
    tableur = tmp / "capture_tableur.png"
    capture_tableur(tableur)
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": L, "height": H}, device_scale_factor=1, locale="fr-FR",
                              record_video_dir=str(tmp), record_video_size={"width": L, "height": H})
        ctx.add_init_script("try { localStorage.setItem('dermia.langue', 'fr') } catch (e) {}")
        ctx.add_init_script(SUPERPOSITION)
        page = ctx.new_page()
        t = Tournage(page)
        attendre = lambda: page.wait_for_load_state("networkidle")        # noqa: E731

        carte(page, "DermIA Prudence 2.0", "Visite complète de l'application",
              "Suivi des lésions · critères ABCD · refus des images hors sujet · recalibrage local · "
              "sauvegarde en un clic · français, anglais et arabe — données de démonstration", 5)

        # 1. Langues et connexion ---------------------------------------------------------------------
        page.goto(URL + "/connexion"); attendre()
        page.mouse.move(L * 0.7, H * 0.4)
        t.legende("1", "Trois langues", "Français, anglais et arabe ; l'arabe s'affiche de droite à gauche.", 1.0)
        t.clic(page.get_by_role("button", name="English")); page.wait_for_timeout(1500)
        t.clic(page.get_by_role("button", name="العربية")); page.wait_for_timeout(2200)
        t.clic(page.get_by_role("button", name="Français")); page.wait_for_timeout(900)
        t.legende("1", "Connexion du médecin", "Chaque utilisateur a son compte ; tout est tracé dans le journal d'audit.", 0.6)
        t.taper(page.get_by_label("Identifiant"), "k.haddad")
        t.taper(page.get_by_label("Mot de passe", exact=True), "Demo2026medecin")
        t.clic(page.get_by_role("button", name="Se connecter"))
        page.wait_for_url(URL + "/"); attendre()

        # 2. File de travail ----------------------------------------------------------------------------
        t.legende("2", "La file de travail", "Les cas les plus graves d'abord ; le badge « Évolution » signale une lésion qui a changé.", 1.2)
        badge = page.locator("main li").filter(has_text="Évolution").first
        t.vers(badge, 30)
        page.wait_for_timeout(1500)
        t.clic(badge)
        page.wait_for_url(re.compile(r".*/analyses/\d+")); attendre()

        # 3. Résultat : orientation, ABCD, évolution -----------------------------------------------------
        page.mouse.move(L * 0.65, H * 0.35, steps=15)
        t.legende("3", "Le résultat", "Orientation, probabilités, et un niveau de confiance garanti : l'IA s'abstient quand elle doute.", 3.5)
        t.clic(page.get_by_role("button", name="Contour ABCD"))
        t.legende("3", "Critères ABCD automatiques", "Contour de la lésion et axes de symétrie, détectés sans intervention.", 3.0)
        t.vers(page.get_by_role("heading", name="Critères ABCD (indicatifs)"))
        t.defiler(380)
        t.legende("3", "Asymétrie, bords, couleurs, diamètre", "Des indicateurs présentés honnêtement : leur pouvoir discriminant mesuré est modeste.", 3.8)
        t.vers(page.get_by_role("heading", name="Évolution de la lésion"))
        t.legende("4", "Suivi dans le temps", "Comparée à l'examen précédent : probabilité de mélanome, orientation, nouvelles couleurs…", 3.8)

        # 4. Page de la lésion suivie --------------------------------------------------------------------
        t.clic(page.get_by_role("link", name="Comparer les images"))
        page.wait_for_url(re.compile(r".*/lesions/\d+.*")); attendre()
        page.mouse.move(L * 0.6, H * 0.45, steps=12)
        t.legende("4", "La lésion suivie", "Chronologie des examens et courbe de la probabilité de mélanome.", 3.4)
        t.defiler(560, 26)
        t.legende("4", "Avant / après, côte à côte", "Images, contours ABCD et indicateurs : le médecin juge l'évolution.", 1.2)
        for bouton in page.get_by_role("button", name="Contour ABCD").all()[:2]:
            t.clic(bouton)
        page.wait_for_timeout(1800)
        t.defiler(420)
        page.wait_for_timeout(2400)
        t.defiler(-1400, 24)

        # 5. Nouvelle image de la lésion : image hors sujet refusée ---------------------------------------
        t.clic(page.get_by_role("button", name="Nouvelle image de cette lésion"))
        page.wait_for_url(re.compile(r".*/analyses/nouvelle.*")); attendre()
        page.wait_for_timeout(800)
        t.legende("5", "Nouvelle image de la même lésion", "Le patient et la lésion sont déjà choisis.", 2.4)
        t.vers(page.get_by_role("button", name="Choisir une image"))
        t.legende("5", "Et si l'image n'est pas une dermoscopie ?", "Ici, une capture d'écran choisie par erreur.", 0.6)
        page.locator("input[type=file]").set_input_files(str(tableur))
        page.wait_for_timeout(1600)
        t.clic(page.get_by_role("button", name="Analyser la lésion"), 30)
        page.get_by_role("dialog").wait_for(timeout=30000)
        t.legende("5", "Image refusée", "Elle ne ressemble pas aux images dermoscopiques d'entraînement : le résultat ne serait pas fiable.", 4.2)
        with page.expect_file_chooser() as choix:
            t.clic(page.get_by_role("button", name="Choisir une autre image"))
        choix.value.set_files(str(IMAGE))
        page.wait_for_timeout(1800)
        t.legende("5", "Avec la bonne image", "", 0.4)
        t.clic(page.get_by_role("button", name="Analyser la lésion"), 30)
        page.wait_for_url(re.compile(r".*/analyses/\d+\?nouvelle=1")); attendre()
        aid = int(page.url.split("/analyses/")[1].split("?")[0])
        page.mouse.move(L * 0.65, H * 0.3, steps=15)
        t.legende("5", "Nouveau résultat", "Comparé automatiquement à l'examen précédent de la même lésion.", 3.0)
        t.vers(page.get_by_role("heading", name="Évolution de la lésion"))
        t.defiler(160)
        page.wait_for_timeout(2600)

        # 6. Validation avec histologie ------------------------------------------------------------------
        t.vers(page.get_by_role("heading", name="Validation médicale"))
        t.legende("6", "Validation médicale", "Le médecin confirme ou corrige, et peut signaler une confirmation histologique.", 0.6)
        t.clic(page.get_by_role("radio", name="Je confirme"))
        t.clic(page.get_by_text("Diagnostic confirmé par histologie (anatomopathologie)"))
        t.taper(page.get_by_label("Commentaire (facultatif)"), "Exérèse : mélanome confirmé.")
        t.clic(page.get_by_role("button", name="Enregistrer la validation"))
        page.wait_for_timeout(1500)
        t.legende("6", "Ces validations servent au recalibrage", "Les cas confirmés par histologie sont les plus fiables.", 2.4)

        # 7. Compte rendu PDF en arabe -------------------------------------------------------------------
        t.defiler(-1600, 20)
        t.vers(page.get_by_label("Langue du compte rendu"))
        t.legende("7", "Compte rendu PDF en trois langues", "Ici en arabe, avec les critères ABCD et l'évolution.", 0.8)
        page.get_by_label("Langue du compte rendu").select_option("ar"); page.wait_for_timeout(900)
        pdf = page.request.get(f"{URL}/api/analyses/{aid}/compte-rendu.pdf?langue=ar").body()
        montrer_pdf(page, t, pdf, "Compte rendu en arabe", "Mise en page de droite à gauche, police arabe intégrée.")

        # 8. L'interface en arabe et en anglais ----------------------------------------------------------
        page.goto(f"{URL}/analyses/{aid}"); attendre()
        t.legende("8", "Toute l'interface change de langue", "Un clic, sans recharger les données.", 0.6)
        t.clic(page.get_by_role("button", name="العربية"))
        page.wait_for_timeout(1200); attendre()
        page.mouse.move(L * 0.45, H * 0.35, steps=12)
        page.wait_for_timeout(2200)
        t.defiler(500); page.wait_for_timeout(1600); t.defiler(-500)
        t.clic(page.get_by_role("button", name="English"))
        page.wait_for_timeout(2600)
        t.clic(page.get_by_role("button", name="Français"))
        page.wait_for_timeout(900)

        # 9. Administration : recalibrage local ----------------------------------------------------------
        t.clic(page.get_by_role("button", name="Se déconnecter").last)
        page.wait_for_url(re.compile(r".*/connexion")); attendre()
        t.legende("9", "Côté administrateur", "", 0.4)
        t.taper(page.get_by_label("Identifiant"), "admin")
        t.taper(page.get_by_label("Mot de passe", exact=True), "Demo2026admin")
        t.clic(page.get_by_role("button", name="Se connecter"))
        page.wait_for_url(URL + "/"); attendre()
        t.clic(page.get_by_role("link", name="Administration"))
        attendre()
        t.clic(page.get_by_role("tab", name="Recalibrage")); attendre()
        t.legende("9", "Recalibrage local", "Réajuste les seuils de l'IA sur les cas validés de l'établissement, sans réentraîner le réseau.", 3.8)
        t.defiler(420)
        t.legende("9", "Une proposition évaluée honnêtement", "Effet estimé par validation croisée, à comparer aux seuils d'origine.", 3.6)
        t.vers(page.get_by_text(re.compile("^Recommandation")).first)
        t.legende("9", "Et une recommandation prudente", "Ici, aucune dérive : appliquer dégraderait la sécurité mélanome, l'outil conseille de garder les seuils.", 4.4)
        t.legende("9", "L'administrateur décide", "Avec un autre dermoscope (expérience simulée), le recalibrage recommandé réduit presque de moitié les mélanomes manqués.", 4.0)

        # 10. Sauvegarde et restauration -----------------------------------------------------------------
        t.defiler(-1200, 16)
        t.clic(page.get_by_role("tab", name="Sauvegardes")); attendre()
        t.legende("10", "Sauvegarde en un clic", "Base de données et images dans une seule archive vérifiée ; sauvegarde automatique chaque jour.", 0.6)
        t.clic(page.get_by_role("button", name="Sauvegarder maintenant"))
        page.get_by_text("Sauvegarde créée").wait_for(timeout=120000)
        page.wait_for_timeout(2200)
        t.legende("10", "Restauration en un clic", "Une sauvegarde de sécurité est faite juste avant ; tout le monde se reconnecte ensuite.", 0.6)
        t.clic(page.locator("main li").first.get_by_role("button", name="Restaurer"))
        page.wait_for_timeout(2600)
        t.clic(page.get_by_role("dialog").get_by_role("button", name="Restaurer"))
        page.wait_for_url(re.compile(r".*/connexion"), timeout=180000); attendre()
        t.legende("10", "Données restaurées", "L'application demande de se reconnecter.", 3.0)
        t.taper(page.get_by_label("Identifiant"), "admin")
        t.taper(page.get_by_label("Mot de passe", exact=True), "Demo2026admin")
        t.clic(page.get_by_role("button", name="Se connecter"))
        page.wait_for_url(URL + "/"); attendre()

        # 11. Réglages et journal ------------------------------------------------------------------------
        page.goto(URL + "/administration?onglet=comptes"); attendre()
        t.vers(page.get_by_label("Largeur du champ du dermoscope (mm)"))
        t.legende("11", "Réglages", "Largeur du champ du dermoscope : elle permet de mesurer le diamètre (critère D).", 3.2)
        t.clic(page.get_by_role("tab", name="Journal d'audit")); attendre()
        page.mouse.move(L * 0.5, H * 0.45, steps=12)
        t.legende("11", "Journal d'audit", "Images refusées, analyses forcées, recalibrages, sauvegardes : tout est tracé.", 3.6)

        # 12. Fiche du modèle ----------------------------------------------------------------------------
        t.clic(page.get_by_role("link", name="Modèle d'IA")); attendre()
        t.legende("12", "La fiche du modèle", "Architecture, performances mesurées une seule fois sur le test, limites connues.", 2.6)
        t.defiler(900, 30)
        t.vers(page.get_by_role("heading", name="Images hors sujet"))
        t.legende("12", "Tout est mesuré et affiché", "Y compris ce que l'outil ne sait pas faire.", 3.2)

        carte(page, "DermIA Prudence 2.0", "Démarrer : double-clic sur <b>lancer_application.bat</b>.<br>"
              "Démonstration : <b>lancer_demo.bat</b>.",
              "Outil d'aide à la décision, pas un dispositif médical. Modèle de démonstration entraîné sur HAM10000 "
              "(licence CC BY-NC 4.0) : usage non commercial.", 5)
        video = page.video.path()
        ctx.close(); nav.close()

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    webm = SORTIE.with_suffix(".webm")
    shutil.copy(video, webm)
    garder = segments_utiles(webm)
    filtres = ";".join(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[s{i}]" for i, (a, b) in enumerate(garder))
    filtres += ";" + "".join(f"[s{i}]" for i in range(len(garder))) + f"concat=n={len(garder)}:v=1[o]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-filter_complex", filtres, "-map", "[o]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "medium", "-movflags", "+faststart",
                    "-r", "25", str(SORTIE)], check=True)
    webm.unlink()
    print("Vidéo :", SORTIE, "| segments conservés :", garder)


if __name__ == "__main__":
    main()
