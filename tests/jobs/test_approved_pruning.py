"""Approved pruning cannot delete retained economics or energy observations."""

from datetime import date
from pathlib import Path
import shutil

from openpyxl import Workbook, load_workbook
import pytest

from htfa.monitoring.uae.jobs import db, prune_unused, source_foreign_labour as labour
from htfa.monitoring.uae.jobs.publish_report import publish_workbook
from htfa.monitoring.uae.jobs.source_registry import SOURCES
from htfa.monitoring.uae.jobs.uae_metadata import sync_workbook_dictionary
from htfa.monitoring.uae.jobs.update_data import run_sources


def make_pair(tmp_path):
    database, workbook = tmp_path / "before.duckdb", tmp_path / "before.xlsx"
    book = Workbook()
    book.active.title = "指标字典"
    book.active.append(['指标名称','类型','行业','频率','开始日期','最新日期','缺失期数','数据来源','预测变量'])
    for title, names in [
        ("月度_CBUAE", ["阿联酋政府存款", "阿联酋:银行国外资产(Foreign Assets)"]),
        ("月度_能源港口", ["能源保供:测试港[port1]:进港次数:已观测月合计"]),
    ]:
        for name in names:
            book["指标字典"].append([name,"数值","金融","月",None,None,None,"官方来源","否"])
        sheet = book.create_sheet(title)
        sheet.append(["官方来源"])
        sheet.append(["指标名称", *names])
        sheet.append(["频率", *["月"]*len(names)])
        sheet.append(["单位", *["百万迪拉姆"]*len(names)])
        sheet.append(["来源", *["官方来源"]*len(names)])
        sheet.append(["更新时间", *[date(2026, 1, 31)]*len(names)])
        sheet.append([date(2026, 1, 31), *range(10, 10+len(names))])
    book.save(workbook)
    book.close()
    with db.connect(database) as con:
        db.init_schema(con)
        con.execute("INSERT INTO cbuae_monthly VALUES ('2026-01-31','阿联酋政府存款',10,'2026-01','source.xlsx')")
        con.execute("INSERT INTO cbuae_monthly VALUES ('2026-01-31','阿联酋:银行国外资产(Foreign Assets)',11,'2026-01','source.xlsx')")
        con.execute("CREATE SCHEMA energy_supply")
        con.execute("CREATE TABLE energy_supply.portwatch_daily(day DATE,node_id VARCHAR,value DOUBLE)")
        con.execute("INSERT INTO energy_supply.portwatch_daily VALUES ('2026-01-31','port1',7)")
        con.execute("CREATE TABLE energy_supply.ais_reports(mmsi VARCHAR,observed TIMESTAMP)")
        con.execute("INSERT INTO energy_supply.ais_reports VALUES ('123','2026-01-31')")
        con.execute("CREATE TABLE energy_supply.report_indicators(indicator VARCHAR)")
        con.execute("INSERT INTO energy_supply.report_indicators VALUES ('unused monthly copy')")
    with db.connect(database) as con:
        publish_workbook(con, workbook)
    return database, workbook


def test_prune_changes_only_approved_columns_and_preserves_originals_on_dry_run(tmp_path):
    database, workbook = make_pair(tmp_path)
    before_db, before_book = database.read_bytes(), workbook.read_bytes()
    result = prune_unused.run(database=database, workbook=workbook)
    assert result['validation']['indicators_removed'] == 2
    assert result['validation']['indicators_retained'] == 1
    assert result['validation']['energy_tables_unchanged'] == 2
    assert database.read_bytes() == before_db
    assert workbook.read_bytes() == before_book


@pytest.mark.parametrize('change', ['credit_value', 'credit_delete', 'port_delete', 'ais_delete', 'report_value', 'misclassified_retirement'])
def test_pruning_audit_rejects_retained_value_change_or_deletion(tmp_path, change):
    database, workbook = make_pair(tmp_path)
    original = tmp_path / 'original.duckdb'
    shutil.copy2(database, original)
    prune_unused.run(database=database, workbook=workbook, publish=True)
    mutations = {
        'credit_value': "UPDATE cbuae_monthly SET value=99",
        'credit_delete': "DELETE FROM cbuae_monthly",
        'port_delete': "DELETE FROM energy_supply.portwatch_daily",
        'ais_delete': "DELETE FROM energy_supply.ais_reports",
        'report_value': "UPDATE report.observations SET value=99",
        'misclassified_retirement': "INSERT INTO meta_retired_indicators VALUES ('月度_CBUAE','阿联酋政府存款'); DELETE FROM cbuae_monthly",
    }
    with db.connect(database) as con:
        con.execute(mutations[change])
    with pytest.raises(ValueError, match='Retained'):
        prune_unused.validate_pruning(original, database)


def test_retired_sources_cannot_be_selected_by_python_or_daily_runner():
    from htfa.monitoring.uae.jobs.daily_refresh import HIGH_FREQUENCY_SOURCES
    retired = {'cloudflare_radar','comtrade','comtrade_vehicles','rta','salik','gfs','energy_supply'}
    assert not retired & set(SOURCES)
    assert not retired & set(HIGH_FREQUENCY_SOURCES)
    for name in retired:
        with pytest.raises(ValueError, match='Unknown source'):
            run_sources([name])


def test_labour_refresh_no_longer_depends_on_philippines_or_three_country_baseline(monkeypatch):
    assert not hasattr(labour, 'parse_philippines')
    monkeypatch.setattr(labour, 'parse_nepal', lambda: {'2026-01': {'with_reentry': 20, 'without_reentry': 15}})
    monkeypatch.setattr(labour, 'parse_bangladesh', lambda: {'2026-02': 30})
    rows = labour.build_display_rows()
    assert len(rows) == 2
    assert rows[0]['nepal_with_reentry'] is None
    assert rows[0]['bangladesh_clearance'] == 30
    assert rows[1]['nepal_with_reentry'] == 20
    assert rows[1]['bangladesh_clearance'] is None
    assert all('proxy_sum' not in row and 'philippines_total' not in row for row in rows)


def test_labour_invalid_retained_value_is_rejected(monkeypatch):
    monkeypatch.setattr(labour, 'parse_nepal', lambda: {'2026-01': {'with_reentry': -1}})
    monkeypatch.setattr(labour, 'parse_bangladesh', lambda: {'2026-01': 30})
    with pytest.raises(ValueError, match='Invalid displayed labour value'):
        labour.build_display_rows()
