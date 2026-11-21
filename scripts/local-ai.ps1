# -Setup installs packages and downloads free models; subsequent runs are offline.
param([switch]$Setup,[string]$Model='qwen3-vl:4b-instruct')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python=Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv using Python 3.12 first.' }
if ($Setup) {
    & $python -m pip install -r backend/requirements.txt -r backend/requirements-local-ai.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & ollama pull $Model
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
}
$modelCache=Join-Path $projectRoot '.runtime/local-ultimate-media/models/faster-whisper'
$downloadCode='from faster_whisper.utils import download_model; import sys; print(download_model("base",cache_dir=sys.argv[1],local_files_only=sys.argv[2]=="offline"))'
$speech=& $python -c $downloadCode $modelCache $(if($Setup){'download'}else{'offline'})
if ($LASTEXITCODE -ne 0) { throw 'Speech model missing. Run once with -Setup.' }
$env:ACF_LOCAL_MODEL=$Model
$env:ACF_SPEECH_MODEL=($speech | Select-Object -Last 1).Trim()
$env:OLLAMA_HOST='127.0.0.1:11435'
$env:OLLAMA_VULKAN='0'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_CONTEXT_LENGTH='4096'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$modelServer=$null
try {
    try { $null=Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' -TimeoutSec 3 }
    catch {
        $ollama=(Get-Command ollama -ErrorAction Stop).Source
        $modelServer=Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru
        $ready=$false
        for($attempt=0;$attempt -lt 90;$attempt++) {
            try { $null=Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' -TimeoutSec 2; $ready=$true; break }
            catch { Start-Sleep -Seconds 1 }
        }
        if(-not $ready){throw 'Local Ollama did not start. Check its GPU/server logs.'}
    }
    & (Join-Path $PSScriptRoot 'dev.ps1') -Python $python -LocalAI
} finally {
    if($modelServer -and -not $modelServer.HasExited){Stop-Process -Id $modelServer.Id}
}
