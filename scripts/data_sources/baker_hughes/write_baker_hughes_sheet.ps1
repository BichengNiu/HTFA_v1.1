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
$header = $null

try {
    $payload = Get-Content -Raw -LiteralPath $DataPath | ConvertFrom-Json
    $records = @(foreach ($record in $payload.records) { $record })
    $indicators = @($payload.indicators)
    $indicatorNames = @($indicators | ForEach-Object { $_.name })
    $columnCount = $indicatorNames.Count + 1
    $rowCount = $records.Count + 6

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

    $sheet.Cells.Clear()
    $values = [object[,]]::new($rowCount, $columnCount)
    $values[0, 0] = "Baker Hughes"
    $metadataLabels = @($payload.metadata_labels)
    for ($row = 0; $row -lt $metadataLabels.Count; $row++) {
        $values[($row + 1), 0] = $metadataLabels[$row]
    }
    for ($column = 0; $column -lt $indicatorNames.Count; $column++) {
        $targetColumn = $column + 1
        $values[1, $targetColumn] = $indicatorNames[$column]
        $values[2, $targetColumn] = $payload.frequency
        $values[3, $targetColumn] = $payload.unit
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
        for ($column = 0; $column -lt $indicatorNames.Count; $column++) {
            $values[($index + 6), ($column + 1)] = [double]$record.values[$column]
        }
    }

    $range = $sheet.Range(
        $sheet.Cells.Item(1, 1),
        $sheet.Cells.Item($rowCount, $columnCount)
    )
    $range.Value2 = $values
    $lastColumn = $sheet.Cells.Item(1, $columnCount).Address($false, $false) -replace '\d', ''
    $header = $sheet.Range("A2:${lastColumn}2")
    $header.Font.Bold = $true
    $header.Font.Color = 0xFFFFFF
    $header.Interior.Color = 0x784E1F
    $header.HorizontalAlignment = -4108
    $sheet.Range("B6:${lastColumn}6").NumberFormat = "yyyy-mm-dd"
    $sheet.Range("A7:A$rowCount").NumberFormat = "yyyy-mm"
    $sheet.Range("B7:${lastColumn}$rowCount").NumberFormat = "#,##0"
    $sheet.Columns.Item("A").ColumnWidth = 13
    $sheet.Range("B:${lastColumn}").ColumnWidth = 23

    $dictionarySheet = $workbook.Worksheets.Item($payload.dictionary_sheet_name)
    $lastDictionaryRow = $dictionarySheet.Cells.Item(
        $dictionarySheet.Rows.Count,
        1
    ).End(-4162).Row
    $obsoleteIndicators = @($payload.obsolete_indicators)
    for ($row = $lastDictionaryRow; $row -ge 2; $row--) {
        $name = [string]$dictionarySheet.Cells.Item($row, 1).Value2
        if ($obsoleteIndicators -contains $name) {
            $dictionarySheet.Rows.Item($row).Delete()
        }
    }
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
    for ($index = 0; $index -lt $indicatorNames.Count; $index++) {
        $name = $indicatorNames[$index]
        if (-not $knownIndicators.ContainsKey($name)) {
            $lastDictionaryRow++
            $dictionarySheet.Cells.Item($lastDictionaryRow, 1).Value2 = $name
            $dictionarySheet.Cells.Item($lastDictionaryRow, 2).Value2 = $indicators[$index].type
            $dictionarySheet.Cells.Item($lastDictionaryRow, 3).Value2 = $indicators[$index].industry
            $dictionarySheet.Cells.Item($lastDictionaryRow, 4).Value2 = $payload.source
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
        $header,
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
