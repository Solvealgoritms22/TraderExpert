param([switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

Set-Location $Root
& $Python -m PyInstaller --noconfirm --clean "TraderExpert.spec"
Write-Host "Ejecutable generado en: $Root\dist\TraderExpert\TraderExpert.exe"
