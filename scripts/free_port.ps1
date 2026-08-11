param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8501,

    [ValidateRange(1, 60)]
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

function Get-ListenerProcessIds {
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    $processIds = foreach ($line in (& netstat -ano -p tcp)) {
        if ($line -match $pattern) {
            [int]$Matches[1]
        }
    }
    return @($processIds | Sort-Object -Unique)
}

$processIds = @(Get-ListenerProcessIds)
if ($processIds.Count -eq 0) {
    Write-Host "[OK] Port $Port is available."
    exit 0
}

foreach ($processId in $processIds) {
    Write-Host "[INFO] Stopping process $processId on port $Port..."
    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
    }
    catch {
        Write-Host "[WARN] Could not stop process $processId`: $($_.Exception.Message)"
    }
}

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (@(Get-ListenerProcessIds).Count -eq 0) {
        Write-Host "[OK] Port $Port released and verified."
        exit 0
    }
    Start-Sleep -Milliseconds 250
}

$remaining = @(Get-ListenerProcessIds)
Write-Host "[ERROR] Port $Port is still in use by PID(s): $($remaining -join ', ')"
exit 1
