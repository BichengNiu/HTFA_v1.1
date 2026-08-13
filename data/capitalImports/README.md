# UAE classified equipment imports

This folder contains a reproducible UN Comtrade pipeline for five monthly UAE
equipment-import categories defined at HS6 level:

- Manufacturing equipment.
- Civil construction equipment.
- Large energy-project equipment.
- Drilling equipment.
- Port and rail equipment.

The 59 exact HS6 codes are recorded in `reference/commodity_scope.csv` and
documented in `UNComtrade_口径.md`. Deliberately excluded related codes are
recorded in `reference/commodity_scope_exclusions.csv`. The methodology
document also contains annual source counts, continuous source ranges and a
complete month-by-month source ledger.

## Source priority

Source selection is performed separately for every month and category:

1. If the UAE reports an import value for the category, use only the UAE value.
2. Otherwise, sum exports to the UAE reported by every individual country.
3. Never restrict the mirror source to a fixed number of partner countries.
4. Keep a mirror value whenever at least one reporter has data; leave it blank
   only when no reporter has data for that category and month.

Values are monthly observations. No rolling average or rolling sum is applied.

## Run

From this folder, use the project runtime:

```powershell
..\..\runtime\python.exe download_comtrade.py
..\..\runtime\python.exe process_and_merge.py
..\..\runtime\python.exe validate_outputs.py
```

The downloader resumes from cached JSON files. Use `--force` to refresh them.
It reads the key from `COMTRADE_API_KEY` or `.env` beside the script.

On Windows, processing calls `merge_with_excel.ps1` so Excel itself preserves
the workbook's comments, print settings, formulas and links.

## Outputs

- `raw/equipment_uae_reported/`: UAE-reported monthly imports.
- `raw/equipment_all_mirror/`: exports to the UAE from all reporters.
- `reference/commodity_scope.csv`: auditable HS6 classification.
- `processed/uae_imports_monthly.csv`: category-level monthly series.
- `processed/mirror_partner_detail.csv`: reporter contributions when mirror
  data is used.
- `processed/quantity_source_detail.csv`: HS6-level selected item counts,
  source, reported/estimated split and mirror reporter count.
- `processed/quality_report.json`: validation and source-coverage results.
- `../阿联酋.xlsx`: updated `月度_UNComtrade` worksheet.

Credentials, raw data, processed extracts and backups remain excluded from Git.
