$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "LocalAI Control - Windows installation" -ForegroundColor Green

$Python = Get-Command py -ErrorAction SilentlyContinue
if (-not $Python) {
    throw "Python 3.12 or newer was not found. Install it from python.org and run this script again."
}
$VersionText = & py -3.12 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
if (-not $VersionText) {
    throw "Python 3.12 or newer is required."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py -3.12 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --requirement requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $SecretBytes = New-Object byte[] 48
    $SearchBytes = New-Object byte[] 48
    $Generator.GetBytes($SecretBytes)
    $Generator.GetBytes($SearchBytes)
    $Generator.Dispose()
    $Secret = [Convert]::ToBase64String($SecretBytes)
    $SearchSecret = [Convert]::ToBase64String($SearchBytes)
    $Config = Get-Content ".env" -Raw
    $Config = $Config.Replace("replace-with-at-least-32-random-characters", $Secret)
    $Config = $Config.Replace("replace-with-a-separate-random-secret", $SearchSecret)
    Set-Content ".env" $Config -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path "data\uploads", "data\projects", "data\backups" | Out-Null

Write-Host "Create the first administrator account." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m scripts.create_admin

$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($Ollama) {
    $InstallModel = Read-Host "Install the default local model qwen2.5-coder:7b now? [Y/n]"
    if ($InstallModel -notin @("n", "N", "no", "No")) {
        & ollama pull qwen2.5-coder:7b
    }
} else {
    Write-Warning "Ollama was not found. Install it from https://ollama.com/download before using chat."
}

Write-Host "Installation complete. Run .\start-windows.ps1" -ForegroundColor Green
