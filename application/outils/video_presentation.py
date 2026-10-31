"""Tourne la vidéo de présentation aux clients sur le site en ligne, avec la voix off de narration_presentation.py.

Prérequis : outils/narration_presentation.py exécuté (docs/video/voix), Playwright, Google Chrome, ffmpeg.
Usage : python outils/video_presentation.py [--url https://dermia-prudence.vercel.app] → docs/video/presentation_dermia.mp4

Chaque scène dure au moins le temps de sa voix ; l'heure de début de chaque scène sert à placer la voix au montage.
Le tournage ne laisse rien sur le site : les analyses restent dans le navigateur de tournage, qui est jeté à la fin.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pymupdf
from playwright.sync_api import Page, sync_playwright

from video_complete import capture_tableur
from video_tutoriel import SUPERPOSITION, Tournage

ICI = Path(__file__).resolve().parent
HAM = ICI.parents[2] / "HAM10000"
IMAGE = HAM / "HAM10000_images_part_1" / "ISIC_0026811.jpg"     # mélanome du jeu de test : visage, homme
VOIX = ICI.parent / "docs" / "video" / "voix"
SORTIE = ICI.parent / "docs" / "video" / "presentation_dermia.mp4"
L, H = 1280, 800
CAS_INCERTAIN, LESION_SUIVIE, CAS_PDF = 430, 419, 419           # cas calculés à l'avance de la démonstration

LOGO = """<svg width="84" height="84" viewBox="-14 -14 28 28"><circle r="13" fill="#e8cfc6"/><circle r="9.6" fill="#2b211c"/>
<path d="M-4.5 -3 C-2.5 -6 3 -5.5 4.2 -2.4 C5.4 0.6 3.6 4 0.4 4.4 C-2.8 4.8 -5.6 2.6 -5.4 -0.4 Z" fill="#7a4a35"/>
<path d="M-2 -1.4 C-0.6 -3 2 -2.4 2.2 -0.6 C2.4 1.2 0.6 2.2 -0.8 1.8 C-2.2 1.4 -2.8 -0.2 -2 -1.4 Z" fill="#3b2219"/></svg>"""

CARTE = """<!doctype html><html lang="fr"><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:linear-gradient(180deg,#0f5f5a,#083d3a);color:#fff;
  font-family:'Segoe UI',system-ui,sans-serif;text-align:center}
main{max-width:1040px;padding:0 48px}
h1{font-size:50px;margin:20px 0 12px;font-weight:700}
p{font-size:26px;line-height:1.45;color:#d5e8e6;margin:0}
.lien{font-size:34px;font-weight:700;color:#fff;margin:6px 0 30px}
.note{font-size:18px;color:#b4d4d0;margin-top:10px}
.chiffres{display:grid;grid-template-columns:repeat(3,1fr);gap:34px;margin:34px 0 26px}
.chiffres b{display:block;font-size:66px;font-weight:700;color:#fff;line-height:1.1}
.chiffres span{display:block;font-size:20px;line-height:1.35;color:#d5e8e6;margin-top:10px}
.v{opacity:0;animation:v .7s ease-out forwards}
@keyframes v{to{opacity:1}}
</style><body><main>{corps}</main></body></html>"""


class Chrono:
    """Note le début de chaque scène et la garde au moins aussi longue que sa voix."""

    def __init__(self, page: Page, durees: dict[str, float]):
        self.page, self.durees, self.marques, self.nom = page, durees, {}, ""

    def debut(self, nom: str) -> None:
        self.nom = nom
        self.marques[nom] = time.monotonic()

    def jusqua(self, s: float) -> None:
        reste = self.marques[self.nom] + s - time.monotonic()
        if reste > 0:
            self.page.wait_for_timeout(int(reste * 1000))

    def fin(self, marge: float = 0.45) -> None:
        self.jusqua(self.durees[self.nom] + marge)
        print(f"  {self.nom} : {time.monotonic() - self.marques[self.nom]:.1f} s (voix {self.durees[self.nom]:.1f} s)")


def carte(page: Page, corps: str) -> None:
    page.set_content(CARTE.replace("{corps}", corps))


def retard(s: float) -> str:
    return f'class="v" style="animation-delay:{s}s"'


def aller(page: Page, chemin: str) -> None:
    """Navigation interne, sans recharger la page (l'avis accepté et l'écran restent en place)."""
    page.evaluate("(c) => { history.pushState({}, '', c); dispatchEvent(new PopStateEvent('popstate')) }", chemin)
    page.wait_for_load_state("networkidle")


def attendre_image(page: Page) -> None:
    page.wait_for_function("(() => { const i = document.querySelector('figure img'); return i && i.complete && i.naturalWidth > 0 })()",
                           timeout=20000)


def montrer_comptes_rendus(page: Page, url: str, t: Tournage) -> None:
    imgs = ""
    for langue in ("fr", "en", "ar"):
        pdf = page.request.get(f"{url}/demo/pdf/{CAS_PDF}_{langue}.pdf").body()
        png = pymupdf.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=110).tobytes("png")
        imgs += (f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}" '
                 'style="width:392px;box-shadow:0 10px 34px rgba(0,0,0,.35);margin:0 8px">')
    page.set_content(f"""<body style="margin:0;background:#e6eeed;height:100vh;overflow:hidden">
        <div style="display:flex;justify-content:center;padding-top:28px">{imgs}</div></body>""")
    page.add_script_tag(content=SUPERPOSITION)
    t.legende("", "Compte rendu en trois langues", "Exemples issus d'un cas de démonstration.", 0)


def prechauffer(ctx, url: str) -> None:
    """Télécharge le modèle hors caméra : il reste dans le cache du navigateur pour la page filmée."""
    c = ctx.new_page()
    octets = []
    c.on("response", lambda r: octets.append(int(r.headers.get("content-length", 0))) if "/demo/modele/" in r.url or ".wasm" in r.url else None)
    c.goto(url + "/connexion")
    c.wait_for_load_state("networkidle")
    b = base64.b64encode(IMAGE.read_bytes()).decode()
    t0 = time.monotonic()
    c.evaluate("""async (b64) => {
      const m = await window.__dermiaTest();
      const o = atob(b64), a = new Uint8Array(o.length);
      for (let i = 0; i < o.length; i++) a[i] = o.charCodeAt(i);
      await m.analyserImage(new Blob([a], {type: 'image/jpeg'}), {age: 55, sexe: 'male', localisation: 'face'}, 10, true, 'chauffe');
    }""", b)
    print(f"Préchauffage : {sum(octets) / 1e6:.1f} Mo transférés, {time.monotonic() - t0:.1f} s")
    c.close()


def debut_carte(video: Path) -> float:
    """Instant de la vidéo où la première carte apparaît (la capture démarre sur une page blanche)."""
    sortie = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
    return float(re.search(r"pts_time:([\d.]+)", sortie).group(1))


def monter(video: Path, marques: dict[str, float], durees: dict[str, float], coupe: tuple[float, float]) -> None:
    t0 = debut_carte(video)
    origine = marques["intro"]
    a, b = coupe[0] - origine, coupe[1] - origine

    def place(t: float) -> float:
        r = t - origine
        return r - (b - a) if r >= b else r

    noms = list(marques)
    fin = place(marques[noms[-1]]) + durees[noms[-1]] + 1.6
    entrees = []
    filtres = [f"[0:v]trim=start={t0 + 0.02:.3f}:end={t0 + a:.3f},setpts=PTS-STARTPTS[v0]",
               f"[0:v]trim=start={t0 + b:.3f},setpts=PTS-STARTPTS[v1]", "[v0][v1]concat=n=2:v=1[image]"]
    for i, nom in enumerate(noms):
        entrees += ["-i", str(VOIX / f"{nom}.mp3")]
        filtres.append(f"[{i + 1}:a]adelay=delays={int(place(marques[nom]) * 1000)}:all=1[a{i}]")
        print(f"  {place(marques[nom]):6.1f} s  {nom}")
    filtres.append("".join(f"[a{i}]" for i in range(len(noms))) + f"amix=inputs={len(noms)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voix]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), *entrees,
                    "-filter_complex", ";".join(filtres), "-map", "[image]", "-map", "[voix]", "-t", f"{fin:.2f}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-r", "25",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(SORTIE)], check=True)
    print(f"Vidéo : {SORTIE} ({fin:.1f} s, {b - a:.1f} s d'attente coupées, carte à {t0:.2f} s dans la capture)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://dermia-prudence.vercel.app")
    URL = ap.parse_args().url.rstrip("/")
    durees = json.loads((VOIX / "durees.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="presentation_"))
    tableur = tmp / "capture_tableur.png"
    capture_tableur(tableur)

    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": L, "height": H}, device_scale_factor=1, locale="fr-FR",
                              record_video_dir=str(tmp), record_video_size={"width": L, "height": H})
        ctx.add_init_script(SUPERPOSITION)
        prechauffer(ctx, URL)
        page = ctx.new_page()
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        t, s = Tournage(page), Chrono(page, durees)
        attendre = lambda: page.wait_for_load_state("networkidle")        # noqa: E731

        # Ouverture ----------------------------------------------------------------------------------
        page.wait_for_timeout(300)
        carte(page, f"""{LOGO}<h1>dermIA</h1><p>Aide au tri des lésions cutanées</p>
            <p class="v" style="animation-delay:4.6s;margin-top:22px">L'outil oriente. Le médecin décide.</p>""")
        s.debut("intro")
        s.fin(0.7)

        # Connexion et langues -------------------------------------------------------------------------
        page.goto(URL + "/connexion"); attendre()
        s.debut("connexion")
        page.mouse.move(L * 0.7, H * 0.4)
        t.legende("", "Un simple navigateur", "Français, anglais ou arabe.", 0)
        t.clic(page.get_by_role("button", name="English"), 12); page.wait_for_timeout(450)
        t.clic(page.get_by_role("button", name="العربية"), 12); page.wait_for_timeout(650)
        t.clic(page.get_by_role("button", name="Français"), 12); page.wait_for_timeout(250)
        t.clic(page.get_by_role("button", name="Se connecter"), 14)
        page.wait_for_url(URL + "/"); attendre()
        s.fin(0)

        # File de travail ------------------------------------------------------------------------------
        s.debut("file")
        t.legende("", "La file de travail", "Les cas les plus graves en tête ; un badge signale les lésions qui évoluent.", 0)
        t.vers(page.locator("main li").first, 26)
        page.wait_for_timeout(1500)
        t.vers(page.locator("main li").filter(has_text="Évolution").first, 34)
        s.fin()

        # Nouvelle analyse, jusqu'au calcul dans le navigateur ------------------------------------------
        s.debut("nouvelle")
        t.clic(page.get_by_role("link", name="Nouvelle analyse").first, 18)
        page.wait_for_url("**/analyses/nouvelle"); attendre()
        t.legende("", "Nouvelle analyse", "Le patient, l'image dermoscopique, la localisation.", 0)
        patient = page.locator("main ul li button").filter(has_text="Homme").first
        patient.wait_for(timeout=8000)
        t.clic(patient, 16)
        page.get_by_role("button", name="Changer de patient").wait_for()
        page.wait_for_timeout(500)
        t.vers(page.get_by_role("button", name="Choisir une image"), 18)
        page.locator("input[type=file]").set_input_files(str(IMAGE))
        page.wait_for_timeout(900)
        t.clic(page.locator('g[role=button][aria-label="Visage"]'), 24)
        s.jusqua(7.2)
        page.mouse.wheel(0, -2000)
        t.legende("", "Dans cette démonstration", "Le calcul se fait sur l'ordinateur : l'image n'est envoyée à aucun serveur.", 0)
        t.vers(page.get_by_text("Effacer mes analyses").locator("xpath=.."), 22)
        s.jusqua(10.6)
        t.clic(page.get_by_role("button", name="Analyser la lésion").last, 24)
        page.get_by_role("checkbox").wait_for()
        page.wait_for_timeout(350)
        t.clic(page.get_by_role("checkbox"), 14)
        t.clic(page.get_by_role("dialog").get_by_role("button", name="Analyser la lésion"), 12)
        s.fin(0)
        debut_attente = time.monotonic() + 1.6
        page.wait_for_url(re.compile(r".*/analyses/\d+\?nouvelle=1"), timeout=60000); attendre()
        attendre_image(page)
        aid = page.url.split("/analyses/")[1].split("?")[0]

        # Résultat -------------------------------------------------------------------------------------
        page.get_by_text("Suspicion de mélanome").first.wait_for(timeout=5000)      # la voix l'annonce
        coupe = (debut_attente, max(debut_attente, time.monotonic() - 0.4))     # l'attente est coupée au montage
        s.debut("resultat")
        page.mouse.move(L * 0.72, H * 0.3, steps=14)
        t.legende("", "Une orientation claire", "Sept diagnostics, et un seuil d'alerte mélanome.", 0)
        s.jusqua(5.5)
        t.vers(page.get_by_text("Probabilités estimées"), 24)
        page.mouse.move(L * 0.7, H * 0.72, steps=20)
        s.fin()

        # Explication ----------------------------------------------------------------------------------
        s.debut("explication")
        t.clic(page.get_by_role("button", name="Zones regardées par l'IA"), 20)
        t.legende("", "Où l'IA a regardé", "Les zones qui ont le plus pesé dans sa proposition.", 0)
        s.jusqua(3.6)
        t.clic(page.get_by_role("button", name="Contour ABCD"), 14)
        t.legende("", "Critères ABCD", "Mesurés automatiquement sur le contour de la lésion.", 0)
        s.jusqua(6.2)
        t.defiler(620, 24)
        s.fin()

        # Abstention -----------------------------------------------------------------------------------
        aller(page, f"/analyses/{CAS_INCERTAIN}")
        attendre_image(page)
        page.evaluate("scrollTo(0, 0)")
        page.get_by_text("l'IA s'abstient").first.wait_for(timeout=5000)
        s.debut("prudence")
        page.mouse.move(L * 0.72, H * 0.33, steps=16)
        t.legende("", "L'IA sait s'abstenir", "Le cas incertain revient au médecin.", 0)
        s.fin(0.3)

        # Image hors sujet -----------------------------------------------------------------------------
        t.clic(page.get_by_role("button", name="Autre lésion").or_(page.get_by_role("link", name="Autre lésion")).first, 14)
        page.wait_for_url("**/analyses/nouvelle*"); attendre()
        page.get_by_role("button", name="Changer de patient").wait_for()
        page.locator("input[type=file]").set_input_files(str(tableur))
        page.get_by_label("Ou choisissez dans la liste").select_option("back")
        page.wait_for_timeout(250)
        s.debut("hors_sujet")
        t.legende("", "Ici, une capture d'écran choisie par erreur", "", 0)
        t.clic(page.get_by_role("button", name="Analyser la lésion").last, 18)
        page.get_by_role("heading", name="Image inhabituelle").wait_for(timeout=30000)
        t.legende("", "Image refusée", "Elle ne ressemble pas à une dermoscopie.", 0)
        s.fin(1.2)

        # Suivi ----------------------------------------------------------------------------------------
        page.keyboard.press("Escape")
        aller(page, f"/lesions/{LESION_SUIVIE}")
        page.get_by_role("heading", name="Comparaison").wait_for(timeout=8000)
        page.wait_for_timeout(500)
        s.debut("suivi")
        t.legende("", "Suivi dans le temps", "Chronologie, avant / après, signaux d'évolution.", 0)
        page.mouse.move(L * 0.6, H * 0.4, steps=12)
        s.jusqua(1.8)
        t.defiler(640, 34)
        s.jusqua(4.3)
        t.defiler(520, 30)
        s.fin()

        # Validation et comptes rendus -----------------------------------------------------------------
        aller(page, f"/analyses/{aid}")
        attendre_image(page)
        confirmer = page.get_by_role("radio", name="Je confirme")
        confirmer.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        s.debut("validation")
        t.legende("", "Le médecin valide ou corrige", "Sa décision est enregistrée dans le dossier.", 0)
        t.clic(confirmer, 16)
        t.clic(page.get_by_role("button", name="Enregistrer la validation"), 16)
        s.jusqua(3.2)
        montrer_comptes_rendus(page, URL, t)
        s.fin(0.6)

        # Administration -------------------------------------------------------------------------------
        page.goto(URL + "/administration?onglet=comptes"); attendre()
        s.debut("administration")
        t.legende("", "L'établissement garde la main", "Comptes, journal d'audit, sauvegardes, recalibrage.", 0)
        page.mouse.move(L * 0.55, H * 0.45, steps=12)
        s.jusqua(2.2)
        t.clic(page.get_by_role("tab", name="Journal d'audit"), 16)
        s.jusqua(4.2)
        t.clic(page.get_by_role("tab", name="Sauvegardes"), 16)
        s.jusqua(6.0)
        t.clic(page.get_by_role("tab", name="Recalibrage"), 16)
        attendre()
        t.vers(page.get_by_text(re.compile("^Recommandation")).first, 18)
        s.fin()

        # Chiffres -------------------------------------------------------------------------------------
        t.clic(page.get_by_role("link", name="Modèle d'IA"), 16)
        attendre()
        page.get_by_role("heading", name="Images hors sujet").wait_for(timeout=8000)
        s.debut("chiffres")
        t.legende("", "Performances publiées, limites comprises", "", 0)
        s.jusqua(2.9)
        carte(page, f"""<h1>Résultats mesurés sur le jeu de test</h1>
            <div class="chiffres">
              <div {retard(0.7)}><b>1 009</b><span>images jamais vues par le modèle, dont 113 mélanomes</span></div>
              <div {retard(3.2)}><b>92,0 %</b><span>des mélanomes signalés</span></div>
              <div {retard(5.6)}><b>22,5 %</b><span>de fausses alertes sur les lésions non mélanomes</span></div>
            </div><p class="note">HAM10000, contexte clinique complet. Performance rétrospective, sans validation clinique.</p>""")
        s.fin(0.6)

        # Fin ------------------------------------------------------------------------------------------
        carte(page, f"""{LOGO}<h1>Version de démonstration</h1>
            <p {retard(0.6)}>Pas un dispositif médical.</p>
            <p {retard(3.0)}>Modèle entraîné sur HAM10000 (CC BY-NC 4.0), à usage non commercial.</p>
            <p {retard(5.6)}>Réentraînement et validation clinique requis avant tout usage réel.</p>""")
        s.debut("fin")
        s.fin(1.6)
        video = page.video.path()
        page.close()
        ctx.close(); nav.close()
    if erreurs:
        print("Erreurs de page :", erreurs[:5])

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    capture = tmp / "capture.webm"
    shutil.copy(video, capture)
    monter(capture, s.marques, durees, coupe)


if __name__ == "__main__":
    main()
