param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$DataPath,

    [Parameter(Mandatory = $true)]
    [string]$SheetName
)

# Monthly wide-table writer for IMF PortWatch data.
# Two layouts, selected by payload:
#   - no "dimension_label"   -> standard monthly layout (A = month-end, B.. = indicators)
#   - with "dimension_label" -> dimension layout    (A = month-end, B = dimension, C.. = indicators)
# All Chinese text comes from the JSON payload (ensure_ascii=True), never from
# literals in this file, so script encoding is irrelevant.

$ErrorActionPreference = "Stop"
$excel = $null
$workbook = $null
$sheet = $null
$dictionarySheet = $null
$range = $null

try {
    $payload = Get-Content -Raw -LiteralPath $DataPath | ConvertFrom-Json
    $records = @(foreach ($record in $payload.records) { $record })
    $indicatorNames = @($payload.indicators | ForEach-Object { $_.name })
    $indicatorCount = $indicatorNames.Count

    $dimensionLabel = [string]$payload.dimension_label
    $hasDimension = -not [string]::IsNullOrWhiteSpace($dimensionLabel)

    $lastColumnIndex = 1 + $(if ($hasDimension) { 1 } else { 0 }) + $indicatorCount
    $lastColumnLetter = [char]([int][char]'A' + $lastColumnIndex - 1)
    $dimensionColumn = 1
    $firstIndicatorColumn = $(if ($hasDimension) { 2 } else { 1 })

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    $resolvedWorkbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
    $workbook = $excel.Workbooks.Open($resolvedWorkbook, 0, $false)
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

    $legacySheetNames = @($payload.legacy_sheet_names)
    foreach ($legacyName in $legacySheetNames) {
        if ([string]::IsNullOrWhiteSpace([string]$legacyName)) {
            continue
        }
        foreach ($candidate in @($workbook.Worksheets)) {
            if ($candidate.Name -eq $legacyName) {
                $candidate.Delete()
                [void][Runtime.InteropServices.Marshal]::ReleaseComObject($candidate)
                break
            }
        }
    }

    $sheet.Cells.Clear()
    $rowCount = $records.Count + 6
    $values = [object[,]]::new($rowCount, $lastColumnIndex)
    $sourceLabel = $payload.source_label
    if ($null -eq $sourceLabel -or [string]::IsNullOrWhiteSpace([string]$sourceLabel)) {
        $sourceLabel = $payload.source
    }
    $values[0, 0] = $sourceLabel
    $metadataLabels = @($payload.metadata_labels)
    for ($row = 0; $row -lt $metadataLabels.Count; $row++) {
        $values[($row + 1), 0] = $metadataLabels[$row]
    }

    if ($hasDimension) {
        $values[1, $dimensionColumn] = $dimensionLabel
        $values[2, $dimensionColumn] = $payload.frequency
        $values[3, $dimensionColumn] = ""
        $values[4, $dimensionColumn] = $payload.source
        $values[5, $dimensionColumn] = (
            [datetime]::ParseExact(
                $payload.updated_at,
                "yyyy-MM-dd",
                [Globalization.CultureInfo]::InvariantCulture
            ).ToOADate()
        )
    }

    for ($column = 0; $column -lt $indicatorCount; $column++) {
        $targetColumn = $column + $firstIndicatorColumn
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
        if ($hasDimension) {
            $values[($index + 6), $dimensionColumn] = $record.dimension
        }
        for ($column = 0; $column -lt $indicatorCount; $column++) {
            $value = $record.values[$column]
            if ($null -ne $value) {
                $values[($index + 6), ($column + $firstIndicatorColumn)] = [double]$value
            }
        }
    }

    $range = $sheet.Range(
        $sheet.Cells.Item(1, 1),
        $sheet.Cells.Item($rowCount, $lastColumnIndex)
    )
    $range.Value2 = $values
    $header = $sheet.Range("A2:$($lastColumnLetter)2")
    $header.Font.Bold = $true
    $header.Font.Color = 0xFFFFFF
    $header.Interior.Color = 0x784E1F
    $header.HorizontalAlignment = -4108
    $sheet.Range("B6:$($lastColumnLetter)6").NumberFormat = "yyyy-mm-dd"
    $sheet.Range("A7:A$rowCount").NumberFormat = "yyyy-mm"
    $sheet.Range("B7:$($lastColumnLetter)$rowCount").NumberFormat = "#,##0"
    $sheet.Columns.Item("A").ColumnWidth = 13
    if ($hasDimension) {
        $sheet.Columns.Item("B").ColumnWidth = 24
        $sheet.Columns.Item("C:$($lastColumnLetter)").ColumnWidth = 16
    } else {
        $sheet.Columns.Item("B:$($lastColumnLetter)").ColumnWidth = 42
    }

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

    $sheet.Activate()
    $excel.ActiveWindow.SplitColumn = 0
    $excel.ActiveWindow.SplitRow = 6
    $excel.ActiveWindow.FreezePanes = $true
    $workbook.Save()
    if (-not $workbook.Saved) {
        throw "Excel did not save the destination workbook: $resolvedWorkbook"
    }
}
finally {
    if ($null -ne $workbook) {
        $workbook.Close($false)
    }
    if ($null -ne $excel) {
        $excel.Quit()
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