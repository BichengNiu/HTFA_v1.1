[CmdletBinding()]
param(
    [ValidateSet("Run", "Watch")]
    [string]$Mode = "Run",
    [string]$ProjectRoot,
    [string]$RuntimePython,
    [int]$Port = 8501,
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

    # The initial browser PID covers the short interval before WMI exposes the
    # complete Chromium process tree.
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
    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $resolvedRuntimePython = (Resolve-Path -LiteralPath $RuntimePython).Path
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
        $backend = Start-Process -FilePath $resolvedRuntimePython `
            -ArgumentList (Join-ProcessArguments -Arguments $backendArguments) `
            -WorkingDirectory $resolvedProjectRoot `
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
            "-Mode",
            "Watch",
            "-ProjectRoot",
            $resolvedProjectRoot,
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

if ($Mode -eq "Watch") {
    exit (Invoke-Watch)
}
exit (Invoke-Run)
