[CmdletBinding()]
param(
    [ValidateSet("Start", "Stop", "SetupRuntime", "Watch")]
    [string]$Command = "Start",
    [string]$ProjectRoot,
    [string]$RuntimePython,
    [int]$Port = 8501,
    [int]$WaitSeconds = 15,
    [ValidateSet("Auto", "Edge", "Chrome")]
    [string]$Browser = "Auto",
    [int]$LauncherPid = 0,
    [int]$BackendPid = 0,
    [int]$BrowserPid = 0,
    [string]$BrowserPath,
    [string]$BrowserDataDirectory,
    [string]$StateFile,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StreamlitArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSCommandPath
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
if ([string]::IsNullOrWhiteSpace($RuntimePython)) {
    $RuntimePython = Join-Path $ProjectRoot "runtime\python.exe"
}

function ConvertTo-ProcessArgument {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Join-ProcessArguments {
    param([string[]]$Arguments)

    return (($Arguments | ForEach-Object {
                ConvertTo-ProcessArgument -Value $_
            }) -join " ")
}

function Get-ProcessRecord {
    param([int]$ProcessId)

    if ($ProcessId -le 0) {
        return $null
    }
    return Get-CimInstance -ClassName Win32_Process `
        -Filter "ProcessId = $ProcessId" `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Test-ProcessAlive {
    param([int]$ProcessId)

    return $null -ne (Get-ProcessRecord -ProcessId $ProcessId)
}

function Get-LauncherProcessId {
    $current = Get-ProcessRecord -ProcessId $PID
    if ($null -eq $current) {
        return 0
    }

    $parentId = [int]$current.ParentProcessId
    while ($parentId -gt 0) {
        $parent = Get-ProcessRecord -ProcessId $parentId
        if ($null -eq $parent) {
            return $parentId
        }
        $parentName = [IO.Path]::GetFileNameWithoutExtension([string]$parent.Name)
        if ($parentName -ieq "cmd") {
            return $parentId
        }
        $parentId = [int]$parent.ParentProcessId
    }
    return 0
}

function Get-BrowserNames {
    switch ($Browser) {
        "Edge" { return @("msedge.exe") }
        "Chrome" { return @("chrome.exe") }
        default { return @("msedge.exe", "chrome.exe") }
    }
}

function Find-BrowserPath {
    foreach ($name in (Get-BrowserNames)) {
        $command = Get-Command $name -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandType -eq "Application" } |
            Select-Object -First 1
        if ($null -ne $command -and (Test-Path -LiteralPath $command.Source)) {
            return (Resolve-Path -LiteralPath $command.Source).Path
        }
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    $roots = @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        $env:LOCALAPPDATA
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($root in $roots) {
        if ($Browser -in @("Auto", "Edge")) {
            [void]$candidates.Add((Join-Path $root "Microsoft\Edge\Application\msedge.exe"))
        }
        if ($Browser -in @("Auto", "Chrome")) {
            [void]$candidates.Add((Join-Path $root "Google\Chrome\Application\chrome.exe"))
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "No supported Edge or Chrome executable was found for the linked HTFA window."
}

function Get-BrowserSessionProcessIds {
    $ids = New-Object System.Collections.Generic.List[int]
    $browserName = Split-Path -Leaf $BrowserPath
    $profileNeedle = $BrowserDataDirectory.Replace('"', '').ToLowerInvariant()
    $records = @(Get-CimInstance -ClassName Win32_Process `
        -Filter "Name = '$browserName'" `
        -ErrorAction SilentlyContinue)

    foreach ($record in $records) {
        $commandLine = ([string]$record.CommandLine).Replace('"', '').ToLowerInvariant()
        if ($commandLine.Contains($profileNeedle)) {
            [void]$ids.Add([int]$record.ProcessId)
        }
    }

    if (Test-ProcessAlive -ProcessId $BrowserPid) {
        [void]$ids.Add($BrowserPid)
    }
    return @($ids | Sort-Object -Unique)
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    if ($ProcessId -le 0) {
        return
    }
    try {
        & taskkill.exe /PID $ProcessId /T /F *> $null
    }
    catch {
        # The process may have exited between the liveness check and taskkill.
    }
}

function Stop-BrowserSession {
    foreach ($processId in @(Get-BrowserSessionProcessIds | Sort-Object -Descending)) {
        Stop-ProcessTree -ProcessId $processId
    }
}

function Remove-SessionArtifacts {
    if (-not [string]::IsNullOrWhiteSpace($BrowserDataDirectory) -and
        (Test-Path -LiteralPath $BrowserDataDirectory)) {
        Remove-Item -LiteralPath $BrowserDataDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not [string]::IsNullOrWhiteSpace($StateFile) -and
        (Test-Path -LiteralPath $StateFile)) {
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    }
}

function Write-SessionState {
    param([string]$State)

    if ([string]::IsNullOrWhiteSpace($StateFile)) {
        return
    }
    try {
        Set-Content -LiteralPath $StateFile -Value $State -Encoding UTF8
    }
    catch {
        # Cleanup still proceeds if the state file cannot be written.
    }
}

function Test-PortOpen {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync("127.0.0.1", $Port)
        if ($connection.Wait(250) -and $client.Connected) {
            return $true
        }
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
    return $false
}

function Wait-BackendReady {
    param([int]$ProcessId)

    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if (-not (Test-ProcessAlive -ProcessId $ProcessId)) {
            throw "HTFA backend exited before opening port $Port."
        }
        if (Test-PortOpen) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "HTFA backend did not open port $Port within 30 seconds."
}

function Invoke-RepositoryUpdate {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $git) {
        Write-Host "[WARN] Git was not found; keeping the current HTFA source."
        return
    }

    $isRepository = (& $git.Source -C $ProjectRoot rev-parse --is-inside-work-tree 2>$null).Trim()
    if ($isRepository -ne "true") {
        Write-Host "[WARN] This folder is not a Git repository; keeping the current HTFA source."
        return
    }

    $branch = (& $git.Source -C $ProjectRoot branch --show-current 2>$null).Trim()
    if ($branch -ine "main") {
        Write-Host "[WARN] Current branch is '$branch'; skipping the HTFA update."
        return
    }

    $status = @(& $git.Source -C $ProjectRoot status --porcelain 2>$null)
    if ($status.Count -gt 0) {
        Write-Host "[WARN] Local HTFA changes were detected; skipping the HTFA update."
        return
    }

    Write-Host "[INFO] Updating HTFA from origin/main..."
    & $git.Source -C $ProjectRoot pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] HTFA update failed; continuing with the current source."
    }
    else {
        Write-Host "[OK] HTFA source is up to date."
    }
}

function Get-SystemPython {
    foreach ($name in @("python", "py")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandType -eq "Application" } |
            Select-Object -First 1
        if ($null -ne $command) {
            return $command.Source
        }
    }
    return $null
}

function Ensure-Runtime {
    if (Test-Path -LiteralPath $RuntimePython) {
        return
    }

    $systemPython = Get-SystemPython
    if ($null -eq $systemPython) {
        throw "No system Python was found to build the first project runtime."
    }
    Write-Host "[INFO] Bundled runtime was not found. Building it now..."
    & $systemPython -B (Join-Path $ProjectRoot "scripts\htfa.py") setup-runtime
    if ($LASTEXITCODE -ne 0) {
        throw "Project runtime setup failed."
    }
    if (-not (Test-Path -LiteralPath $RuntimePython)) {
        throw "Runtime setup completed without creating $RuntimePython."
    }
}

function Clear-PythonCaches {
    foreach ($root in @(
            (Join-Path $ProjectRoot "runtime"),
            (Join-Path $ProjectRoot "htfa"),
            $ProjectRoot
        )) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        Get-ChildItem -LiteralPath $root -Directory -Filter "__pycache__" -Recurse -Force `
            -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Watch {
    if ([string]::IsNullOrWhiteSpace($BrowserPath) -or
        [string]::IsNullOrWhiteSpace($BrowserDataDirectory)) {
        throw "The linked browser session metadata is incomplete."
    }

    try {
        while ($true) {
            $launcherAlive = $LauncherPid -le 0 -or (Test-ProcessAlive -ProcessId $LauncherPid)
            $backendAlive = Test-ProcessAlive -ProcessId $BackendPid
            $browserProcesses = @(Get-BrowserSessionProcessIds)

            if (-not $launcherAlive) {
                Write-SessionState -State "launcher_closed"
                Stop-ProcessTree -ProcessId $BackendPid
                Stop-BrowserSession
                break
            }
            if (-not $backendAlive) {
                Write-SessionState -State "backend_exited"
                Stop-BrowserSession
                break
            }
            if ($browserProcesses.Count -eq 0) {
                Write-SessionState -State "browser_closed"
                Stop-ProcessTree -ProcessId $BackendPid
                break
            }
            Start-Sleep -Milliseconds 500
        }
    }
    finally {
        Stop-BrowserSession
        if ($LauncherPid -gt 0 -and -not (Test-ProcessAlive -ProcessId $LauncherPid)) {
            Start-Sleep -Seconds 1
            Remove-SessionArtifacts
        }
    }
    return 0
}

function Invoke-Run {
    $selectedBrowser = Find-BrowserPath
    $sessionId = [Guid]::NewGuid().ToString("N")
    $sessionRoot = [IO.Path]::GetTempPath()
    $sessionBrowserDirectory = Join-Path $sessionRoot "HTFA-browser-$sessionId"
    $sessionStateFile = Join-Path $sessionRoot "HTFA-session-$sessionId.state"

    New-Item -ItemType Directory -Path $sessionBrowserDirectory -Force | Out-Null
    $script:BrowserPath = $selectedBrowser
    $script:BrowserDataDirectory = $sessionBrowserDirectory
    $script:StateFile = $sessionStateFile
    $script:LauncherPid = Get-LauncherProcessId

    $backend = $null
    $browserProcess = $null
    $watcher = $null
    try {
        $backendArguments = @(
            "-B",
            "scripts\htfa.py",
            "start"
        ) + @($StreamlitArguments) + @(
            "--server.port=$Port",
            "--server.headless=true"
        )
        Write-Host "[INFO] Starting HTFA backend on port $Port..."
        $backend = Start-Process -FilePath $RuntimePython `
            -ArgumentList (Join-ProcessArguments -Arguments $backendArguments) `
            -WorkingDirectory $ProjectRoot `
            -NoNewWindow `
            -PassThru
        $script:BackendPid = $backend.Id
        Wait-BackendReady -ProcessId $backend.Id

        $browserArguments = @(
            "--app=http://127.0.0.1:$Port",
            "--user-data-dir=$sessionBrowserDirectory",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--disable-background-mode"
        )
        Write-Host "[INFO] Opening linked browser window: $selectedBrowser"
        $browserProcess = Start-Process -FilePath $selectedBrowser `
            -ArgumentList (Join-ProcessArguments -Arguments $browserArguments) `
            -PassThru
        $script:BrowserPid = $browserProcess.Id

        $powershellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
        $watcherArguments = @(
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $PSCommandPath,
            "-Command",
            "Watch",
            "-ProjectRoot",
            $ProjectRoot,
            "-Port",
            [string]$Port,
            "-LauncherPid",
            [string]$script:LauncherPid,
            "-BackendPid",
            [string]$script:BackendPid,
            "-BrowserPid",
            [string]$script:BrowserPid,
            "-BrowserPath",
            $selectedBrowser,
            "-BrowserDataDirectory",
            $sessionBrowserDirectory,
            "-StateFile",
            $sessionStateFile
        )
        $watcher = Start-Process -FilePath $powershellPath `
            -ArgumentList (Join-ProcessArguments -Arguments $watcherArguments) `
            -WindowStyle Hidden `
            -PassThru

        while (Test-ProcessAlive -ProcessId $backend.Id) {
            Start-Sleep -Milliseconds 250
        }

        $backend.Refresh()
        $backendExitCode = $backend.ExitCode
        $sessionState = ""
        if (Test-Path -LiteralPath $sessionStateFile) {
            $sessionState = (Get-Content -LiteralPath $sessionStateFile -Raw).Trim()
        }
        if ($sessionState -in @("launcher_closed", "browser_closed", "backend_exited")) {
            return 0
        }
        return [int]$backendExitCode
    }
    catch {
        Write-Host "[ERROR] $($_.Exception.Message)"
        return 1
    }
    finally {
        if ($null -ne $watcher -and (Test-ProcessAlive -ProcessId $watcher.Id)) {
            Stop-ProcessTree -ProcessId $watcher.Id
        }
        if ($null -ne $backend -and (Test-ProcessAlive -ProcessId $backend.Id)) {
            Stop-ProcessTree -ProcessId $backend.Id
        }
        Stop-BrowserSession
        Remove-SessionArtifacts
    }
}

function Invoke-Stop {
    if (-not (Test-Path -LiteralPath $RuntimePython)) {
        throw "Bundled runtime was not found: $RuntimePython"
    }
    & $RuntimePython -B (Join-Path $ProjectRoot "scripts\htfa.py") stop `
        --port $Port `
        --wait-seconds $WaitSeconds
    return [int]$LASTEXITCODE
}

function Invoke-SetupRuntime {
    $systemPython = Get-SystemPython
    if ($null -eq $systemPython) {
        throw "No system Python was found to build the project runtime."
    }
    & $systemPython -B (Join-Path $ProjectRoot "scripts\htfa.py") setup-runtime
    return [int]$LASTEXITCODE
}

try {
    switch ($Command) {
        "Watch" { exit (Invoke-Watch) }
        "Stop" { exit (Invoke-Stop) }
        "SetupRuntime" { exit (Invoke-SetupRuntime) }
        "Start" {
            Write-Host "========================================"
            Write-Host "HTFA Dashboard Startup"
            Write-Host "========================================"
            Write-Host ""
            Invoke-RepositoryUpdate
            Ensure-Runtime
            Clear-PythonCaches
            if ([string]::IsNullOrWhiteSpace($env:HTFA_DEBUG_MODE)) {
                $env:HTFA_DEBUG_MODE = "true"
            }
            Write-Host "[INFO] Debug mode: $env:HTFA_DEBUG_MODE"
            Write-Host "[INFO] Checking Ts main before launch; offline mode uses the local version."
            exit (Invoke-Run)
        }
    }
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    exit 1
}
