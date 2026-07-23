$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker was not found." }
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $Config = Get-Content ".env" -Raw
    $Config = $Config.Replace("replace-with-at-least-32-random-characters", [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
    $Config = $Config.Replace("replace-with-a-separate-random-secret", [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
    Set-Content ".env" $Config -Encoding UTF8
}
docker compose up --detach --build
docker compose exec app python -m scripts.create_admin
docker compose exec ollama ollama pull qwen2.5-coder:7b
Write-Host "Ready at https://localhost:8443" -ForegroundColor Green
Write-Host "Your browser may require the local Caddy CA certificate to be trusted. See README.md."
