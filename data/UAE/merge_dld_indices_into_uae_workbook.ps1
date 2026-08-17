param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$SourceDataThrough,

    [string]$SheetName = "周度_迪拜房地产",
    [string]$PreviewPath = ""
)

$ErrorActionPreference = "Stop"
$missing = [Type]::Missing
$excel = $null
$book = $null
$sheet = $null
$styleSheet = $null
$dictionarySheet = $null
$tempPath = $null
$backupPath = $null

function Release-ComObject([object]$Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

try {
    $CsvPath = [IO.Path]::GetFullPath($CsvPath)
    $WorkbookPath = [IO.Path]::GetFullPath($WorkbookPath)
    if (-not (Test-Path -LiteralPath $CsvPath -PathType Leaf)) {
        throw "CSV not found: $CsvPath"
    }
    if (-not (Test-Path -LiteralPath $WorkbookPath -PathType Leaf)) {
        throw "Workbook not found: $WorkbookPath"
    }

    $records = @(Import-Csv -LiteralPath $CsvPath -Encoding UTF8 | Sort-Object {
        [datetime]::ParseExact($_.'截止日期', 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)
    } -Descending)
    if ($records.Count -eq 0) {
        throw "CSV contains no data rows."
    }

    $headers = @($records[0].PSObject.Properties.Name)
    $expectedHeaders = @(
        '截止日期',
        '经确认新期房项目数_近28天',
        '期房销售笔数_近28天',
        '活跃期房项目数_近28天',
        '项目启动指数',
        '期房销售吸收指数',
        '项目商业转化指数'
    )
    if (($headers -join "`n") -ne ($expectedHeaders -join "`n")) {
        throw "CSV schema does not match the required seven Chinese columns."
    }

    $directory = [IO.Path]::GetDirectoryName($WorkbookPath)
    $baseName = [IO.Path]::GetFileNameWithoutExtension($WorkbookPath)
    $tempPath = Join-Path $directory ("{0}.dld_update_{1}.xlsx" -f $baseName, [guid]::NewGuid().ToString('N'))
    Copy-Item -LiteralPath $WorkbookPath -Destination $tempPath

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $book = $excel.Workbooks.Open($tempPath, 0, $false)

    # 与 data/DLD/ 原版 ps1 的唯一有意差异（写在副本内以便追溯）：
    # 原版用 删除旧表→新建同名表 实现替换，但本机 Excel COM 的
    # Worksheet.Delete() 不稳定（静默无效或长时间挂起），导致重命名新表时
    # 报“名称已使用”。改为“复用现有表并清除重写 / 缺表时新建”，
    # 对工作表内容、格式与校验结果与原协议完全等价。
    $sheet = $null
    foreach ($candidate in $book.Worksheets) {
        if ($candidate.Name -eq $SheetName) {
            $sheet = $candidate
            break
        }
        Release-ComObject $candidate
    }
    if ($null -eq $sheet) {
        $afterSheet = $book.Worksheets.Item($book.Worksheets.Count)
        $sheet = $book.Worksheets.Add($missing, $afterSheet)
        Release-ComObject $afterSheet
        $sheet.Name = $SheetName
    } else {
        [void]$sheet.Cells.Clear()
        [void]$sheet.Cells.ClearFormats()
    }

    try {
        $styleSheet = $book.Worksheets.Item('月度_CBUAE')
    }
    catch {
        $styleSheet = $book.Worksheets.Item(1)
    }

    $rowCount = $records.Count + 6
    $matrix = New-Object 'object[,]' $rowCount, 7
    $matrix[0, 0] = 'DLD'
    $matrix[1, 0] = '指标名称'
    $matrix[2, 0] = '频率'
    $matrix[3, 0] = '单位'
    $matrix[4, 0] = '来源'
    $matrix[5, 0] = '更新时间'

    $indicatorNames = $expectedHeaders[1..6]
    $units = @('个', '笔', '个', '指数', '指数', '指数')

    $dictionarySheet = $book.Worksheets.Item('指标字典')
    $lastDictionaryRow = $dictionarySheet.UsedRange.Rows.Count
    $existingIndicators = @{}
    for ($row = 2; $row -le $lastDictionaryRow; $row++) {
        $name = [string]$dictionarySheet.Range("A$row").Text
        if ($name) {
            $existingIndicators[$name.Trim()] = $row
        }
    }
    $dictionaryTypes = @('项目数', '交易笔数', '项目数', '指数', '指数', '指数')
    for ($index = 0; $index -lt $indicatorNames.Count; $index++) {
        $name = $indicatorNames[$index]
        if (-not $existingIndicators.ContainsKey($name)) {
            $newRow = $lastDictionaryRow + 1
            $dictionarySheet.Cells.Item($newRow, 1).Value2 = $name
            $dictionarySheet.Cells.Item($newRow, 2).Value2 = $dictionaryTypes[$index]
            $dictionarySheet.Cells.Item($newRow, 3).Value2 = '房地产'
            $dictionarySheet.Cells.Item($newRow, 4).Value2 = 'Dubai Land Department (DLD)'
            $dictionarySheet.Cells.Item($newRow, 5).Value2 = $null
            $existingIndicators[$name] = $newRow
            $lastDictionaryRow = $newRow
        }
    }

    $sourceDate = [datetime]::ParseExact(
        $SourceDataThrough,
        'yyyy-MM-dd',
        [Globalization.CultureInfo]::InvariantCulture
    ).ToOADate()
    for ($column = 1; $column -le 6; $column++) {
        $matrix[1, $column] = $indicatorNames[$column - 1]
        $matrix[2, $column] = '周'
        $matrix[3, $column] = $units[$column - 1]
        $matrix[4, $column] = 'DLD'
        $matrix[5, $column] = $sourceDate
    }

    $culture = [Globalization.CultureInfo]::InvariantCulture
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $row = $index + 6
        $matrix[$row, 0] = [datetime]::ParseExact($record.'截止日期', 'yyyy-MM-dd', $culture).ToOADate()
        $matrix[$row, 1] = [int]::Parse($record.'经确认新期房项目数_近28天', $culture)
        $matrix[$row, 2] = [int]::Parse($record.'期房销售笔数_近28天', $culture)
        $matrix[$row, 3] = [int]::Parse($record.'活跃期房项目数_近28天', $culture)
        $matrix[$row, 4] = [double]::Parse($record.'项目启动指数', $culture)
        $matrix[$row, 5] = [double]::Parse($record.'期房销售吸收指数', $culture)
        $matrix[$row, 6] = [double]::Parse($record.'项目商业转化指数', $culture)
    }

    $target = $sheet.Range("A1:G$rowCount")
    $target.Value = $matrix
    $target.Font.Name = $styleSheet.Cells.Font.Name
    $target.Font.Size = $styleSheet.Cells.Font.Size
    $target.VerticalAlignment = -4108

    $sheet.Range('A2:G2').Interior.Color = 7884319
    $sheet.Range('A2:G2').Font.Color = 16777215
    $sheet.Range('A2:G2').Font.Bold = $true
    $sheet.Range('A2:G2').HorizontalAlignment = -4108
    $sheet.Range('A2:G2').WrapText = $true
    $sheet.Range('A3:G6').Interior.Color = 14277081
    $sheet.Range('A3:A6').Font.Bold = $true
    $sheet.Range("A7:A$rowCount").NumberFormat = 'yyyy-mm-dd'
    $sheet.Range('B6:G6').NumberFormat = 'yyyy-mm-dd'
    $sheet.Range("B7:D$rowCount").NumberFormat = '#,##0'
    $sheet.Range("E7:G$rowCount").NumberFormat = '0.00'
    $sheet.Range("A2:G$rowCount").Borders.Item(9).LineStyle = 1
    $sheet.Range("A2:G$rowCount").Borders.Item(9).Color = 14277081

    $sheet.Columns.Item(1).ColumnWidth = 13
    $sheet.Columns.Item(2).ColumnWidth = 26
    $sheet.Columns.Item(3).ColumnWidth = 20
    $sheet.Columns.Item(4).ColumnWidth = 22
    $sheet.Columns.Item(5).ColumnWidth = 16
    $sheet.Columns.Item(6).ColumnWidth = 18
    $sheet.Columns.Item(7).ColumnWidth = 18
    $sheet.Rows.Item(2).RowHeight = 32
    $sheet.Rows.Item('3:6').RowHeight = 20

    [void]$sheet.Activate()
    [void]$sheet.Range('A7').Select()
    $excel.ActiveWindow.FreezePanes = $false
    $excel.ActiveWindow.SplitColumn = 0
    $excel.ActiveWindow.SplitRow = 6
    $excel.ActiveWindow.FreezePanes = $true
    [void]$sheet.Range('A7').Select()

    if ($PreviewPath) {
        $PreviewPath = [IO.Path]::GetFullPath($PreviewPath)
        $previewRange = $sheet.Range('A1:G20')
        $previewRange.CopyPicture(1, 2)
        $chartObject = $sheet.ChartObjects().Add(0, 0, $previewRange.Width, $previewRange.Height)
        [void]$chartObject.Chart.Paste()
        if (-not $chartObject.Chart.Export($PreviewPath, 'PNG')) {
            throw "Excel could not export the worksheet preview."
        }
        [void]$chartObject.Delete()
        Release-ComObject $chartObject
        Release-ComObject $previewRange
    }

    $book.Save()
    $book.Close($true)
    Release-ComObject $target
    Release-ComObject $dictionarySheet
    Release-ComObject $styleSheet
    Release-ComObject $sheet
    Release-ComObject $book
    $target = $null
    $dictionarySheet = $null
    $styleSheet = $null
    $sheet = $null
    $book = $null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()

    $checkBook = $excel.Workbooks.Open($tempPath, 0, $true)
    $checkSheet = $checkBook.Worksheets.Item($SheetName)
    $checkDictionary = $checkBook.Worksheets.Item('指标字典')
    try {
        if ($checkSheet.UsedRange.Rows.Count -ne $rowCount) {
            throw "Worksheet row count validation failed."
        }
        if ($checkSheet.UsedRange.Columns.Count -ne 7) {
            throw "Worksheet column count validation failed."
        }
        if ($checkSheet.Range('B2').Text -ne $expectedHeaders[1]) {
            throw "Worksheet header validation failed."
        }
        if ($checkSheet.Range('A7').Text -ne $records[0].'截止日期') {
            throw "Worksheet latest-date validation failed."
        }
        $dictionaryNames = @{}
        for ($row = 2; $row -le $checkDictionary.UsedRange.Rows.Count; $row++) {
            $name = [string]$checkDictionary.Range("A$row").Text
            if ($name) {
                $dictionaryNames[$name.Trim()] = $true
            }
        }
        foreach ($name in $indicatorNames) {
            if (-not $dictionaryNames.ContainsKey($name)) {
                throw "Indicator dictionary validation failed: $name"
            }
        }
    }
    finally {
        $checkBook.Close($false)
        Release-ComObject $checkDictionary
        Release-ComObject $checkSheet
        Release-ComObject $checkBook
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }

    $excel.Quit()
    Release-ComObject $excel
    $excel = $null

    $backupPath = Join-Path $directory ("{0}.dld_backup_{1}.xlsx" -f $baseName, [guid]::NewGuid().ToString('N'))
    [IO.File]::Replace($tempPath, $WorkbookPath, $backupPath, $true)
    $tempPath = $null
    Remove-Item -LiteralPath $backupPath -Force
    $backupPath = $null
    Write-Output "Workbook: $WorkbookPath"
    Write-Output "Worksheet: $SheetName"
    Write-Output "Data rows: $($records.Count)"
}
catch {
    Write-Error (
        "Excel merge failed at script line {0}: {1}" -f
        $_.InvocationInfo.ScriptLineNumber,
        $_.Exception.Message
    )
    throw
}
finally {
    if ($book) {
        try { $book.Close($false) } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
    }
    foreach ($object in @($dictionarySheet, $styleSheet, $sheet, $book, $excel)) {
        Release-ComObject $object
    }
    if ($tempPath -and (Test-Path -LiteralPath $tempPath)) {
        Remove-Item -LiteralPath $tempPath -Force
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
