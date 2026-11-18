# Start the local stack in one terminal; Ctrl+C stops the child processes.
param(
    [string]$Python = "",
    [switch]$SkipMigrations,
    [switch]$LocalAI
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not $Python) {
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython }
    else { $Python = 'python' }
}

$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Copy .env.example to .env and configure APP_SECRET before starting.'
}
# Read simple KEY=value assignments as data. Never evaluate shell code from .env.
foreach ($rawLine in Get-Content -LiteralPath $envFile) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    $separator = $line.IndexOf('=')
    if ($separator -lt 1) { continue }
    $name = $line.Substring(0, $separator).Trim()
    if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { continue }
    $value = $line.Substring($separator + 1).Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}

if ($LocalAI) {
    $env:FREE_MODE='true'
    $env:LOCAL_NO_AUTH='true'
    $env:OLLAMA_BASE_URL='http://127.0.0.1:11435'
    $env:OLLAMA_MODEL=$env:ACF_LOCAL_MODEL
    $env:LOCAL_AI_FRAME_BATCH_SIZE='1'
    $env:LOCAL_AI_ALLOW_MODEL_DOWNLOAD='false'
    $env:MAX_UPLOAD_MB='1500'
    $env:LOCAL_AI_PROXY_SIZE='1600mb'
    if ($env:ACF_SPEECH_MODEL) { $env:LOCAL_WHISPER_MODEL=$env:ACF_SPEECH_MODEL }
}
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'
$runtimePath = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
if (-not $SkipMigrations) {
    Push-Location -LiteralPath $backendPath
    try {
        & $Python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    } finally { Pop-Location }
}

$processes = @()
try {
    $processes += Start-Process -FilePath $Python -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'api.log') -RedirectStandardError (Join-Path $runtimePath 'api-error.log')
    $processes += Start-Process -FilePath $Python -ArgumentList @('-m', 'app.worker') -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'worker.log') -RedirectStandardError (Join-Path $runtimePath 'worker-error.log')
    Write-Host 'AI Clip Factory starting at http://localhost:3000. Logs: .runtime/. Press Ctrl+C to stop.'
    Push-Location -LiteralPath $frontendPath
    try { & npm.cmd run dev }
    finally { Pop-Location }
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    }
}
