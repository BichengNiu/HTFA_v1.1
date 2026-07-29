# UAE Monitoring Runtime Simulation Implementation Plan

**Goal:** Use real series from `data/阿联酋.xlsx` whenever available and generate deterministic,
macro-consistent simulated series at runtime for missing indicators without creating or modifying
any workbook.

## Non-negotiable contracts

1. Real data always overrides simulated data.
2. Simulation never writes to `data/阿联酋.xlsx` or creates another workbook.
3. Every series carries `real` or `simulated` provenance.
4. Every simulated chart and conclusion is visibly labelled “模拟数据”.
5. Conclusions using simulation have confidence no higher than “低”.
6. Simulated accounting systems reconcile:
   - expenditure GDP components sum to GDP;
   - income GDP components sum to GDP;
   - fiscal net lending equals revenue minus expense minus net non-financial assets;
   - current-account components sum to the current account;
   - M1 ≤ M2 ≤ M3.
7. Simulation uses stable seeds derived from semantic indicator IDs.
8. File changes clear dependent `analysis.uae.*` state.

## Batches

### Batch 1: Foundations

1. Create immutable data, provenance, evidence, and diagnostic contracts.
2. Reuse the formal workbook parser, map existing UAE indicators to semantic IDs, and add a
   deterministic runtime simulation provider with identity tests.
3. Add pure growth contribution, residual, diffusion, and nominal-real calculations.

### Batch 2: Macro diagnostics

4. Build growth, inflation, labor-income, fiscal-external, and monetary-financial analytical
   results from the mixed real/simulated bundle.
5. Add deterministic narrative and confidence rules that expose simulated evidence.

### Batch 3: UI and integration

6. Build the overview and five detailed Streamlit pages.
7. Add monitoring navigation and permission.
8. Test default workbook, shared UAE upload, rejection of non-UAE workbooks, state invalidation,
   provenance labels, and regressions.

## Verification

Run after every batch:

```powershell
python -m pytest tests/analysis/uae -v
```

Final checks:

```powershell
python -m pytest -q
python -m compileall app.py dashboard tests
git diff --check
```

Manual smoke test:

```powershell
streamlit run app.py --server.port=8501
```
