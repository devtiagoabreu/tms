param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoCollector
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = Join-Path $PSScriptRoot "src"
}
if (-not $env:TMS_DATABASE_URL) {
    $env:TMS_DATABASE_URL = "postgresql+psycopg://tms:tms@localhost:5432/tms"
}
if ($NoCollector) {
    $env:TMS_COLLECT_INTERVAL = "0"
} elseif (-not $env:TMS_COLLECT_INTERVAL) {
    $env:TMS_COLLECT_INTERVAL = "60"
}

$python = if ($env:TMS_PYTHON) { $env:TMS_PYTHON } else { "python" }

Write-Host "Aplicando migracoes do banco..."
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao aplicar as migracoes (alembic upgrade head)."
}

Write-Host "TMS disponivel em http://${BindAddress}:$Port"
Write-Host "Pressione Ctrl+C para encerrar."
& $python -m uvicorn tms.app.main:app --host $BindAddress --port $Port --proxy-headers
