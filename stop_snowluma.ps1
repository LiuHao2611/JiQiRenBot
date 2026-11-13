# Stop the isolated SnowLuma deployment. Volumes and data are preserved.
# ASCII-only on purpose: Windows PowerShell 5.1 mishandles UTF-8 without BOM.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Stopping qq_bridge_snowluma containers (data volumes are kept)..."
docker compose -f docker-compose.snowluma.yml down
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed ($LASTEXITCODE)" }
Write-Host "Old deployments (qq_bridge / qq_bridge_official) were NOT touched."
