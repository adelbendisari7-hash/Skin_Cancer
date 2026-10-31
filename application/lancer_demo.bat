@echo off
rem Lance l'instance de DÉMONSTRATION (dossier donnees_demo, cas d'exemple déjà analysés).
rem Comptes : admin / Demo2026admin   et   k.haddad / Demo2026medecin
rem Pour l'usage réel, utiliser lancer_application.bat (dossier donnees, vierge).
setlocal
chcp 65001 >nul
set "DERMIA_DONNEES=%~dp0donnees_demo"
call "%~dp0lancer_application.bat"
