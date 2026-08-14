param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$WideCsvPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$targetSheetName = "月度_MEsteel"
$dictionarySheetName = "指标字典"
$templateSheetName = "月度_CBUAE"
$sourceLabel = "MEsteel（CFR/CPT UAE）"
$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$processedDir = Join-Path $baseDir "processed"
$backupDir = Join-Path $baseDir "backups"
$qualityPath = Join-Path $processedDir "quality_report.json"
$reportPath = Join-Path $processedDir "workbook_merge_report.json"

$WorkbookPath = [IO.Path]::GetFullPath($WorkbookPath)
$WideCsvPath = [IO.Path]::GetFullPath($WideCsvPath)
$lockPath = Join-Path (Split-Path -Parent $WorkbookPath) (
    "~$" + [IO.Path]::GetFileName($WorkbookPath)
)
if (Test-Path -LiteralPath $lockPath) {
    throw "Close Excel before updating the workbook: $lockPath"
}
foreach ($required in @($WorkbookPath, $WideCsvPath, $qualityPath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file not found: $required"
    }
}

$rows = @(Import-Csv -LiteralPath $WideCsvPath -Encoding UTF8)
if ($rows.Count -eq 0) {
    throw "MEsteel wide CSV is empty"
}
$headers = @($rows[0].PSObject.Properties.Name)
if ($headers[0] -ne "month_end" -or $headers.Count -ne 16) {
    throw "MEsteel wide CSV must contain month_end plus 15 indicators"
}
$indicators = @($headers[1..($headers.Count - 1)])
$quality = Get-Content -Raw -Encoding UTF8 -LiteralPath $qualityPath |
    ConvertFrom-Json
$updatedAt = [datetime]::Parse($quality.generated_at).Date

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
New-Item -ItemType Directory -Force -Path $processedDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $backupDir (
    "阿联酋_before_MEsteel_$stamp.xlsx"
)
$temporaryPath = Join-Path (Split-Path -Parent $WorkbookPath) (
    [IO.Path]::GetFileNameWithoutExtension($WorkbookPath) +
    ".mesteel.tmp.xlsx"
)
Copy-Item -LiteralPath $WorkbookPath -Destination $backupPath
Remove-Item -LiteralPath $temporaryPath -ErrorAction SilentlyContinue

$excel = $null
$book = $null
$checkBook = $null
$dictionary = $null
$template = $null
$target = $null
$sheetNamesBefore = @()
$added = 0
$updated = 0
$savedCopy = $false

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $book = $excel.Workbooks.Open($WorkbookPath, 0, $false)

    foreach ($worksheet in $book.Worksheets) {
        if ($worksheet.Name -ne $targetSheetName) {
            $sheetNamesBefore += $worksheet.Name
        }
    }
    if ($book.Worksheets.Item(1).Name -ne $dictionarySheetName) {
        throw "指标字典 must remain the first worksheet"
    }
    $dictionary = $book.Worksheets.Item($dictionarySheetName)
    $template = $book.Worksheets.Item($templateSheetName)

    $expectedHeaders = @("指标名称", "类型", "行业", "数据来源", "预测变量")
    for ($column = 1; $column -le 5; $column++) {
        if ($dictionary.Cells.Item(1, $column).Text -ne $expectedHeaders[$column - 1]) {
            throw "Unexpected indicator dictionary header in column $column"
        }
    }

    $lastDictionaryRow = $dictionary.Cells.Item(
        $dictionary.Rows.Count,
        1
    ).End(-4162).Row
    $dictionaryRows = @{}
    for ($row = 2; $row -le $lastDictionaryRow; $row++) {
        $name = [string]$dictionary.Cells.Item($row, 1).Value2
        if ($name) {
            if ($dictionaryRows.ContainsKey($name)) {
                throw "Duplicate indicator dictionary entry: $name"
            }
            $dictionaryRows[$name] = $row
        }
    }

    foreach ($indicator in $indicators) {
        if ($dictionaryRows.ContainsKey($indicator)) {
            $row = [int]$dictionaryRows[$indicator]
            $updated++
        }
        else {
            $row = ++$lastDictionaryRow
            $sourceRange = $dictionary.Range(
                "A$($row - 1):G$($row - 1)"
            )
            $destinationRange = $dictionary.Range("A$row:G$row")
            $sourceRange.Copy($destinationRange) | Out-Null
            $added++
        }
        $dictionary.Cells.Item($row, 1).Value2 = $indicator
        $dictionary.Cells.Item($row, 2).Value2 = "价格"
        $dictionary.Cells.Item($row, 3).Value2 = "钢铁"
        $dictionary.Cells.Item($row, 4).Value2 = "MEsteel"
        $dictionary.Cells.Item($row, 5).ClearContents() | Out-Null
    }

    foreach ($worksheet in @($book.Worksheets)) {
        if ($worksheet.Name -eq $targetSheetName) {
            $worksheet.Delete()
            break
        }
    }
    $target = $book.Worksheets.Add(
        [Type]::Missing,
        $book.Worksheets.Item($book.Worksheets.Count)
    )
    $target.Name = $targetSheetName

    $template.Range("A1").Copy($target.Range("A1")) | Out-Null
    $target.Range("A1").Value2 = "MEsteel"
    foreach ($rowNumber in 2..6) {
        $template.Cells.Item($rowNumber, 1).Copy(
            $target.Cells.Item($rowNumber, 1)
        ) | Out-Null
        $template.Cells.Item($rowNumber, 2).Copy(
            $target.Range(
                $target.Cells.Item($rowNumber, 2),
                $target.Cells.Item($rowNumber, 16)
            )
        ) | Out-Null
    }
    $target.Cells.Item(2, 1).Value2 = "指标名称"
    $target.Cells.Item(3, 1).Value2 = "频率"
    $target.Cells.Item(4, 1).Value2 = "单位"
    $target.Cells.Item(5, 1).Value2 = "来源"
    $target.Cells.Item(6, 1).Value2 = "更新时间"
    for ($column = 2; $column -le 16; $column++) {
        $target.Cells.Item(2, $column).Value2 = $indicators[$column - 2]
        $target.Cells.Item(3, $column).Value2 = "月"
        $target.Cells.Item(4, $column).Value2 = "美元/吨"
        $target.Cells.Item(5, $column).Value2 = $sourceLabel
        $target.Cells.Item(6, $column).Value2 = $updatedAt.ToString(
            "yyyy-MM-dd"
        )
    }
    $target.Range("B6:P6").NumberFormat = "yyyy-mm-dd"

    $lastDataRow = $rows.Count + 6
    $template.Range("A7").Copy(
        $target.Range("A7:A$lastDataRow")
    ) | Out-Null
    $template.Range("B7").Copy(
        $target.Range("B7:P$lastDataRow")
    ) | Out-Null
    $matrix = New-Object "object[,]" $rows.Count, 16
    for ($rowIndex = 0; $rowIndex -lt $rows.Count; $rowIndex++) {
        $matrix[$rowIndex, 0] = [datetime]::ParseExact(
            $rows[$rowIndex].month_end,
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        ).ToOADate()
        for ($columnIndex = 1; $columnIndex -lt 16; $columnIndex++) {
            $value = [string]$rows[$rowIndex].($headers[$columnIndex])
            $matrix[$rowIndex, $columnIndex] = if ($value) {
                [double]::Parse(
                    $value,
                    [Globalization.CultureInfo]::InvariantCulture
                )
            }
            else {
                $null
            }
        }
    }
    $dataRange = $target.Range("A7:P$lastDataRow")
    $dataRange.Value = $matrix
    $target.Range("A7:A$lastDataRow").NumberFormat = "yyyy-mm"
    $target.Range("B7:P$lastDataRow").NumberFormat = "#,##0.00"
    $target.Columns.Item(1).ColumnWidth = $template.Columns.Item(1).ColumnWidth
    $target.Range("B:P").ColumnWidth = 36
    $target.Rows.Item(2).RowHeight = 60
    $target.Range("A2:P2").WrapText = $true

    $target.Activate() | Out-Null
    $excel.ActiveWindow.SplitColumn = 0
    $excel.ActiveWindow.SplitRow = 6
    $excel.ActiveWindow.FreezePanes = $true
    $book.SaveCopyAs($temporaryPath)
    $savedCopy = $true
    $book.Close($false)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book)
    $book = $null

    $checkBook = $excel.Workbooks.Open($temporaryPath, 0, $true)
    $actualSheetNames = @()
    foreach ($worksheet in $checkBook.Worksheets) {
        if ($worksheet.Name -ne $targetSheetName) {
            $actualSheetNames += $worksheet.Name
        }
    }
    if (($actualSheetNames -join "`n") -ne ($sheetNamesBefore -join "`n")) {
        throw "Existing worksheet order changed during MEsteel merge"
    }
    $checkTarget = $checkBook.Worksheets.Item($targetSheetName)
    if ($checkTarget.UsedRange.Rows.Count -ne $lastDataRow) {
        throw "Unexpected MEsteel worksheet row count"
    }
    if ($checkTarget.UsedRange.Columns.Count -ne 16) {
        throw "Unexpected MEsteel worksheet column count"
    }

    $actualMatrix = $checkTarget.Range("A7:P$lastDataRow").Value2
    for ($rowIndex = 0; $rowIndex -lt $rows.Count; $rowIndex++) {
        for ($columnIndex = 0; $columnIndex -lt 16; $columnIndex++) {
            $expectedValue = $matrix[$rowIndex, $columnIndex]
            $actualValue = $actualMatrix[
                ($rowIndex + 1), ($columnIndex + 1)
            ]
            if ($null -eq $expectedValue) {
                if ($null -ne $actualValue -and [string]$actualValue) {
                    throw (
                        "Unexpected MEsteel value at data row " +
                        "$($rowIndex + 1), column $($columnIndex + 1)"
                    )
                }
                continue
            }
            if ([double]$actualValue -ne [double]$expectedValue) {
                throw (
                    "MEsteel value validation failed at data row " +
                    "$($rowIndex + 1), column $($columnIndex + 1)"
                )
            }
        }
    }
    $checkBook.Close($false)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($checkBook)
    $checkBook = $null
}
catch {
    if ($checkBook) {
        $checkBook.Close($false)
    }
    if ($book) {
        $book.Close($false)
    }
    if ($savedCopy) {
        Remove-Item -LiteralPath $temporaryPath -ErrorAction SilentlyContinue
    }
    throw
}
finally {
    if ($excel) {
        $excel.Quit()
    }
    foreach ($comObject in @(
        $target,
        $template,
        $dictionary,
        $checkBook,
        $book,
        $excel
    )) {
        if ($comObject) {
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($comObject)
        }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Move-Item -LiteralPath $temporaryPath -Destination $WorkbookPath -Force
$report = [ordered]@{
    merged_at = (Get-Date).ToString("s")
    writer = "Microsoft Excel COM"
    workbook = $WorkbookPath
    backup = $backupPath
    target_sheet = $targetSheetName
    target_rows = $rows.Count + 6
    target_columns = 16
    indicator_count = $indicators.Count
    dictionary_rows_added = $added
    dictionary_rows_updated = $updated
    existing_sheet_count_preserved = $sheetNamesBefore.Count
}
$report | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $reportPath
Write-Output $WorkbookPath
