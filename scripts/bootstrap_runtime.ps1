[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-ExactProjectTarget {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Expected
    )

    $projectFullPath = [System.IO.Path]::GetFullPath($ProjectRoot)
    $targetFullPath = [System.IO.Path]::GetFullPath($Target)
    $expectedFullPath = [System.IO.Path]::GetFullPath($Expected)
    $projectPrefix = $projectFullPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $targetFullPath.StartsWith(
        $projectPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unsafe generated target outside project: $targetFullPath"
    }
    if (-not $targetFullPath.Equals(
        $expectedFullPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unexpected generated target: $targetFullPath"
    }
    return $targetFullPath
}

function Remove-GeneratedDirectory {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    if (Test-Path -LiteralPath $LiteralPath) {
        Remove-Item -LiteralPath $LiteralPath -Recurse -Force
    }
}

function Download-VerifiedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    try {
        Invoke-WebRequest `
            -Uri $Uri `
            -OutFile $Destination `
            -UseBasicParsing `
            -TimeoutSec 60
        $actualSha256 = (Get-FileHash `
            -LiteralPath $Destination `
            -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        if ($actualSha256 -ne $ExpectedSha256.ToLowerInvariant()) {
            throw "SHA-256 mismatch for $Destination"
        }
    }
    catch {
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Force
        }
        throw
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath"
        }
    }
    finally {
        Pop-Location
    }
}

function Restore-RuntimeBackup {
    param(
        [Parameter(Mandatory = $true)][string]$RuntimePath,
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][bool]$CandidateMoved,
        [Parameter(Mandatory = $true)][bool]$PreviousRuntimeMoved
    )

    if ($CandidateMoved -and (Test-Path -LiteralPath $RuntimePath)) {
        Remove-GeneratedDirectory -LiteralPath $RuntimePath
    }
    if ($PreviousRuntimeMoved -and (Test-Path -LiteralPath $BackupPath)) {
        Move-Item -LiteralPath $BackupPath -Destination $RuntimePath
    }
}

$projectRootPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$downloadRootPath = Resolve-ExactProjectTarget `
    -ProjectRoot $projectRootPath `
    -Target (Join-Path $projectRootPath "build\portable") `
    -Expected (Join-Path $projectRootPath "build\portable")
$candidateRootPath = Resolve-ExactProjectTarget `
    -ProjectRoot $projectRootPath `
    -Target (Join-Path $projectRootPath "build\runtime-candidate") `
    -Expected (Join-Path $projectRootPath "build\runtime-candidate")
$backupRootPath = Resolve-ExactProjectTarget `
    -ProjectRoot $projectRootPath `
    -Target (Join-Path $projectRootPath "build\runtime-backup") `
    -Expected (Join-Path $projectRootPath "build\runtime-backup")
$runtimeRootPath = Resolve-ExactProjectTarget `
    -ProjectRoot $projectRootPath `
    -Target (Join-Path $projectRootPath "runtime") `
    -Expected (Join-Path $projectRootPath "runtime")

if (Test-Path -LiteralPath $backupRootPath) {
    if (Test-Path -LiteralPath $runtimeRootPath) {
        Remove-GeneratedDirectory -LiteralPath $backupRootPath
    }
    else {
        Move-Item -LiteralPath $backupRootPath -Destination $runtimeRootPath
    }
}
Remove-GeneratedDirectory -LiteralPath $downloadRootPath
Remove-GeneratedDirectory -LiteralPath $candidateRootPath
New-Item -ItemType Directory -Path $downloadRootPath | Out-Null
New-Item -ItemType Directory -Path $candidateRootPath | Out-Null

$specPath = Join-Path $projectRootPath "scripts\portable_runtime.json"
$spec = Get-Content -LiteralPath $specPath -Raw -Encoding UTF8 | ConvertFrom-Json
$pythonArchivePath = Join-Path `
    $downloadRootPath `
    "python-3.13.4-embed-amd64.zip"
$pipWheelPath = Join-Path `
    $downloadRootPath `
    "pip-$($spec.pip_version)-py3-none-any.whl"

Download-VerifiedFile `
    -Uri $spec.archive_url `
    -Destination $pythonArchivePath `
    -ExpectedSha256 $spec.archive_sha256
Download-VerifiedFile `
    -Uri $spec.pip_wheel_url `
    -Destination $pipWheelPath `
    -ExpectedSha256 $spec.pip_wheel_sha256

Expand-Archive `
    -LiteralPath $pythonArchivePath `
    -DestinationPath $candidateRootPath `
    -Force
$candidatePythonPath = Join-Path $candidateRootPath "python.exe"
if (-not (Test-Path -LiteralPath $candidatePythonPath -PathType Leaf)) {
    throw "Candidate Python was not extracted: $candidatePythonPath"
}

$builderPath = Join-Path $projectRootPath "scripts\build_portable.py"
Invoke-Checked `
    -FilePath $candidatePythonPath `
    -ArgumentList @(
        "-B",
        $builderPath,
        "--candidate-root",
        $candidateRootPath,
        "--pip-wheel",
        $pipWheelPath
    ) `
    -WorkingDirectory $projectRootPath

$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$previousCachePrefix = $env:PYTHONPYCACHEPREFIX
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $downloadRootPath "pycache"
try {
    Invoke-Checked `
        -FilePath $candidatePythonPath `
        -ArgumentList @(
            "-B", "-m", "pytest", "-q", "-c", "tooling\pytest.ini",
            "-p", "no:cacheprovider"
        ) `
        -WorkingDirectory $projectRootPath
    Invoke-Checked `
        -FilePath $candidatePythonPath `
        -ArgumentList @(
            "-B", "-m", "compileall", "-q", "app.py", "dashboard", "scripts"
        ) `
        -WorkingDirectory $projectRootPath
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
    $env:PYTHONPYCACHEPREFIX = $previousCachePrefix
}

$previousRuntimeMoved = $false
$candidateMoved = $false
try {
    if (Test-Path -LiteralPath $runtimeRootPath) {
        Move-Item -LiteralPath $runtimeRootPath -Destination $backupRootPath
        $previousRuntimeMoved = $true
    }
    Move-Item -LiteralPath $candidateRootPath -Destination $runtimeRootPath
    $candidateMoved = $true

    $activePythonPath = Join-Path $runtimeRootPath "python.exe"
    Invoke-Checked `
        -FilePath $activePythonPath `
        -ArgumentList @(
            "-B",
            "-c",
            "import streamlit, pandas, scipy, Ts; print('runtime smoke OK')"
        ) `
        -WorkingDirectory $projectRootPath
    Invoke-Checked `
        -FilePath $activePythonPath `
        -ArgumentList @("-B", "-m", "pip", "check") `
        -WorkingDirectory $projectRootPath
}
catch {
    Restore-RuntimeBackup `
        -RuntimePath $runtimeRootPath `
        -BackupPath $backupRootPath `
        -CandidateMoved $candidateMoved `
        -PreviousRuntimeMoved $previousRuntimeMoved
    throw
}

if (Test-Path -LiteralPath $backupRootPath) {
    Remove-GeneratedDirectory -LiteralPath $backupRootPath
}
Write-Output "Unified runtime is ready at $runtimeRootPath"
