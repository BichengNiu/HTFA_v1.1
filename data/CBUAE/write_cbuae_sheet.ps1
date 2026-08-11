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

try {
    $payload = Get-Content -Raw -LiteralPath $DataPath | ConvertFrom-Json
    $records = @(foreach ($record in $payload.records) { $record })
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    $resolvedWorkbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
    $workbook = $excel.Workbooks.Open($resolvedWorkbook, 0, $false)

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
    $columnCount = 5
    $values = [object[,]]::new($rowCount, $columnCount)
    $indicatorNames = @($payload.indicators | ForEach-Object { $_.name })
    $values[0, 0] = "CBUAE"
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
        for ($column = 0; $column -lt 4; $column++) {
            $values[($index + 6), ($column + 1)] = [double]$record.values[$column]
        }
    }

    $range = $sheet.Range(
        $sheet.Cells.Item(1, 1),
        $sheet.Cells.Item($rowCount, $columnCount)
    )
    $range.Value2 = $values
    $header = $sheet.Range("A2:E2")
    $header.Font.Bold = $true
    $header.Font.Color = 0xFFFFFF
    $header.Interior.Color = 0x784E1F
    $header.HorizontalAlignment = -4108
    $sheet.Range("B6:E6").NumberFormat = "yyyy-mm-dd"
    $sheet.Range("A7:A$rowCount").NumberFormat = "yyyy-mm"
    $sheet.Range("B7:E$rowCount").NumberFormat = "#,##0.000"
    $sheet.Columns.Item("A").ColumnWidth = 13
    $sheet.Columns.Item("B:E").ColumnWidth = 34

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
    for ($index = 0; $index -lt $indicatorNames.Count; $index++) {
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
