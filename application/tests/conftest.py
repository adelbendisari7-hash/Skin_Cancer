"""Les tests utilisent un dossier de données temporaire : la base réelle n'est jamais touchée."""
import os
import tempfile

os.environ["DERMIA_DONNEES"] = tempfile.mkdtemp(prefix="dermia_tests_")
os.environ["DERMIA_SAUVEGARDE_AUTO"] = "0"     # pas de fil de sauvegarde pendant les tests
