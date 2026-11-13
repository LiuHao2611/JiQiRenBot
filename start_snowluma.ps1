# Start the isolated SnowLuma deployment. Run this in YOUR OWN terminal.
# ASCII-only on purpose: Windows PowerShell 5.1 mishandles UTF-8 without BOM.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".env")) {
    throw "Missing .env in $root"
}
if (-not (Test-Path "docker-compose.snowluma.yml")) {
    throw "Missing docker-compose.snowluma.yml"
}

Write-Host "[1/3] Building bridge image and starting containers..."
docker compose -f docker-compose.snowluma.yml up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed ($LASTEXITCODE)" }

Write-Host "[2/3] Container status:"
docker compose -f docker-compose.snowluma.yml ps

Write-Host "[3/3] Next steps (manual, interactive):"
Write-Host "  * WebUI   : http://127.0.0.1:5099  (initial password is in docker logs, shown ONCE)"
Write-Host "  * noVNC   : http://127.0.0.1:6081  (password = VNC_PASSWD in .env)"
Write-Host "  * Logs    : docker logs qq-bridge-snowluma-protocol | Select-String 'initial credentials|password'"
Write-Host "  * After first WebUI wizard + QR login, run:"
Write-Host "      python scripts/setup_snowluma_ws.py"
Write-Host "      docker compose -f docker-compose.snowluma.yml restart snowluma"
Write-Host "  * Verify  : python scripts/verify_snowluma_deploy.py"
Write-Host ""
Write-Host "SAFETY: do NOT log the same QQ account into NapCat and SnowLuma at the same time."
Write-Host "        Do NOT add an auto-restart daemon to the protocol container."
