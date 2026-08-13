param(
    [string]$SourceWorkbook = "",
    [string]$OutputWorkbook = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$monthlyCsv = Join-Path $scriptRoot "processed\uae_imports_monthly.csv"
$backupRoot = Join-Path $scriptRoot "backups"

if ([string]::IsNullOrWhiteSpace($SourceWorkbook)) {
    $books = @(Get-ChildItem -LiteralPath $dataRoot -Filter "*.xlsx" |
        Where-Object { -not $_.Name.StartsWith("~$") })
    if ($books.Count -ne 1) {
        throw "Expected one workbook in data/, found $($books.Count)."
    }
    $SourceWorkbook = $books[0].FullName
}
else {
    $SourceWorkbook = (Resolve-Path -LiteralPath $SourceWorkbook).Path
}

if ([string]::IsNullOrWhiteSpace($OutputWorkbook)) {
    $OutputWorkbook = $SourceWorkbook
}
else {
    $OutputWorkbook = [System.IO.Path]::GetFullPath($OutputWorkbook)
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path -LiteralPath $OutputWorkbook) {
    $outputItem = Get-Item -LiteralPath $OutputWorkbook
    $backupPath = Join-Path $backupRoot (
        "$($outputItem.BaseName)_before_native_merge_$stamp.xlsx"
    )
    Copy-Item -LiteralPath $OutputWorkbook -Destination $backupPath
}

$rows = @(Import-Csv -LiteralPath $monthlyCsv -Encoding UTF8)
$temporary = Join-Path $scriptRoot (
    "native_merge_" + [guid]::NewGuid().ToString("N") + ".xlsx"
)
$missing = [System.Type]::Missing
$excel = $null
$workbook = $null

function Convert-NullableDouble([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    return [double]::Parse(
        $text,
        [System.Globalization.CultureInfo]::InvariantCulture
    )
}

function Add-WorksheetAfterLast($book, [string]$name) {
    $after = $book.Worksheets.Item($book.Worksheets.Count)
    $sheet = $book.Worksheets.Add($missing, $after, 1, $missing)
    $sheet.Name = $name
    return $sheet
}

function Delete-WorksheetIfPresent($book, [string]$name) {
    $sheet = $null
    try {
        $sheet = $book.Worksheets.Item($name)
    }
    catch {
        $sheet = $null
    }
    if ($null -ne $sheet) {
        $sheet.Delete()
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet) |
            Out-Null
    }
}

function Style-Header($range) {
    $range.Interior.Color = 7880223
    $range.Font.Color = 16777215
    $range.Font.Bold = $true
    $range.HorizontalAlignment = -4108
    $range.VerticalAlignment = -4108
}

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $workbook = $excel.Workbooks.Open($SourceWorkbook, 0, $false)

    Delete-WorksheetIfPresent $workbook "月度_UNComtrade"
    Delete-WorksheetIfPresent $workbook "UNComtrade_口径"

    $dataSheet = Add-WorksheetAfterLast $workbook "月度_UNComtrade"
    $headers = @(
        "日期",
        "制造业设备进口:百万美元",
        "土木及基建施工设备进口:百万美元",
        "能源项目设备进口:百万美元",
        "钻探设备进口:百万美元",
        "港口及铁路专项设备进口:百万美元",
        "制造业设备进口:台/件",
        "土木及基建施工设备进口:台/件",
        "能源项目设备进口:台/件",
        "钻探设备进口:台/件",
        "港口及铁路专项设备进口:台/件"
    )
    $matrix = [object[,]]::new($rows.Count + 1, $headers.Count)
    for ($column = 0; $column -lt $headers.Count; $column++) {
        $matrix[0, $column] = $headers[$column]
    }
    for ($index = 0; $index -lt $rows.Count; $index++) {
        $row = $rows[$index]
        $year = [int]$row.month.Substring(0, 4)
        $month = [int]$row.month.Substring(4, 2)
        $monthEnd = [datetime]::new(
            $year,
            $month,
            [datetime]::DaysInMonth($year, $month)
        )
        $matrix[($index + 1), 0] = $monthEnd.ToOADate()
        $matrix[($index + 1), 1] = Convert-NullableDouble $row.manufacturing_equipment_usd_mn
        $matrix[($index + 1), 2] = Convert-NullableDouble $row.civil_construction_equipment_usd_mn
        $matrix[($index + 1), 3] = Convert-NullableDouble $row.energy_project_equipment_usd_mn
        $matrix[($index + 1), 4] = Convert-NullableDouble $row.drilling_equipment_usd_mn
        $matrix[($index + 1), 5] = Convert-NullableDouble $row.port_rail_equipment_usd_mn
        $matrix[($index + 1), 6] = Convert-NullableDouble $row.manufacturing_equipment_units
        $matrix[($index + 1), 7] = Convert-NullableDouble $row.civil_construction_equipment_units
        $matrix[($index + 1), 8] = Convert-NullableDouble $row.energy_project_equipment_units
        $matrix[($index + 1), 9] = Convert-NullableDouble $row.drilling_equipment_units
        $matrix[($index + 1), 10] = Convert-NullableDouble $row.port_rail_equipment_units
    }
    $dataRange = $dataSheet.Range(
        $dataSheet.Cells.Item(1, 1),
        $dataSheet.Cells.Item($rows.Count + 1, $headers.Count)
    )
    $dataRange.Value2 = $matrix
    $null = Style-Header $dataSheet.Range("A1:K1")
    $dataSheet.Range("A2:A$($rows.Count + 1)").NumberFormat = "yyyy-mm"
    $dataSheet.Range("B2:F$($rows.Count + 1)").NumberFormat = "#,##0.000"
    $dataSheet.Range("G2:K$($rows.Count + 1)").NumberFormat = "#,##0.000"
    $dataSheet.Columns.Item("A").ColumnWidth = 13
    $dataSheet.Columns.Item("B:K").ColumnWidth = 28
    $dataRange.AutoFilter() | Out-Null
    $dataSheet.Activate()
    $excel.ActiveWindow.SplitRow = 1
    $freezeResult = $excel.ActiveWindow.FreezePanes = $true

    $dictionary = $workbook.Worksheets.Item(1)
    $lastRow = $dictionary.Cells.Item(
        $dictionary.Rows.Count,
        1
    ).End(-4162).Row
    $obsolete = @(
        "阿联酋:进口:资本品:当月值",
        "阿联酋:进口:钢材及结构金属:当月值",
        "阿联酋:进口:工程及工业机械:当月值",
        "阿联酋:进口:水泥:当月值",
        "阿联酋:进口:能源大型项目设备:当月值"
    )
    for ($rowNumber = $lastRow; $rowNumber -ge 2; $rowNumber--) {
        $indicator = [string]$dictionary.Cells.Item($rowNumber, 1).Value2
        if ($obsolete -contains $indicator) {
            $null = $dictionary.Rows.Item($rowNumber).Delete()
        }
    }
    $lastRow = $dictionary.Cells.Item(
        $dictionary.Rows.Count,
        1
    ).End(-4162).Row
    $existing = @{}
    for ($rowNumber = 2; $rowNumber -le $lastRow; $rowNumber++) {
        $existing[[string]$dictionary.Cells.Item($rowNumber, 1).Value2] = $true
    }
    $entries = @(
        @("阿联酋:进口:制造业设备:当月值", "金额", "工业", "UN Comtrade"),
        @("阿联酋:进口:土木及基建施工设备:当月值", "金额", "建筑", "UN Comtrade"),
        @("阿联酋:进口:能源项目设备:当月值", "金额", "能源", "UN Comtrade"),
        @("阿联酋:进口:钻探设备:当月值", "金额", "能源", "UN Comtrade"),
        @("阿联酋:进口:港口及铁路专项设备:当月值", "金额", "基建", "UN Comtrade"),
        @("阿联酋:进口:制造业设备:台数:当月值", "数量", "工业", "UN Comtrade"),
        @("阿联酋:进口:土木及基建施工设备:台数:当月值", "数量", "建筑", "UN Comtrade"),
        @("阿联酋:进口:能源项目设备:台数:当月值", "数量", "能源", "UN Comtrade"),
        @("阿联酋:进口:钻探设备:台数:当月值", "数量", "能源", "UN Comtrade"),
        @("阿联酋:进口:港口及铁路专项设备:台数:当月值", "数量", "基建", "UN Comtrade")
    )
    foreach ($entry in $entries) {
        if ($existing.ContainsKey($entry[0])) {
            continue
        }
        $lastRow++
        $dictionary.Rows.Item($lastRow - 1).Copy()
        $dictionary.Rows.Item($lastRow).PasteSpecial(-4122)
        $dictionary.Range(
            $dictionary.Cells.Item($lastRow, 1),
            $dictionary.Cells.Item($lastRow, $dictionary.UsedRange.Columns.Count)
        ).ClearContents()
        for ($column = 0; $column -lt $entry.Count; $column++) {
            $dictionary.Cells.Item($lastRow, $column + 1).Value2 = $entry[$column]
        }
    }

    $workbook.SaveAs($temporary, 51)
    $workbook.Close($false)
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook) |
        Out-Null
    $workbook = $null
}
finally {
    if ($null -ne $workbook) {
        $workbook.Close($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook) |
            Out-Null
    }
    if ($null -ne $excel) {
        $excel.Quit()
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) |
            Out-Null
    }
    [gc]::Collect()
    [gc]::WaitForPendingFinalizers()
}

if (-not (Test-Path -LiteralPath $temporary)) {
    throw "Excel did not create the temporary workbook."
}

for ($attempt = 0; $attempt -lt 12; $attempt++) {
    try {
        if (Test-Path -LiteralPath $OutputWorkbook) {
            $replaceBackup = Join-Path $scriptRoot (
                "replace_backup_" + [guid]::NewGuid().ToString("N") + ".xlsx"
            )
            [System.IO.File]::Replace(
                $temporary,
                $OutputWorkbook,
                $replaceBackup,
                $true
            )
            [System.IO.File]::Delete($replaceBackup)
        }
        else {
            [System.IO.File]::Move($temporary, $OutputWorkbook)
        }
        Write-Output $OutputWorkbook
        exit 0
    }
    catch [System.IO.IOException] {
        if ($attempt -eq 11) {
            throw
        }
        Start-Sleep -Milliseconds ([math]::Min(10000, 500 * ($attempt + 1)))
    }
}
