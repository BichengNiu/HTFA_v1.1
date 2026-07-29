# UAE Economic Monitoring Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the first usable UAE economic-monitoring page that explains GDP changes through oil/non-oil and industry contributions, while preserving an explicit boundary between accounting facts, mechanism evidence, and leading signals.

**Architecture:** A thin UAE analysis adapter reuses the formal workbook parser in `dashboard.preview.core.workbook_parser` and converts its normalized output into semantic growth inputs. Pure calculation and diagnostic modules perform additivity checks, contribution calculations, confidence grading, and deterministic narrative generation; the Streamlit renderer only presents those results. Phase 1 implements growth diagnostics only and does not create empty inflation, labor, fiscal, external, or monetary pages.

**Tech Stack:** Python 3.11+, pandas, Streamlit, Plotly, openpyxl, pytest

---

## Scope and non-goals

In scope:

- UAE monitoring navigation and permission;
- default `data/阿联酋.xlsx` plus the global shared-uploaded workbook;
- semantic resolution of the Phase 1 GDP series;
- oil/non-oil and industry growth contributions;
- nominal-real bridge, structural shares, diffusion, residual checks;
- deterministic diagnostic text, evidence labels, confidence, and data cutoffs;
- unit tests, real-workbook contract test, compile check, and Streamlit smoke test.

Not in scope:

- raw data tables already provided by Preview;
- CPI, labor, fiscal, balance-of-payments, and monetary calculations;
- forecasting, causal inference, or model-based attribution;
- automatic download or scraping of public data;
- changing the formal workbook format;
- Git commits unless separately requested.

Design references:

- `docs/analysis/阿联酋经济监测模块设计说明.md`
- `docs/analysis/阿联酋经济监测变量字典.md`
- `dashboard/preview/core/workbook_parser.py`
- `dashboard/core/ui/utils/shared_dataset.py`

## Task 1: Create the UAE analysis data contract

**Files:**

- Create: `dashboard/analysis/uae/__init__.py`
- Create: `dashboard/analysis/uae/contracts.py`
- Test: `tests/analysis/uae/test_contracts.py`

**Step 1: Create the test package**

Create:

- `tests/analysis/__init__.py`
- `tests/analysis/uae/__init__.py`

**Step 2: Write the failing contract tests**

Create `tests/analysis/uae/test_contracts.py`:

```python
import pandas as pd
import pytest

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    DiagnosticResult,
    EvidenceClass,
    EvidenceItem,
    UAEDataBundle,
)


def test_bundle_returns_a_copy_of_a_known_series():
    source = pd.Series(
        [100.0, 105.0],
        index=pd.period_range("2025Q1", periods=2, freq="Q"),
        name="实际GDP",
    )
    bundle = UAEDataBundle(series_by_id={"growth.real_gdp": source}, metadata={})

    result = bundle.require_series("growth.real_gdp")
    result.iloc[0] = -1.0

    assert source.iloc[0] == 100.0


def test_bundle_reports_missing_semantic_ids_together():
    bundle = UAEDataBundle(series_by_id={}, metadata={})

    with pytest.raises(ValueError, match="growth.real_gdp, growth.nonoil_real_gdp"):
        bundle.require_ids(
            {"growth.real_gdp", "growth.nonoil_real_gdp"}
        )


def test_diagnostic_result_keeps_evidence_class_and_confidence():
    result = DiagnosticResult(
        title="非油增长",
        summary="非油增长加快。",
        confidence=ConfidenceLevel.MEDIUM,
        confidence_reasons=("行业覆盖存在残差",),
        evidence=(
            EvidenceItem(
                label="制造业贡献",
                value=1.2,
                unit="个百分点",
                evidence_class=EvidenceClass.ACCOUNTING,
                as_of="2025Q4",
            ),
        ),
    )

    assert result.evidence[0].evidence_class is EvidenceClass.ACCOUNTING
    assert result.confidence is ConfidenceLevel.MEDIUM
```

**Step 3: Run the tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_contracts.py -v
```

Expected: collection fails because `dashboard.analysis.uae.contracts` does not exist.

**Step 4: Implement the immutable contracts**

Create `dashboard/analysis/uae/contracts.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import pandas as pd


class EvidenceClass(str, Enum):
    ACCOUNTING = "核算事实"
    MECHANISM = "机制证据"
    LEADING = "领先信号"
    MODEL = "模型估计"


class ConfidenceLevel(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    value: float | str
    unit: str
    evidence_class: EvidenceClass
    as_of: str
    note: str = ""


@dataclass(frozen=True)
class DiagnosticResult:
    title: str
    summary: str
    confidence: ConfidenceLevel
    confidence_reasons: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class UAEDataBundle:
    series_by_id: Mapping[str, pd.Series]
    metadata: Mapping[str, Any]

    def require_ids(self, indicator_ids: set[str]) -> None:
        missing = sorted(indicator_ids - set(self.series_by_id))
        if missing:
            raise ValueError(
                "阿联酋监测缺少必需指标: " + ", ".join(missing)
            )

    def require_series(self, indicator_id: str) -> pd.Series:
        self.require_ids({indicator_id})
        return self.series_by_id[indicator_id].copy()
```

Create `dashboard/analysis/uae/__init__.py` without importing Streamlit:

```python
"""阿联酋经济监测模块。"""

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    DiagnosticResult,
    EvidenceClass,
    EvidenceItem,
    UAEDataBundle,
)

__all__ = [
    "ConfidenceLevel",
    "DiagnosticResult",
    "EvidenceClass",
    "EvidenceItem",
    "UAEDataBundle",
]
```

**Step 5: Run the contract tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_contracts.py -v
```

Expected: 3 tests pass.

## Task 2: Add the semantic indicator catalog and parser adapter

**Files:**

- Create: `dashboard/analysis/uae/indicator_catalog.py`
- Create: `dashboard/analysis/uae/data_adapter.py`
- Modify: `dashboard/analysis/uae/__init__.py`
- Test: `tests/analysis/uae/test_data_adapter.py`
- Read only: `data/阿联酋.xlsx`

**Step 1: Inventory the actual Phase 1 workbook names**

Run:

```powershell
$env:PYTHONUTF8='1'
python -c "from dashboard.preview.core.workbook_parser import parse_preview_workbook; d=parse_preview_workbook(r'data/阿联酋.xlsx'); print('\n'.join(sorted(d.indicator_metadata)))"
```

Expected: the current indicator names print without modifying the workbook.

Copy only the exact names needed for:

- actual and nominal total GDP;
- actual and nominal non-oil GDP;
- actual and nominal values for the 11 currently available industries;
- crude oil production;
- DFM index.

**Step 2: Write failing catalog tests**

Create `tests/analysis/uae/test_data_adapter.py` with an in-memory workbook fixture that follows
the existing contract: `指标字典` first, metadata in rows 2–6, data from row 7.

Test:

```python
from io import BytesIO

import pandas as pd
import pytest

from dashboard.analysis.uae.data_adapter import load_uae_bundle


def test_adapter_reuses_formal_workbook_contract(valid_uae_workbook):
    bundle = load_uae_bundle(valid_uae_workbook)

    assert "growth.real_gdp" in bundle.series_by_id
    assert "growth.nonoil_real_gdp" in bundle.series_by_id
    assert bundle.require_series("growth.real_gdp").index.is_monotonic_increasing


def test_adapter_rejects_a_valid_but_non_uae_workbook(valid_industrial_workbook):
    with pytest.raises(ValueError, match="不是可识别的阿联酋监测工作簿"):
        load_uae_bundle(valid_industrial_workbook)


def test_real_default_workbook_resolves_phase_one_ids():
    bundle = load_uae_bundle("data/阿联酋.xlsx")

    bundle.require_ids(
        {
            "growth.real_gdp",
            "growth.nominal_gdp",
            "growth.nonoil_real_gdp",
            "growth.nonoil_nominal_gdp",
            "oil.crude_production",
        }
    )
```

Reuse or extract the in-memory workbook builder from
`tests/preview/test_workbook_parser.py`; do not introduce a second workbook format.

**Step 3: Run the adapter tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_data_adapter.py -v
```

Expected: tests fail because the catalog and adapter do not exist.

**Step 4: Implement an explicit catalog**

Create `dashboard/analysis/uae/indicator_catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpec:
    indicator_id: str
    aliases: tuple[str, ...]
    required_phase_one: bool = False


INDICATOR_SPECS = (
    IndicatorSpec(
        "growth.real_gdp",
        ("<replace with exact current workbook name>",),
        required_phase_one=True,
    ),
    IndicatorSpec(
        "growth.nominal_gdp",
        ("<replace with exact current workbook name>",),
        required_phase_one=True,
    ),
    IndicatorSpec(
        "growth.nonoil_real_gdp",
        ("<replace with exact current workbook name>",),
        required_phase_one=True,
    ),
    IndicatorSpec(
        "growth.nonoil_nominal_gdp",
        ("<replace with exact current workbook name>",),
        required_phase_one=True,
    ),
    IndicatorSpec(
        "oil.crude_production",
        ("<replace with exact current workbook name>",),
        required_phase_one=True,
    ),
)

PHASE_ONE_REQUIRED_IDS = frozenset(
    spec.indicator_id for spec in INDICATOR_SPECS if spec.required_phase_one
)
```

Replace every placeholder during implementation using the read-only inventory from Step 1.
Add the 11 industry nominal and actual series as explicit specs. Do not guess aliases.

**Step 5: Implement the thin parser adapter**

Create `dashboard/analysis/uae/data_adapter.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.analysis.uae.contracts import UAEDataBundle
from dashboard.analysis.uae.indicator_catalog import (
    INDICATOR_SPECS,
    PHASE_ONE_REQUIRED_IDS,
)
from dashboard.preview.core.workbook_parser import parse_preview_workbook


def load_uae_bundle(file_input: Any) -> UAEDataBundle:
    parsed = parse_preview_workbook(file_input)
    available = {
        name: frame[name]
        for frame in parsed.dataframes.values()
        for name in frame.columns
    }
    metadata = parsed.indicator_metadata
    resolved: dict[str, pd.Series] = {}

    for spec in INDICATOR_SPECS:
        matches = [alias for alias in spec.aliases if alias in available]
        if len(matches) > 1:
            raise ValueError(
                f"指标{spec.indicator_id}匹配到多个序列: {', '.join(matches)}"
            )
        if matches:
            resolved[spec.indicator_id] = available[matches[0]].copy()

    bundle = UAEDataBundle(series_by_id=resolved, metadata=metadata)
    missing = sorted(PHASE_ONE_REQUIRED_IDS - set(resolved))
    if missing:
        raise ValueError(
            "当前文件不是可识别的阿联酋监测工作簿；缺少: "
            + ", ".join(missing)
        )
    return bundle
```

The adapter must not import Preview renderers, tabs, or Streamlit state.

**Step 6: Run parser, adapter, and architecture tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_data_adapter.py tests/preview/test_workbook_parser.py tests/preview/test_architecture.py -v
```

Expected: all selected tests pass and no reverse UI import is introduced.

## Task 3: Implement pure growth calculations

**Files:**

- Create: `dashboard/analysis/uae/growth.py`
- Test: `tests/analysis/uae/test_growth.py`

**Step 1: Write failing additivity and contribution tests**

Create `tests/analysis/uae/test_growth.py`:

```python
import pandas as pd
import pytest

from dashboard.analysis.uae.growth import (
    calculate_diffusion,
    calculate_growth_contributions,
    calculate_nominal_real_bridge,
    validate_additivity,
)


def quarterly(values, name):
    return pd.Series(
        values,
        index=pd.period_range("2024Q1", periods=len(values), freq="Q"),
        name=name,
        dtype=float,
    )


def test_yoy_contributions_sum_to_total_growth_when_components_add():
    oil = quarterly([30, 31, 32, 33, 33, 34, 35, 36], "oil")
    nonoil = quarterly([70, 72, 74, 76, 77, 79, 81, 84], "nonoil")
    total = oil + nonoil

    result = calculate_growth_contributions(
        total,
        {"oil": oil, "nonoil": nonoil},
        periods=4,
    )

    assert result.contributions.sum(axis=1).iloc[-1] == pytest.approx(
        result.total_growth.iloc[-1]
    )


def test_additivity_reports_residual_instead_of_hiding_it():
    total = quarterly([100, 105], "total")
    components = {
        "a": quarterly([40, 42], "a"),
        "b": quarterly([50, 51], "b"),
    }

    result = validate_additivity(total, components)

    assert result.residual.iloc[-1] == pytest.approx(12.0)
    assert not result.within_tolerance.iloc[-1]


def test_nominal_real_bridge_is_log_additive():
    nominal = quarterly([100, 110], "nominal")
    real = quarterly([100, 105], "real")

    result = calculate_nominal_real_bridge(nominal, real, periods=1)

    assert (
        result.real_log_growth + result.deflator_log_growth
    ).iloc[-1] == pytest.approx(result.nominal_log_growth.iloc[-1])


def test_diffusion_excludes_missing_industries_from_denominator():
    industries = pd.DataFrame(
        {
            "a": [100, 105],
            "b": [100, 95],
            "c": [100, float("nan")],
        },
        index=pd.period_range("2024Q1", periods=2, freq="Q"),
    )

    result = calculate_diffusion(industries, periods=1)

    assert result.iloc[-1] == pytest.approx(0.5)
```

**Step 2: Run the tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_growth.py -v
```

Expected: collection fails because `dashboard.analysis.uae.growth` does not exist.

**Step 3: Implement calculation result dataclasses**

Add immutable result classes in `growth.py`:

```python
@dataclass(frozen=True)
class AdditivityResult:
    residual: pd.Series
    residual_ratio: pd.Series
    within_tolerance: pd.Series


@dataclass(frozen=True)
class ContributionResult:
    total_growth: pd.Series
    contributions: pd.DataFrame
    additivity: AdditivityResult


@dataclass(frozen=True)
class NominalRealBridge:
    deflator: pd.Series
    nominal_log_growth: pd.Series
    real_log_growth: pd.Series
    deflator_log_growth: pd.Series
```

**Step 4: Implement additivity**

Use:

```python
residual = total - components.sum(axis=1, min_count=1)
residual_ratio = residual.abs() / total.abs().replace(0.0, pd.NA)
within_tolerance = (residual.abs() <= absolute_tolerance) | (
    residual_ratio <= relative_tolerance
)
```

Default tolerances:

- `absolute_tolerance=1e-6`;
- `relative_tolerance=0.005`.

Never silently add the residual to an industry.

**Step 5: Implement growth contributions**

For a `periods` comparison:

```python
contribution_i = (
    component_i - component_i.shift(periods)
) / total.shift(periods) * 100

total_growth = (
    total - total.shift(periods)
) / total.shift(periods) * 100
```

Requirements:

- inner-align indexes before calculation;
- preserve missing values;
- reject duplicated indexes;
- reject nonpositive or zero lagged denominators with a clear error;
- include additivity results.

Do not annualize unadjusted quarter-on-quarter values.

**Step 6: Implement the nominal-real bridge**

Use:

```python
deflator = nominal / real * 100
nominal_log_growth = 100 * np.log(nominal / nominal.shift(periods))
real_log_growth = 100 * np.log(real / real.shift(periods))
deflator_log_growth = 100 * np.log(deflator / deflator.shift(periods))
```

This creates an exact log-additive decomposition. Label the growth unit “log percentage points”.

**Step 7: Implement diffusion**

Compute industry growth at the requested lag, then:

```python
positive = growth.gt(0).sum(axis=1)
valid = growth.notna().sum(axis=1)
diffusion = positive / valid.replace(0, pd.NA)
```

**Step 8: Run calculation tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_growth.py -v
```

Expected: all growth tests pass.

## Task 4: Add the deterministic diagnostic engine

**Files:**

- Create: `dashboard/analysis/uae/diagnostics.py`
- Test: `tests/analysis/uae/test_diagnostics.py`

**Step 1: Write failing language and confidence tests**

Create `tests/analysis/uae/test_diagnostics.py`:

```python
import pandas as pd

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    EvidenceClass,
)
from dashboard.analysis.uae.diagnostics import diagnose_growth
from dashboard.analysis.uae.growth import (
    AdditivityResult,
    ContributionResult,
)


def test_growth_diagnostic_uses_accounting_language():
    index = pd.period_range("2025Q4", periods=1, freq="Q")
    contributions = ContributionResult(
        total_growth=pd.Series([4.0], index=index),
        contributions=pd.DataFrame(
            {"非油": [3.2], "石油": [0.8]},
            index=index,
        ),
        additivity=AdditivityResult(
            residual=pd.Series([0.0], index=index),
            residual_ratio=pd.Series([0.0], index=index),
            within_tolerance=pd.Series([True], index=index),
        ),
    )

    result = diagnose_growth(contributions)

    assert "贡献" in result.summary
    assert "导致" not in result.summary
    assert result.evidence[0].evidence_class is EvidenceClass.ACCOUNTING
    assert result.confidence is ConfidenceLevel.HIGH


def test_residual_and_missing_mechanism_evidence_reduce_confidence():
    index = pd.period_range("2025Q4", periods=1, freq="Q")
    contributions = ContributionResult(
        total_growth=pd.Series([4.0], index=index),
        contributions=pd.DataFrame({"非油": [2.0]}, index=index),
        additivity=AdditivityResult(
            residual=pd.Series([2.0], index=index),
            residual_ratio=pd.Series([0.02], index=index),
            within_tolerance=pd.Series([False], index=index),
        ),
    )

    result = diagnose_growth(contributions, mechanism_evidence=())

    assert result.confidence is ConfidenceLevel.LOW
    assert any("残差" in reason for reason in result.confidence_reasons)
```

**Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_diagnostics.py -v
```

Expected: collection fails because the diagnostic module does not exist.

**Step 3: Implement fixed confidence rules**

Create `dashboard/analysis/uae/diagnostics.py` with these rules:

1. Start at high confidence.
2. Reduce to medium if the latest additivity check fails or a required series is stale.
3. Reduce to low if both accounting coverage is incomplete and no independent mechanism evidence is available.
4. Reduce one level if evidence directions conflict.
5. Never increase confidence because more charts are present.

**Step 4: Implement deterministic narrative**

The narrative must:

- identify the latest result period;
- state the total direction and magnitude;
- name at most the two largest positive and two largest negative contributions;
- use “贡献/拖累” for accounting facts;
- use “与……一致/提供支持” for mechanism evidence;
- state one material limitation;
- never use “导致/造成/决定” unless a future model result is explicitly passed.

**Step 5: Run diagnostic tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_diagnostics.py -v
```

Expected: all diagnostic tests pass.

## Task 5: Assemble the Phase 1 monitoring service

**Files:**

- Create: `dashboard/analysis/uae/service.py`
- Test: `tests/analysis/uae/test_service.py`

**Step 1: Write a failing end-to-end service test**

The test must pass a valid in-memory UAE workbook and assert:

- oil and non-oil contribution results exist;
- industry results include an explicit residual;
- nominal-real bridge exists;
- diffusion exists;
- diagnostic evidence is labelled;
- every output has a latest observation period;
- no raw workbook DataFrame is exposed as a public service result.

**Step 2: Run the test and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_service.py -v
```

Expected: fails because the service does not exist.

**Step 3: Implement the service contract**

Use:

```python
@dataclass(frozen=True)
class GrowthMonitoringResult:
    headline: DiagnosticResult
    oil_nonoil: ContributionResult
    industries: ContributionResult
    nominal_real: NominalRealBridge
    diffusion: pd.Series
    latest_period: str
    data_cutoffs: Mapping[str, str]
```

Implement:

```python
def build_growth_monitoring(file_input) -> GrowthMonitoringResult:
    bundle = load_uae_bundle(file_input)
    # Resolve required series.
    # Validate index and metadata compatibility.
    # Calculate oil/non-oil and industry results.
    # Preserve the uncovered residual.
    # Build deterministic diagnostic output.
    # Return immutable analytical results only.
```

**Step 4: Add metadata compatibility checks**

Before calculation:

- require quarterly frequency for GDP and industry inputs;
- require compatible units for components and total;
- require identical comparison basis for nominal versus actual series;
- reject duplicate periods;
- do not interpolate missing values;
- use metadata `updated_at` as the data cutoff.

**Step 5: Run service and real-workbook tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_service.py tests/analysis/uae/test_data_adapter.py -v
```

Expected: all tests pass.

## Task 6: Build the Streamlit renderer

**Files:**

- Create: `dashboard/analysis/uae/renderer.py`
- Create: `dashboard/analysis/uae/charts.py`
- Modify: `dashboard/analysis/uae/__init__.py`
- Test: `tests/analysis/uae/test_renderer.py`

**Step 1: Write failing renderer tests**

Test pure chart builders and a fake Streamlit boundary:

- contribution chart receives contribution data, not raw levels;
- residual is visibly named “其他行业、税收与残差”;
- accounting/mechanism/leading evidence uses distinct labels;
- low confidence is visible;
- missing or non-UAE workbook produces a clear error and no stale result;
- no large raw data table is rendered.

**Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_renderer.py -v
```

Expected: fails because renderer and chart builders do not exist.

**Step 3: Implement pure chart builders**

Create functions in `charts.py`:

```python
def build_growth_history_chart(result: GrowthMonitoringResult):
    ...


def build_oil_nonoil_contribution_chart(result: GrowthMonitoringResult):
    ...


def build_industry_contribution_chart(result: GrowthMonitoringResult):
    ...


def build_nominal_real_bridge_chart(result: GrowthMonitoringResult):
    ...
```

Return Plotly figures without importing Streamlit.

**Step 4: Implement renderer data selection**

Use the raw shared file when present and the default UAE workbook otherwise:

```python
from pathlib import Path

from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file


DEFAULT_UAE_WORKBOOK = Path("data") / "阿联酋.xlsx"


def _select_workbook():
    return get_shared_dataset_file() or DEFAULT_UAE_WORKBOOK
```

If a shared workbook exists but is not a UAE workbook, show the validation error. Do not silently fall
back to the default file because that would misrepresent which data the user selected.

**Step 5: Implement the Phase 1 reading order**

`render_uae_monitoring(st_obj)` renders:

1. title and active data source;
2. one diagnostic summary card;
3. result trend;
4. oil/non-oil contribution;
5. industry contribution including residual;
6. nominal-real bridge;
7. diffusion and current structure;
8. mechanism evidence for oil production and, when later available, Brent;
9. evidence limitations and data cutoffs;
10. link/caption directing raw-data inspection to Preview.

Do not create empty tabs for unimplemented macro systems.

**Step 6: Clear stale renderer state**

Use the shared dataset fingerprint in the cache key. On file change or validation failure, remove only
state keys prefixed with `analysis.uae.`.

**Step 7: Run renderer tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_renderer.py -v
```

Expected: all renderer tests pass.

## Task 7: Add navigation and permissions

**Files:**

- Modify: `app.py:233-247`
- Modify: `dashboard/core/ui/constants.py:21-54`
- Modify: `dashboard/core/ui/components/content_router.py:293-310`
- Modify: `dashboard/core/ui/components/content_router.py:501-507`
- Modify: `dashboard/auth/permissions.py:38-49`
- Test: `tests/analysis/uae/test_navigation.py`

**Step 1: Write failing navigation tests**

Create `tests/analysis/uae/test_navigation.py`:

```python
import ast
from pathlib import Path

from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP
from dashboard.core.ui.components.content_router import detect_navigation_level
from dashboard.core.ui.constants import UIConstants


def read_module_config():
    module = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MODULE_CONFIG"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("app.py does not define MODULE_CONFIG")


def test_uae_monitoring_is_navigable():
    assert "阿联酋" in read_module_config()["监测分析"]
    assert "阿联酋" in UIConstants.MAIN_MODULES["监测分析"]["sub_modules"]
    assert detect_navigation_level("监测分析", "阿联酋") == "FUNCTION_ACTIVE"


def test_uae_monitoring_has_granular_permission():
    permission = GRANULAR_PERMISSION_MAP["监测分析"]["sub_modules"]["阿联酋"]

    assert permission == {
        "code": "monitoring_analysis.uae",
        "tabs": None,
    }
```

**Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/analysis/uae/test_navigation.py -v
```

Expected: both tests fail because monitoring navigation contains only `工业`.

**Step 3: Add the main navigation entry**

Change `app.py`:

```python
"监测分析": {
    "工业": ["工业增加值", "工业企业利润"],
    "阿联酋": None,
},
```

Change `dashboard/core/ui/constants.py`:

```python
"监测分析": {
    "icon": "[CHART]",
    "description": "对经济运行数据进行深度监测和分析，提供专业的分析报告",
    "sub_modules": ["工业", "阿联酋"],
},
```

Keep the existing UAE submodule card but update its description so it covers both Preview and
Monitoring without claiming raw data is the analysis.

**Step 4: Add routing**

In `render_monitoring_analysis_content`:

```python
if sub_module == "工业":
    from dashboard.analysis.industrial import render_industrial_analysis

    render_industrial_analysis(st)
elif sub_module == "阿联酋":
    from dashboard.analysis.uae import render_uae_monitoring

    render_uae_monitoring(st)
else:
    st.info("请选择一个子模块以开始监测分析")
```

Update navigation-level detection:

```python
if main_module == "监测分析" and sub_module in {"工业", "阿联酋"}:
    return "FUNCTION_ACTIVE"
```

**Step 5: Add permission**

Under `GRANULAR_PERMISSION_MAP["监测分析"]["sub_modules"]`:

```python
"阿联酋": {
    "code": "monitoring_analysis.uae",
    "tabs": None,
},
```

Phase 1 has no separately permissioned internal tabs.

**Step 6: Run navigation and existing preview tests**

Run:

```powershell
python -m pytest tests/analysis/uae/test_navigation.py tests/preview/test_uae_navigation.py -v
```

Expected: all tests pass and Preview UAE routing is unchanged.

## Task 8: Full verification

**Files:**

- Read only: `data/阿联酋.xlsx`
- Read only: all changed source and test files

**Step 1: Run the UAE analysis suite**

Run:

```powershell
python -m pytest tests/analysis/uae -v
```

Expected: all UAE contract, adapter, calculation, diagnostic, service, renderer, and navigation tests
pass.

**Step 2: Run affected regression suites**

Run:

```powershell
python -m pytest tests/preview tests/explore/test_shared_dataset.py -v
```

Expected: all affected Preview and shared-dataset tests pass.

**Step 3: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: zero failures.

**Step 4: Run compile validation**

Run:

```powershell
python -m compileall app.py dashboard tests
```

Expected: exit code 0 and no syntax errors.

**Step 5: Smoke-test Streamlit**

Run:

```powershell
streamlit run app.py --server.port=8501
```

Manual scenarios:

1. Open `监测分析 → 阿联酋` without a shared upload; the default workbook loads.
2. Verify the page presents conclusions and contributions, not raw tables.
3. Verify residual and confidence are visible.
4. Upload `data/阿联酋.xlsx` through the shared uploader; the page recomputes.
5. Upload a valid industrial workbook; UAE monitoring rejects it clearly and does not show stale UAE results.
6. Switch to Preview; raw UAE data remains available there.
7. Switch back to industrial monitoring; existing industrial behavior remains unchanged.

Expected: all seven scenarios behave as specified, with no Streamlit error or exception.

**Step 6: Inspect the diff**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- no whitespace errors;
- no changes to `data/阿联酋.xlsx`;
- only the planned UAE analysis, routing, permission, test, and documentation files changed.

No Git commit is included because the user did not request one.

## Phase 1 acceptance criteria

Phase 1 is complete only when:

1. The result variable and comparison period are explicit.
2. Oil/non-oil and industry contributions are mathematically reconcilable or show a visible residual.
3. Nominal and actual changes are not mixed.
4. Every statement is labelled as accounting fact, mechanism evidence, or leading signal.
5. Confidence has a reproducible reason.
6. National, emirate, and sample coverage are not conflated.
7. Raw data remains in Preview.
8. A non-UAE workbook cannot generate a UAE diagnosis.
9. File changes cannot leave stale diagnosis results.
10. All automated and manual checks pass.

Only after these criteria pass should Phase 2 add CPI and monetary-financial diagnostics.
