import pandas as pd
import pytest

from dashboard.analysis.uae.contracts import ProvenanceKind
from dashboard.analysis.uae.data_adapter import (
    load_real_uae_bundle,
    load_runtime_uae_bundle,
)


def test_real_default_workbook_resolves_current_growth_data():
    bundle = load_real_uae_bundle()

    bundle.require_ids(
        {
            "growth.real_gdp",
            "growth.nominal_gdp",
            "growth.nonoil_real_gdp",
            "growth.nonoil_nominal_gdp",
            "oil.crude_production",
            "market.dfm_index",
        }
    )
    assert bundle.require_provenance(
        "growth.real_gdp"
    ).kind is ProvenanceKind.REAL


def test_runtime_simulation_never_overwrites_real_series():
    real = load_real_uae_bundle()
    runtime = load_runtime_uae_bundle()

    pd.testing.assert_series_equal(
        runtime.require_series("growth.real_gdp"),
        real.require_series("growth.real_gdp"),
    )
    assert runtime.require_provenance(
        "growth.real_gdp"
    ).kind is ProvenanceKind.REAL


def test_runtime_simulation_is_deterministic():
    first = load_runtime_uae_bundle()
    second = load_runtime_uae_bundle()

    pd.testing.assert_series_equal(
        first.require_series("inflation.cpi_all"),
        second.require_series("inflation.cpi_all"),
    )


def test_simulated_series_are_explicitly_labelled():
    bundle = load_runtime_uae_bundle()
    provenance = bundle.require_provenance("inflation.cpi_all")

    assert provenance.kind is ProvenanceKind.SIMULATED
    assert "模拟数据" in provenance.source
    assert "非官方" in provenance.source


def test_simulated_expenditure_and_income_accounts_reconcile():
    bundle = load_runtime_uae_bundle()
    nominal = bundle.require_series("growth.nominal_gdp")
    household = bundle.require_series("expenditure.household_consumption")
    government = bundle.require_series("expenditure.government_consumption")
    investment = bundle.require_series("expenditure.gfcf")
    inventories = bundle.require_series("expenditure.inventory_change")
    exports = bundle.require_series("expenditure.exports")
    imports = bundle.require_series("expenditure.imports")

    expenditure_total = (
        household + government + investment + inventories + exports - imports
    )
    pd.testing.assert_series_equal(
        expenditure_total,
        nominal,
        check_names=False,
        rtol=1e-12,
    )

    income_total = (
        bundle.require_series("income.compensation")
        + bundle.require_series("income.operating_surplus")
        + bundle.require_series("income.mixed_income")
        + bundle.require_series("income.production_taxes_net")
    )
    pd.testing.assert_series_equal(
        income_total,
        nominal,
        check_names=False,
        rtol=1e-12,
    )


def test_simulated_fiscal_and_external_accounts_reconcile():
    bundle = load_runtime_uae_bundle()
    fiscal_balance = (
        bundle.require_series("fiscal.total_revenue")
        - bundle.require_series("fiscal.total_expense")
        - bundle.require_series("fiscal.net_nonfinancial_assets")
    )
    pd.testing.assert_series_equal(
        fiscal_balance,
        bundle.require_series("fiscal.net_lending_borrowing"),
        check_names=False,
        rtol=1e-12,
    )

    current_account = (
        bundle.require_series("external.goods_balance")
        + bundle.require_series("external.services_balance")
        + bundle.require_series("external.primary_income")
        + bundle.require_series("external.secondary_income")
    )
    pd.testing.assert_series_equal(
        current_account,
        bundle.require_series("external.current_account"),
        check_names=False,
        rtol=1e-12,
    )


def test_simulated_money_aggregates_are_ordered():
    bundle = load_runtime_uae_bundle()
    m1 = bundle.require_series("monetary.m1")
    m2 = bundle.require_series("monetary.m2")
    m3 = bundle.require_series("monetary.m3")

    assert (m1 <= m2).all()
    assert (m2 <= m3).all()
