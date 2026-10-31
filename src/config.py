"""Configuration centrale du projet HAM10000 (chemins, graines, hyperparamètres).

Tous les autres modules importent ces constantes : modifier une valeur ici
suffit pour relancer toute la chaîne avec un autre réglage.
Les chemins utilisent pathlib et fonctionnent sous Windows, Linux et Colab.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------
IS_COLAB = "google.colab" in sys.modules or "COLAB_RELEASE_TAG" in os.environ

PROJECT_DIR = Path(__file__).resolve().parents[1]          # .../projet
# Le dossier HAM10000 est en lecture seule ; on peut le déplacer via HAM_DIR.
DATA_DIR = Path(os.environ.get("HAM_DIR", PROJECT_DIR.parent / "HAM10000"))
METADATA_CSV = DATA_DIR / "HAM10000_metadata.csv"
IMAGE_DIRS = [DATA_DIR / "HAM10000_images_part_1", DATA_DIR / "HAM10000_images_part_2"]

CACHE_DIR = PROJECT_DIR / "cache"            # images redimensionnées (dérivées, régénérables)
RESULTS_DIR = PROJECT_DIR / "resultats"
FIG_DIR = RESULTS_DIR / "figures"
TAB_DIR = RESULTS_DIR / "tableaux"
PRED_DIR = RESULTS_DIR / "predictions"       # probabilités sauvegardées de chaque modèle
CKPT_DIR = PROJECT_DIR / "checkpoints"       # poids des réseaux (non versionnés)
SPLIT_CSV = RESULTS_DIR / "split_lesions.csv"

for _d in (CACHE_DIR, FIG_DIR, TAB_DIR, PRED_DIR, CKPT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Données
# --------------------------------------------------------------------------
# Ordre fixe des classes : il définit les indices de toutes les sorties.
CLASSES = ["nv", "mel", "bkl", "bcc", "akiec", "vasc", "df"]
CLASS_NAMES_FR = {
    "nv": "Nævus mélanocytaire",
    "mel": "Mélanome",
    "bkl": "Kératose bénigne",
    "bcc": "Carcinome basocellulaire",
    "akiec": "Kératose actinique / Bowen",
    "vasc": "Lésion vasculaire",
    "df": "Dermatofibrome",
}
MEL = CLASSES.index("mel")
N_CLASSES = len(CLASSES)

# Entrées cliniques autorisées. `dx_type` est volontairement EXCLU (fuite :
# follow_up n'existe que pour les nævus).
CLINICAL_COLS = ["age", "sex", "localization"]

# Découpage par lésion : train / validation / calibration / test
SPLIT_FRACTIONS = {"train": 0.70, "val": 0.10, "calib": 0.10, "test": 0.10}
SPLIT_SEED = 42
TRAIN_SEEDS = [0, 1, 2]

# --------------------------------------------------------------------------
# Images et entraînement
# --------------------------------------------------------------------------
IMG_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

EPOCHS = 15                 # maximum imposé
PATIENCE = 5                # arrêt si le F1 macro de validation stagne
BATCH_SIZE = 32
LR_BACKBONE = 3e-4
LR_HEAD = 1e-3
WEIGHT_DECAY = 1e-2         # AdamW (décroissance découplée)
NUM_WORKERS = 0             # l'augmentation se fait sur GPU : pas besoin de workers

# Perte sensible au coût : poids ∝ (n_max / n_k)^POWER, multiplié pour le mélanome
CLASS_WEIGHT_POWER = 0.5
MEL_WEIGHT_BOOST = 2.0

# Dropout de la modalité clinique (bonus) : probabilité de masquer le contexte patient
CLINICAL_DROPOUT_P = 0.25

# --------------------------------------------------------------------------
# Décision et abstention
# --------------------------------------------------------------------------
COST_RATIOS = [5, 10, 20]   # coût d'un mélanome manqué / coût d'une fausse alerte
DEFAULT_COST_RATIO = 10
ALPHA = 0.10                # niveau d'erreur de la prédiction conforme (couverture visée 90 %)
N_BOOTSTRAP = 2000
