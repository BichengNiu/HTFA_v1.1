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
    $rowCount = $records.Count + 6
    $columnCount = 2

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
    $values[0, 0] = $payload.source_label
    $metadataLabels = @($payload.metadata_labels)
    for ($row = 0; $row -lt $metadataLabels.Count; $row++) {
        $values[($row + 1), 0] = $metadataLabels[$row]
    }
    $values[1, 1] = $payload.indicator.name
    $values[2, 1] = $payload.frequency
    $values[3, 1] = $payload.unit
    $values[4, 1] = $payload.source
    $values[5, 1] = (
        [datetime]::ParseExact(
            $payload.updated_at,
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        ).ToOADate()
    )

    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $monthStart = [datetime]::ParseExact(
            "$($record.period)-01",
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        )
        $values[($index + 6), 0] = $monthStart.AddMonths(1).AddDays(-1).ToOADate()
        $values[($index + 6), 1] = [double]$record.value
    }

    $range = $sheet.Range(
        $sheet.Cells.Item(1, 1),
        $sheet.Cells.Item($rowCount, $columnCount)
    )
    $range.Value2 = $values
    $header = $sheet.Range("A2:B2")
    $header.Font.Bold = $true
    $header.Font.Color = 0xFFFFFF
    $header.Interior.Color = 0x784E1F
    $header.HorizontalAlignment = -4108
    $sheet.Range("B6:B6").NumberFormat = "yyyy-mm-dd"
    $sheet.Range("A7:A$rowCount").NumberFormat = "yyyy-mm"
    $sheet.Range("B7:B$rowCount").NumberFormat = "0.0"
    $sheet.Columns.Item("A").ColumnWidth = 13
    $sheet.Columns.Item("B").ColumnWidth = 38

    $dictionarySheet = $workbook.Worksheets.Item($payload.dictionary_sheet_name)
    $lastDictionaryRow = $dictionarySheet.Cells.Item(
        $dictionarySheet.Rows.Count,
        1
    ).End(-4162).Row
    $indicatorRow = $null
    for ($row = 2; $row -le $lastDictionaryRow; $row++) {
        $name = [string]$dictionarySheet.Cells.Item($row, 1).Value2
        if ($name -eq $payload.indicator.name) {
            if ($null -ne $indicatorRow) {
                throw "Duplicate indicator dictionary entry: $name"
            }
            $indicatorRow = $row
        }
    }
    if ($null -eq $indicatorRow) {
        $indicatorRow = $lastDictionaryRow + 1
        $dictionarySheet.Cells.Item($indicatorRow, 1).Value2 = $payload.indicator.name
    }
    $dictionarySheet.Cells.Item($indicatorRow, 2).Value2 = $payload.indicator.type
    $dictionarySheet.Cells.Item($indicatorRow, 3).Value2 = $payload.indicator.industry
    $dictionarySheet.Cells.Item($indicatorRow, 4).Value2 = $payload.source

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
