<#
推  送  前  必  须  运  行  的  临  时  /  缓  存  清  理  器

删除仓库内所有临时/缓存/调试文件：Python 缓存、测试缓存、合并中间产物、
备份、残留在根目录的调试脚本与输出。

绝不删除真实数据：
  - data/UAE/uae.duckdb（Git LFS 推送的数据库）
  - data/UAE/阿联酋.xlsx（成品工作簿）
  - data/UAE/raw/**（原始数据，本地保留，不入库）
  - data/UAE/.env（密钥）、工作搜索热度.csv、users.db、sheet.txt
  - data/工业、data/暂存

用法（仓库根）：
  powershell -NoProfile -ExecutionPolicy Bypass -File tooling\scripts\clean_temps.ps1
  # 显式删除根目录 .cache 中的临时诊断脚本、截图和测试副本：
  powershell -NoProfile -ExecutionPolicy Bypass -File tooling\scripts\clean_temps.ps1 -IncludeAgentCache
#>
param([switch]$IncludeAgentCache)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$rootPrefix = $root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$pathComparison = if ([IO.Path]::DirectorySeparatorChar -eq '\') {
    [StringComparison]::OrdinalIgnoreCase
} else { [StringComparison]::Ordinal }
$protectedPaths = @(
    '.git', '.env', 'references-local', 'users.db', 'data\users.db', 'sheet.txt',
    'data\UAE\raw', 'data\UAE\.env', 'data\UAE\uae.duckdb',
    'data\UAE\阿联酋.xlsx', 'data\UAE\工作搜索热度.csv', 'data\工业', 'data\暂存'
) | ForEach-Object {
    [IO.Path]::GetFullPath((Join-Path $root $_.Replace('\', [string][IO.Path]::DirectorySeparatorChar)))
}
Set-Location $root

function Test-ProtectedPath([string]$path) {
    foreach ($protected in $protectedPaths) {
        if ($path.Equals($protected, $pathComparison) -or
            $path.StartsWith($protected + [IO.Path]::DirectorySeparatorChar, $pathComparison)) {
            return $true
        }
    }
    return $false
}

$deleted = @()
$deletedCount = 0
function Remove-ItemNow([string]$path, [switch]$Recurse) {
    $absolute = [IO.Path]::GetFullPath($path.Replace('\', [string][IO.Path]::DirectorySeparatorChar))
    if (-not $absolute.StartsWith($rootPrefix, $pathComparison)) {
        throw "Cleanup target is outside workspace or is the workspace root: $absolute"
    }
    if ((Test-ProtectedPath $absolute) -or -not (Test-Path -LiteralPath $absolute)) {
        return
    }
    # Reject links in the target's parent chain before any recursive deletion.
    $ancestor = $absolute
    while ($ancestor -ne $root) {
        $entry = Get-Item -LiteralPath $ancestor -Force
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Output "clean_temps: skipped linked path $absolute"
            return
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    if ($Recurse) {
        $pending = New-Object 'System.Collections.Generic.Stack[string]'
        $pending.Push($absolute)
        while ($pending.Count -gt 0) {
            foreach ($entry in (Get-ChildItem -LiteralPath $pending.Pop() -Force)) {
                if ((Test-ProtectedPath $entry.FullName) -or
                    ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    Write-Output "clean_temps: skipped tree with protected or linked child $absolute"
                    return
                }
                if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            }
        }
    }
    $script:deleted += $absolute
    $script:deletedCount++
    Remove-Item -LiteralPath $absolute -Recurse:$Recurse -Force
}

# 1) Python / 工具缓存目录（全仓递归）
foreach ($name in @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.ipynb_checkpoints', 'htmlcov')) {
    Get-ChildItem -Path $root -Directory -Filter $name -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-ProtectedPath $_.FullName) } |
        ForEach-Object { Remove-ItemNow $_.FullName -Recurse }
}
Remove-ItemNow (Join-Path $root '.coverage')

# 2) 数据管线临时目录与中间文件（data/UAE 内）
Remove-ItemNow (Join-Path $root 'data\UAE\backups') -Recurse
Remove-ItemNow (Join-Path $root 'data\UAE\processed') -Recurse
Remove-ItemNow (Join-Path $root 'data\UAE\.cache') -Recurse
Remove-ItemNow (Join-Path $root 'htfa\jobs\uae_data\backups') -Recurse
Remove-ItemNow (Join-Path $root 'htfa\jobs\uae_data\processed') -Recurse
Get-ChildItem -Path (Join-Path $root 'data\UAE') -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like '.mesteel-wide-*.csv' -or $_.Name -like '.dld_indices_*.csv' -or
        $_.Name -like '*.duckdb.wal' -or $_.Name -like '*.duckdb.tmp' -or
        $_.Name -match '^\.(portwatch-sheet|rta-monthly)-.*\.json$' -or
        $_.Name -match '^[0-9A-Fa-f]{8}(\.xlsx)?$'
    } |
    ForEach-Object { Remove-ItemNow $_.FullName }

# 3) 通用临时文件（全仓；跳过 .git / runtime / .venv / node_modules / raw / references-local）
Get-ChildItem -Path $root -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch '[/\\]\.git[/\\]|[/\\]runtime[/\\]|[/\\]\.venv[/\\]|[/\\]node_modules[/\\]|[/\\]data[/\\]UAE[/\\]raw[/\\]|[/\\]references-local[/\\]' -and
        ($_.Name -like '*.pyc' -or $_.Name -like '*.pyo' -or $_.Name -like '*.tmp' -or
         $_.Name -like '*.temp' -or $_.Name -like '*.log' -or $_.Name -like '*.cache' -or
         $_.Name -like '~$*')
    } |
    ForEach-Object { Remove-ItemNow $_.FullName }

# 4) 仓库根的调试残留（未跟踪的 _*.py / _*.ps1 / _*.json / _*.csv）
Get-ChildItem -Path $root -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like '_*' -and $_.Extension -in '.py', '.ps1', '.json', '.csv'
    } |
    Where-Object { -not (git ls-files -c -- $_.Name) } |
    ForEach-Object { Remove-ItemNow $_.FullName }

if ($IncludeAgentCache) {
    Remove-ItemNow (Join-Path $root '.cache') -Recurse
}

if ($deletedCount -eq 0) {
    Write-Output 'clean_temps: 没有需要清理的临时/缓存文件。'
}
else {
    Write-Output "clean_temps: 已删除 $deletedCount 个临时/缓存项："
    $deleted | ForEach-Object { Write-Output "  - $_" }
}
