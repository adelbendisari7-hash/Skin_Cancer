# dermIA — application locale d'aide au triage des lésions cutanées

*Avant toute commercialisation, vérifiez que le nom « dermIA » est libre. Pour le changer : variable `DERMIA_NOM` et
`frontend/index.html`.*

Le médecin envoie une image dermoscopique, indique le patient (pseudonymisé) et la localisation de la lésion.
L'IA propose une orientation — **suspicion de mélanome**, **avis spécialisé**, **bénin probable** ou **renvoi au
médecin quand elle n'est pas assez sûre d'elle** — avec les probabilités, l'ensemble de diagnostics garanti à 90 %,
la carte des zones regardées (Grad-CAM) et un outil « et si » qui montre l'influence du contexte. Le médecin valide
ou corrige ; un compte rendu PDF est généré. Tout fonctionne **en local**, sans internet.

**Version 2** : suivi d'une même lésion dans le temps (chronologie, comparaison avant/après, signaux d'évolution),
critères **ABCD** automatiques, **refus des images hors sujet**, **recalibrage local** des seuils sur les cas validés
de l'établissement, **sauvegarde et restauration en un clic**, interface et comptes rendus en **français, anglais et
arabe** (de droite à gauche), modèle plus puissant (EfficientNet-B2, 288 px). Résultats chiffrés : `docs/resultats_v2.md`.

**Version 3 (modèle par défaut depuis le 4 novembre 2026)** : même réseau, entraîné sur HAM10000 **et BCN20000**
(Barcelone), soit trois centres ; le champ circulaire du dermoscope est recadré avant l'analyse et la localisation est
ramenée à cinq zones communes aux deux bases. Plan fixé avant l'entraînement : `docs/plan_v3.md` ; résultats :
`docs/resultats_v3.md`. Le paquet v2 reste disponible (`DERMIA_MODELE=modeles/ham10000-m5-v2`).

Captures d'écran : `docs/captures/` (v1) et `docs/captures/v2/` (3 langues) — images de démonstration HAM10000,
usage non commercial. **Vidéos** : `docs/video/visite_complete_dermia.mp4` (toutes les fonctions) et
`docs/video/tutoriel_dermia.mp4` (prise en main). Régénérables avec `python outils/video_complete.py` et
`python outils/video_tutoriel.py` (instance de démonstration lancée, Playwright et Google Chrome requis).
Présentation aux clients, avec voix off : `docs/video/presentation_dermia.mp4`, tournée sur le site en ligne
(`python outils/narration_presentation.py` puis `python outils/video_presentation.py`).

## Démonstration en ligne

Une démonstration est déployée sur Vercel depuis ce dépôt (`vercel.json`, branche `main`) :
https://dermia-prudence.vercel.app. Le mode s'active à la construction (`VITE_DEMO_STATIQUE=1`) ; il est absent de la
version installée. Elle contient deux choses :

- un instantané de vraies réponses de l'application (`frontend/demo-statique/`, régénéré par
  `python outils/exporter_demo_statique.py`), en lecture seule ;
- le vrai moteur, qui tourne **dans le navigateur du visiteur** (ONNX Runtime Web dans un fil de calcul,
  `frontend/src/navigateur/`). L'image n'est envoyée à aucun serveur ; patients, analyses et validations du visiteur
  restent dans son navigateur (IndexedDB) et peuvent être effacés d'un clic. Un avis obligatoire précède la première
  analyse, car un site public peut être utilisé par un non-médecin. Premier lancement : environ 55 Mo téléchargés.

Les réseaux sont exportés par `python -m src.export_onnx` (depuis `projet/`, demi-précision, un tronc et une tête par
réseau). `vercel.json` envoie les en-têtes COOP/COEP qui activent le calcul multi-fil ; sans eux, le moteur tourne sur
un seul fil, plus lentement.

Fidélité au moteur PyTorch (`python outils/verifier_navigateur.py <dist>`, résultats dans
`docs/verification_navigateur.json`, modèle v3) : sur 70 images des jeux de test HAM10000 et BCN20000 dans Chrome,
dont 17 recadrées au champ du dermoscope, décision, orientation, ensemble conforme, refus hors sujet et scores A, B et C
identiques dans 100 % des cas, écart de probabilité maximal 0,0046, aucune requête d'envoi pendant les analyses, document
de test refusé. C'est une vérification de reproduction du moteur, pas une
nouvelle évaluation clinique.

Différences avec l'application installée : pas de compte rendu PDF ni de diamètre (échelle inconnue) sur les analyses
du visiteur, pas de lecture des TIFF, et aucune administration réelle.

Le moteur serveur complet ne peut pas fonctionner sur Vercel : PyTorch et les poids dépassent la limite de 500 Mo d'une
fonction Python, et une base SQLite ne survit pas sur un disque non persistant. **Les réseaux ONNX sont publics** (dans
ce dépôt et téléchargeables depuis le site) : ils restent soumis aux licences non commerciales de HAM10000 et
BCN20000. Les poids PyTorch (`modeles/*/poids`, `hors_sujet.npz`) ne sont pas publiés et se régénèrent avec
`python -m src.export_v3`.

## Statut — à lire avant toute démonstration

| | |
|---|---|
| **Logiciel** | Code propriétaire du projet : peut être commercialisé. |
| **Modèle fourni** (`modeles/ham10000-bcn20000-m5-v3` ; v1 et v2 conservés) | Entraîné sur HAM10000 et BCN20000, **licences CC BY-NC 4.0 : usage non commercial uniquement**. Démonstrations et recherche seulement. |
| **Usage clinique** | **Interdit en l'état.** Un logiciel d'aide au diagnostic est un dispositif médical : marquage/enregistrement obligatoire avant toute mise sur le marché (voir la feuille de route). |

L'application affiche ce statut en permanence (bandeau, fiche du modèle, comptes rendus).

## Démarrage (Windows)

1. Installer **Python 3.13** (python.org), puis double-cliquer sur **`installer.bat`** (une seule fois ; installe
   PyTorch GPU si une carte NVIDIA est présente, sinon la version processeur).
2. Double-cliquer sur **`lancer_application.bat`** : le navigateur s'ouvre sur `http://127.0.0.1:8765`.
3. Au premier lancement, créer le **compte administrateur** et le nom de l'établissement, puis les comptes des
   médecins dans *Administration*.

Matériel : un PC de bureau suffit. Une analyse prend ~0,5 s sur processeur (~0,2 s sur GPU), plus ~0,6 s pour la
carte Grad-CAM sur processeur (~0,1 s sur GPU), critères ABCD en plus (~0,2 s). Mémoire : ~2 Go.

**Démonstration commerciale** : double-cliquer sur **`lancer_demo.bat`** — instance séparée (`donnees_demo`) avec
un historique d'environ 400 lésions validées (jeu de test HAM10000, étalé sur douze mois), des lésions suivies dans le
temps, des analyses à valider, une image hors sujet refusée puis forcée, une proposition de recalibrage et une
sauvegarde ; comptes `admin` / `Demo2026admin` et `k.haddad` / `Demo2026medecin` (images HAM10000 : démonstration non
commerciale ; dates et ordre des images d'une même lésion mis en scène). Pour la recréer (application arrêtée) :
`python outils\creer_demo.py --remplacer`.

Le lanceur vérifie que l'environnement Python est **complet** avant de démarrer : si `installer.bat` a été
interrompu, il utilise l'environnement du projet (`..\.venv`) ou indique de relancer l'installation (qui reprend là
où elle s'était arrêtée).

## Ce que fait chaque écran

- **File de travail** — analyses à valider, les plus graves en premier (badge « Évolution » si la lésion a changé) ;
  activité et accord médecin–IA.
- **Nouvelle analyse** — patient (recherche ou création), **lésion** (nouvelle, ou nouvelle image d'une lésion
  suivie), image (glisser-déposer), localisation sur une carte du corps, contexte. Une image qui ne ressemble pas à
  une dermoscopie est **refusée avec une explication** ; « analyser quand même » reste possible, tracé et signalé.
- **Résultat** — oculaire (image / Grad-CAM / contour ABCD), orientation et motif, probabilités avec seuil d'alerte
  mélanome, **critères ABCD** (asymétrie, bords, couleurs, diamètre si l'échelle est renseignée), **évolution**
  depuis l'examen précédent, « et si », validation médicale (avec confirmation histologique), compte rendu PDF
  en français, anglais ou arabe.
- **Lésion suivie** — chronologie des examens, courbe de la probabilité de mélanome, comparaison avant/après.
- **Patients** — dossiers pseudonymisés (code `P-AAAA-NNNN`, année de naissance, sexe, n° de dossier local) et
  leurs lésions suivies.
- **Modèle d'IA** — fiche du modèle (traduite) : statut, licence, architecture, performances, détecteur d'images
  hors sujet, règles de décision, limites.
- **Administration** — comptes et réglages (prudence, largeur du champ du dermoscope), **recalibrage local**,
  **sauvegardes** (créer, télécharger, importer, restaurer), journal d'audit.
- **Langue** — sélecteur Français / English / العربية (barre latérale et écran de connexion), mémorisé par poste.

## Architecture

```
application/
├── backend/dermia/          serveur Python (FastAPI)
│   ├── engine/              moteur d'IA autonome : architecture, prétraitement, TTA, décision au coût,
│   │                        abstention conforme, Grad-CAM, « et si », images hors sujet (engine.py),
│   │                        critères ABCD (abcd.py), suivi (suivi.py), recalibrage local (recalibrage.py)
│   ├── api/                 routes REST : système, comptes, patients, analyses, lésions, recalibrage, sauvegardes
│   ├── db.py                SQLite (SQLAlchemy) : utilisateurs, patients, lésions, analyses, calibrations,
│   │                        journal, paramètres ; migration automatique d'une base v1
│   ├── sauvegarde.py        archives ZIP cohérentes (API de sauvegarde SQLite), vérification, restauration
│   ├── i18n.py              messages d'erreur en français, anglais, arabe (en-tête X-Langue)
│   ├── security.py          scrypt, session JWT en cookie HttpOnly, anti-CSRF, limitation des tentatives
│   ├── pdf.py               compte rendu trilingue (ReportLab ; arabe : liaison des lettres et ordre bidi)
│   ├── polices/             IBM Plex Sans Arabic (licence OFL)
│   └── main.py              application + en-têtes de sécurité + service de l'interface
├── frontend/                interface React + TypeScript + Tailwind (dist/ = version construite, livrée)
├── modeles/<nom>/           paquet de modèle : manifest.json + poids (empreintes SHA-256 vérifiées)
├── tests/                   moteur (non-régression), ABCD, recalibrage et suivi, sauvegardes, traductions et PDF,
│                            API (parcours complet, lésions, hors sujet, recalibrage, restauration, protections)
├── outils/                  creer_demo.py, captures_revue.py (3 langues), video_complete.py, video_tutoriel.py, video_presentation.py
├── donnees/                 créé au 1er lancement : base, images, clé de session (à sauvegarder, jamais versionné)
├── installer.bat / lancer_application.bat
└── requirements.txt
```

**Chaîne de décision** (identique au projet de recherche, vérifiée par `tests/test_moteur.py`) : image → contrôle
« hors sujet » → 288 px → 4 retournements × 3 réseaux EfficientNet-B2 → probabilités moyennes → « mélanome » si p(mel) ≥ seuil (réglé pour qu'un mélanome manqué coûte R
fausses alertes) → ensemble conforme Mondrian (α = 0,1) → l'IA ne conclut seule que si l'ensemble ne contient qu'un
diagnostic, identique à sa décision. Contexte incomplet → profil robuste (entraîné avec contexte masqué).

## Sécurité et données

- Serveur lié à `127.0.0.1` : inaccessible depuis le réseau par défaut.
- Aucun nom de patient stocké ; images ré-encodées en PNG sans métadonnées.
- Mots de passe scrypt ; session dans un cookie HttpOnly / SameSite=Strict ; refus des requêtes d'autres origines ;
  5 échecs de connexion en 15 min bloquent l'identifiant ; en-têtes `nosniff`, `DENY`, `no-referrer`.
- Journal d'audit : connexions (réussies et refusées), analyses, validations, exports, administration.
- **Sauvegarde** : *Administration → Sauvegardes* (archive vérifiée : intégrité SQLite, empreinte SHA-256, contenu
  attendu uniquement). Sauvegarde automatique au plus une fois par jour (7 conservées) dans `donnees/sauvegardes`.
  Une restauration fait d'abord une sauvegarde de sécurité. **Copier régulièrement une archive hors de la machine.**

## Développement

```powershell
# API (port 8765) en autorisant le serveur de développement de l'interface
$env:PYTHONPATH="backend"; $env:DERMIA_ORIGINES="http://localhost:5173"; ..\.venv\Scripts\python -m dermia
# Interface avec rechargement à chaud (proxy /api → 8765)
cd frontend; npm install; npm run dev
# Tests (GPU si disponible ; DERMIA_DEVICE=cpu pour forcer le processeur)
..\.venv\Scripts\python -m pytest
# Reconstruire l'interface livrée
cd frontend; npm run build
# Régénérer le paquet de modèle v3 (réglages du plan, détecteur hors sujet, fiche) et la référence de non-régression
cd ..; .venv\Scripts\python -m src.export_v3
```

| Variable | Rôle | Défaut |
|---|---|---|
| `DERMIA_NOM` | nom du produit affiché | dermIA |
| `DERMIA_DONNEES` | dossier des données | `application/donnees` |
| `DERMIA_MODELE` | paquet de modèle à charger | `modeles/ham10000-bcn20000-m5-v3` |
| `DERMIA_SAUVEGARDE_AUTO` | `0` pour désactiver la sauvegarde quotidienne | 1 |
| `DERMIA_HOTE`, `DERMIA_PORT` | adresse d'écoute | 127.0.0.1, 8765 |
| `DERMIA_DEVICE` | `cuda` ou `cpu` | automatique |
| `DERMIA_NAVIGATEUR` | `0` pour ne pas ouvrir le navigateur | 1 |
| `DERMIA_ORIGINES` | origines supplémentaires (développement) | — |

**Remplacer le modèle** : produire un nouveau dossier `modeles/<nom>/` au même format (`manifest.json` + poids),
pointer `DERMIA_MODELE` dessus, relancer `pytest`. L'application vérifie les empreintes et affiche la nouvelle fiche ;
chaque analyse enregistre le nom et la version du modèle utilisé.

## Feuille de route vers un produit commercialisable

1. **Données et modèle** — constituer ou licencier un jeu d'images dermoscopiques **autorisé à l'usage commercial**
   (partenariats hospitaliers avec consentement, ou jeux sous licence commerciale), réentraîner avec le même code,
   puis **valider sur des données externes** (autres centres, autres phototypes, dont des peaux foncées).
2. **Réglementaire** — un logiciel d'aide au diagnostic est un dispositif médical : en Europe, règle 11 du MDR
   (classe IIa au minimum, probablement IIb pour le mélanome) ; ailleurs, enregistrement auprès de l'autorité
   sanitaire du pays (en Algérie, à confirmer avec un juriste spécialisé). Prérequis habituels : système qualité
   ISO 13485, cycle de vie logiciel IEC 62304, gestion des risques ISO 14971, aptitude à l'utilisation IEC 62366,
   **étude clinique** prospective, protection des données de santé (RGPD ; loi algérienne 18-07).
3. **Industrialisation** — installateur Windows signé (PyInstaller + Inno Setup), mises à jour, chiffrement de la
   base, mode multi-postes en réseau (HTTPS).
4. **Fonctionnalités** — export DICOM / HL7 FHIR vers les dossiers patients, tableau de bord de fiabilité (accord
   médecin–IA par établissement), photos de peau sans dermoscope (modèle et détecteur à entraîner sur ces images).
