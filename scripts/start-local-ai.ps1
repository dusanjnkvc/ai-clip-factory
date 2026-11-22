# Start once, wait for the app, then open it. Keep the services alive after this window closes.
param(
    [switch]$NoBrowser,
    [switch]$Stop,
    [ValidateRange(10, 600)][int]$StartupTimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.runtime'
$entry = Join-Path $PSScriptRoot 'local-ai.ps1'
$recordPath = Join-Path $runtime 'local-workspace.json'
$url = 'http://localhost:3000/'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Get-ManagedProcess {
    if (-not (Test-Path -LiteralPath $recordPath)) { return $null }
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $process = Get-Process -Id $record.id -ErrorAction Stop
        # A stale PID must never authorize stopping a different process.
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started) { return $null }
        $info = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
        if ($info.CommandLine -notlike "*$entry*") { return $null }
        return $process
    } catch { return $null }
}

function Test-WorkspaceReady {
    try {
        foreach ($endpoint in @('http://127.0.0.1:8000/api/health', 'http://127.0.0.1:3000/api/health')) {
            $health = Invoke-RestMethod $endpoint -TimeoutSec 3
            if ($health.status -ne 'ok' -or $health.browser_mode -ne $false -or $health.free_mode -ne $true) { return $false }
        }
        return $true
    } catch { return $false }
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}

# Serialize launches and stops from this checkout, including rapid double clicks.
$key = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($projectRoot)).Replace('/', '_')
$mutex = New-Object Threading.Mutex($false, "Local\ClipFactory-$key")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'ClipFactory is already starting or stopping. Wait for that launcher to finish.' }
    $process = Get-ManagedProcess
    if ($Stop) {
        if ($process) {
            # Only the verified launcher and its descendants belong to this command.
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local workspace. Check Task Manager.' }
            Write-Host 'ClipFactory stopped. Your videos and projects are saved.'
        } else { Write-Host 'No workspace started by this launcher is running.' }
        exit 0
    }
    if (-not (Test-WorkspaceReady)) {
        if (-not $process) {
            foreach ($port in @(3000, 8000)) {
                if (Test-Port $port) { throw "Port $port is already in use, but ClipFactory is not ready. Close the other server or check .runtime logs before retrying." }
            }
            if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.venv/Scripts/python.exe'))) { throw 'Python environment missing. Follow the first-time setup in README.md.' }
            if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend/node_modules/next/package.json'))) { throw 'Frontend dependencies missing. Run npm ci in the frontend folder first.' }
            if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) { throw 'Local configuration missing. Follow the first-time setup in README.md.' }
            $process = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $entry + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'local-workspace.log') -RedirectStandardError (Join-Path $runtime 'local-workspace-error.log')
            @{ id = $process.Id; started = $process.StartTime.ToUniversalTime().Ticks.ToString() } | ConvertTo-Json | Set-Content -LiteralPath $recordPath
        }
        Write-Host 'Starting free local AI. Please wait; the first page can take a minute...'
        $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            if (Test-WorkspaceReady) { $ready = $true; break }
            $process.Refresh()
            if ($process.HasExited) { throw 'Local AI could not start. Read .runtime/local-workspace-error.log. If a model is missing, run scripts/local-ai.ps1 -Setup once.' }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) { throw 'Startup is taking longer than expected. Check .runtime/local-workspace-error.log and .runtime/api-error.log, then run this launcher again. The existing startup will be reused.' }
    }
    Write-Host "ClipFactory is ready: $url"
    Write-Host 'Services keep running in the background. Use Stop ClipFactory.cmd when finished.'
    if (-not $NoBrowser) { Start-Process $url -WindowStyle Hidden }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
