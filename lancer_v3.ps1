# Entraînement de la version 3 (HAM10000 + BCN20000), plan : application/docs/plan_v3.md
# Relançable sans risque : les graines déjà terminées sont sautées (--reprendre).
# Usage : powershell -ExecutionPolicy Bypass -File lancer_v3.ps1   (journal : logs\v3_entrainement.log)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
$journal = "logs\v3_entrainement.log"
"=== debut $(Get-Date -Format s)" | Out-File -Append -Encoding utf8 $journal
foreach ($exp in "V3_M5_B2", "V3_M5_dropClin_B2") {
    & .venv\Scripts\python.exe -u -m src.train --exp $exp --seeds 0 1 2 --reprendre 2>&1 |
        ForEach-Object { "$_" } | Out-File -Append -Encoding utf8 $journal
    "=== $exp termine (code $LASTEXITCODE) $(Get-Date -Format s)" | Out-File -Append -Encoding utf8 $journal
}
"SERIE TERMINEE $(Get-Date -Format s)" | Out-File -Append -Encoding utf8 $journal
