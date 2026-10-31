@echo off
rem Démarre l'application locale et ouvre le navigateur sur http://127.0.0.1:8765
rem Fermez cette fenêtre pour arrêter l'application.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0backend"
set "PYTHONIOENCODING=utf-8"

rem Choix de l'environnement Python : celui de l'application s'il est COMPLET, sinon celui du projet.
set "PY="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import uvicorn, fastapi, sqlalchemy, reportlab, jwt, multipart, torch, torchvision, scipy, skimage, arabic_reshaper, bidi" >nul 2>nul && set "PY=.venv\Scripts\python.exe"
)
if not defined PY if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" -c "import uvicorn, fastapi, sqlalchemy, reportlab, jwt, multipart, torch, torchvision, scipy, skimage, arabic_reshaper, bidi" >nul 2>nul && set "PY=..\.venv\Scripts\python.exe"
)
if not defined PY (
    echo.
    echo  L'environnement Python est absent ou incomplet ^(installation interrompue ?^).
    echo  Lancez installer.bat et laissez-le aller jusqu'au message « Installation terminée ».
    echo.
    pause
    exit /b 1
)
if not exist "frontend\dist\index.html" (
    echo Interface absente : le dossier frontend\dist doit être fourni avec l'application.
    pause
    exit /b 1
)
echo Environnement utilisé : %PY%
"%PY%" -m dermia
pause
