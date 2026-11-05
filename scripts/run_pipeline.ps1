# zioX Scheduled Pipeline Runner for Windows Task Scheduler
# Usage: powershell.exe -ExecutionPolicy Bypass -File scripts\run_pipeline.ps1 [-NoJitter] [-Live]

param (
    [switch]$NoJitter,
    [switch]$Live
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

$LogDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Timestamp = (Get-Date).ToString("yyyy-MM-dd_HH-mm-ss")
$LogFile = Join-Path $LogDir "pipeline_$Timestamp.log"

Write-Output "[zioX Scheduler] Invoking autonomous pipeline at $(Get-Date)..." | Tee-Object -FilePath $LogFile -Append

$PipelineArgs = @("--pipeline")
if ($NoJitter) {
    $PipelineArgs += "--no-jitter"
} else {
    $PipelineArgs += @("--start-jitter", "15")
}

if ($Live) {
    $PipelineArgs += "--live"
}

# Run unified pipeline with start jitter or immediate execution
& $VenvPython main.py @PipelineArgs 2>&1 | Tee-Object -FilePath $LogFile -Append

$ExitCode = $LASTEXITCODE
Write-Output "[zioX Scheduler] Pipeline completed with exit code: $ExitCode" | Tee-Object -FilePath $LogFile -Append

exit $ExitCode
