$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$work = Join-Path $env:LOCALAPPDATA 'HTFA\DataDubai'
$results = Join-Path $work 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$log = Join-Path $results 'task.log'
Set-Content -LiteralPath $log -Value "Started $(Get-Date -Format o)" -Encoding UTF8
$env:GIT_TERMINAL_PROMPT = '0'
$env:HTFA_UAE_DATA_DIR = Join-Path $work 'snapshot'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

Push-Location -LiteralPath $repo
try {
    $credential = "url=https://github.com/BichengNiu/HTFA_v1.1.git`n`n" |
        git -c credential.interactive=never credential fill
    if ($LASTEXITCODE -ne 0) {
        throw 'Git Credential Manager could not load the saved GitHub credential.'
    }
    $password = $credential | Where-Object { $_.StartsWith('password=') } | Select-Object -First 1
    if (!$password) {
        throw 'Git Credential Manager returned no GitHub token.'
    }
    $env:GH_TOKEN = $password.Substring(9)
    $python = Join-Path $repo 'runtime\python.exe'
    # Start-Process keeps UTF-8 output intact on Windows PowerShell 5.
    $stderrPath = Join-Path $results 'task-error.log'
    $stdoutPath = Join-Path $results 'task-output.log'
    $process = Start-Process -FilePath $python -WindowStyle Hidden -Wait -PassThru `
        -ArgumentList @('-m', 'htfa.monitoring.uae.jobs.publish_snapshot',
            '--data-dubai-only', '--results-dir', ('"{0}"' -f $results)) `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if ($process.ExitCode -ne 0) {
        throw "Data Dubai refresh exited with code $($process.ExitCode). See $stderrPath and the source results."
    }
    Add-Content -LiteralPath $log -Value "Completed $(Get-Date -Format o)" -Encoding UTF8
} catch {
    Add-Content -LiteralPath $log -Value $_.Exception.Message -Encoding UTF8
    exit 1
} finally {
    Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
    Pop-Location
}
