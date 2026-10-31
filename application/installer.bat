@echo off
rem Installation de l'application : environnement Python dédié + dépendances.
rem À lancer une seule fois (ou après une mise à jour). Nécessite Python 3.13 et une connexion internet.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul || (echo Python 3.13 est introuvable. Installez-le depuis python.org puis relancez. & pause & exit /b 1)

if not exist ".venv\Scripts\python.exe" (
    echo Création de l'environnement Python...
    py -3.13 -m venv .venv || (echo Échec de la création de l'environnement. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q

echo.
echo  Installation de PyTorch : téléchargement de 0,3 à 3 Go selon la version.
echo  Cela peut prendre 5 à 20 minutes. NE FERMEZ PAS cette fenêtre.
echo.
where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
    echo Carte graphique NVIDIA détectée : PyTorch GPU ^(CUDA 12.8^).
    ".venv\Scripts\python.exe" -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128 || goto echec
) else (
    echo Pas de carte NVIDIA : PyTorch pour processeur.
    ".venv\Scripts\python.exe" -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu || goto echec
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto echec

".venv\Scripts\python.exe" -c "import uvicorn, fastapi, sqlalchemy, reportlab, jwt, multipart, torch, torchvision" || goto echec
echo.
echo  Installation terminée. Lancez l'application avec lancer_application.bat
pause
exit /b 0

:echec
echo.
echo  L'installation a échoué ou a été interrompue. Vérifiez la connexion internet puis relancez installer.bat :
echo  l'installation reprendra là où elle s'est arrêtée.
pause
exit /b 1
