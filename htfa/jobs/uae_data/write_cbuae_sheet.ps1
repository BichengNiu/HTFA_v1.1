param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [Parameter(Mandatory = $true)]
    [string]$SheetName
)

$ErrorActionPreference = "Stop"
$excel = $null
$workbook = $null
$sheet = $null
$dictionarySheet = $null
$range = $null
$temporaryWorkbookPath = $null
$temporaryBackupPath = $null

try {
    $payload = Get-Content -Raw -LiteralPath $DataPath | ConvertFrom-Json
    $records = @(foreach ($record in $payload.records) { $record })
    $indicatorNames = @($payload.indicators | ForEach-Object { $_.name })
    $indicatorCount = $indicatorNames.Count
    # 末列（跳过 A 列日期）：B 为第 2 列，指标数即占用列数，最大字母索引 = 1 + indicatorCount
    $lastColumnIndex = 1 + $indicatorCount
    $lastColumnLetter = [char]([int][char]'A' + $lastColumnIndex - 1)

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    $resolvedWorkbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
    # Excel 16 on this workstation rejects the workbook's existing package
    # through the short Open overload.  The explicit overload with repair mode
    # opens the same workbook and preserves the existing sheets before the
    # requested sheet is rebuilt.
    $workbook = $excel.Workbooks.Open(
        $resolvedWorkbook,
        0,
        $false,
        5,
        '',
        '',
        $true,
        2,
        $null,
        $false,
        $false,
        $null,
        $false,
        $null,
        1
    )
    if ($workbook.ReadOnly) {
        throw "Destination workbook is open or read-only: $resolvedWorkbook"
    }

    foreach ($candidate in $workbook.Worksheets) {
        if ($candidate.Name -eq $SheetName) {
            $sheet = $candidate
            break
        }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($candidate)
    }

    if ($null -eq $sheet) {
        $lastSheet = $workbook.Worksheets.Item($workbook.Worksheets.Count)
        $sheet = $workbook.Worksheets.Add([Type]::Missing, $lastSheet)
        $sheet.Name = $SheetName
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($lastSheet)
    }

    $sheet.Cells.Clear()
    $rowCount = $records.Count + 6
    $columnCount = $lastColumnIndex
    $values = [object[,]]::new($rowCount, $columnCount)
    $values[0, 0] = $payload.source
    $metadataLabels = @($payload.metadata_labels)
    for ($row = 0; $row -lt $metadataLabels.Count; $row++) {
        $values[($row + 1), 0] = $metadataLabels[$row]
    }
    for ($column = 0; $column -lt $indicatorCount; $column++) {
        $targetColumn = $column + 1
        # 单位优先取单指标（支付表数量/金额单位不同）；缺省退回整体单位
        $perUnit = $payload.indicators[$column].unit
        if ($null -eq $perUnit -or [string]::IsNullOrWhiteSpace([string]$perUnit)) {
            $perUnit = $payload.unit
        }
        $values[1, $targetColumn] = $indicatorNames[$column]
        $values[2, $targetColumn] = $payload.frequency
        $values[3, $targetColumn] = $perUnit
        $values[4, $targetColumn] = $payload.source
        $values[5, $targetColumn] = (
            [datetime]::ParseExact(
                $payload.updated_at,
                "yyyy-MM-dd",
                [Globalization.CultureInfo]::InvariantCulture
            ).ToOADate()
        )
    }

    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $monthStart = [datetime]::ParseExact(
            "$($record.period)-01",
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        )
        $values[($index + 6), 0] = $monthStart.AddMonths(1).AddDays(-1).ToOADate()
        for ($column = 0; $column -lt $indicatorCount; $column++) {
            $value = $record.values[$column]
            if ($null -ne $value) {
                $values[($index + 6), ($column + 1)] = [double]$value
            }
        }
    }

    $range = $sheet.Range(
        $sheet.Cells.Item(1, 1),
        $sheet.Cells.Item($rowCount, $columnCount)
    )
    $range.Value2 = $values
    $header = $sheet.Range("A2:$($lastColumnLetter)2")
    $header.Font.Bold = $true
    $header.Font.Color = 0xFFFFFF
    $header.Interior.Color = 0x784E1F
    $header.HorizontalAlignment = -4108
    $sheet.Range("B6:$($lastColumnLetter)6").NumberFormat = "yyyy-mm-dd"
    $sheet.Range("A7:A$rowCount").NumberFormat = "yyyy-mm"
    $sheet.Range("B7:$($lastColumnLetter)$rowCount").NumberFormat = "#,##0.000"
    $sheet.Columns.Item("A").ColumnWidth = 13
    $sheet.Columns.Item("B:$($lastColumnLetter)").ColumnWidth = 34

    $dictionarySheet = $workbook.Worksheets.Item(
        $payload.dictionary_sheet_name
    )
    $lastDictionaryRow = $dictionarySheet.Cells.Item(
        $dictionarySheet.Rows.Count,
        1
    ).End(-4162).Row
    $knownIndicators = @{}
    for ($row = 2; $row -le $lastDictionaryRow; $row++) {
        $name = [string]$dictionarySheet.Cells.Item($row, 1).Value2
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            $knownIndicators[$name] = $true
        }
    }
    for ($index = 0; $index -lt $indicatorCount; $index++) {
        $name = $indicatorNames[$index]
        if (-not $knownIndicators.ContainsKey($name)) {
            $lastDictionaryRow++
            $dictionarySheet.Cells.Item($lastDictionaryRow, 1).Value2 = $name
            $dictionarySheet.Cells.Item($lastDictionaryRow, 2).Value2 = (
                $payload.indicators[$index].type
            )
            $dictionarySheet.Cells.Item($lastDictionaryRow, 3).Value2 = (
                $payload.indicators[$index].industry
            )
            $knownIndicators[$name] = $true
        }
    }

    # Keep the COM instance headless.  Activating a sheet can surface Excel's
    # automation window even when Application.Visible is false.
    # Repair-mode opens require SaveAs rather than the short Save property on
    # this Excel installation.  Save beside the target and replace it only
    # after Excel has closed the repaired package successfully.
    $temporaryWorkbookPath = "$resolvedWorkbook.wam-write.tmp.xlsx"
    if (Test-Path -LiteralPath $temporaryWorkbookPath) {
        Remove-Item -LiteralPath $temporaryWorkbookPath -Force
    }
    $workbook.SaveAs($temporaryWorkbookPath, 51)
    $workbook.Close($false)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
    $workbook = $null
    $excel.Quit()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    $excel = $null
    if (-not (Test-Path -LiteralPath $temporaryWorkbookPath)) {
        throw "Excel did not create the temporary workbook: $temporaryWorkbookPath"
    }
    # Windows PowerShell's Move-Item -Force does not reliably replace an
    # existing file on this workstation.  File.Replace performs the intended
    # same-volume atomic replacement after Excel has closed the package.
    $temporaryBackupPath = "$resolvedWorkbook.cbuae-write-backup.tmp.xlsx"
    if (Test-Path -LiteralPath $temporaryBackupPath) {
        Remove-Item -LiteralPath $temporaryBackupPath -Force
    }
    [System.IO.File]::Replace(
        $temporaryWorkbookPath,
        $resolvedWorkbook,
        $temporaryBackupPath,
        $true
    )
    if (Test-Path -LiteralPath $temporaryBackupPath) {
        Remove-Item -LiteralPath $temporaryBackupPath -Force
    }
    $temporaryBackupPath = $null
    $temporaryWorkbookPath = $null
}
finally {
    if ($null -ne $workbook) {
        $workbook.Close($false)
    }
    if ($null -ne $excel) {
        $excel.Quit()
    }
    if ($null -ne $temporaryWorkbookPath -and (Test-Path -LiteralPath $temporaryWorkbookPath)) {
        Remove-Item -LiteralPath $temporaryWorkbookPath -Force
    }
    if ($null -ne $temporaryBackupPath -and (Test-Path -LiteralPath $temporaryBackupPath)) {
        Remove-Item -LiteralPath $temporaryBackupPath -Force
    }
    foreach ($comObject in @(
        $range,
        $dictionarySheet,
        $sheet,
        $workbook,
        $excel
    )) {
        if ($null -ne $comObject) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($comObject)
        }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
