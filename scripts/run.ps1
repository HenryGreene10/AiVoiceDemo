# scripts/run.ps1
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..   # go to repo root

# Per-run env (no need to persist)
$env:PYTHONPATH = (Resolve-Path .\src).Path
if (-not $env:ELEVENLABS_API_KEY) { $env:ELEVENLABS_API_KEY = "<YOUR_ELEVENLABS_KEY>" }
if (-not $env:ELEVENLABS_VOICE)   { $env:ELEVENLABS_VOICE   = "<REAL_VOICE_ID>" }

# Free port 8000 if needed
try {
  $p = (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess
  if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
} catch {}

python -m uvicorn main:app --reload --port 8000


