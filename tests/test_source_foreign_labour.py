"""The retained labour pipeline publishes two countries without synthetic proxies."""

from datetime import date

from openpyxl import Workbook, load_workbook

from htfa.monitoring.uae.jobs import db
from htfa.monitoring.uae.jobs import source_foreign_labour as source


def _make_bangladesh(year, month, value):
    path = source.RAW_DIR / 'bangladesh' / f'bangladesh_bmet_{year}_{month:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"payload":{"totalEmployee":%d,"data":['
                    '{"country_name":"UNITED ARAB EMIRATES","total_employee":%d}]}}' % (value, value))


def test_numeric_handles_dash_and_commas():
    assert source.numeric(None) == 0
    assert source.numeric('-') == 0
    assert source.numeric('1,234') == 1234


def test_parse_bangladesh_reads_complete_months(tmp_path, monkeypatch):
    monkeypatch.setattr(source, 'RAW_DIR', tmp_path)
    _make_bangladesh(2026, 6, 100)
    _make_bangladesh(2026, 7, 120)
    assert source.parse_bangladesh() == {'2026-06': 100, '2026-07': 120}


def test_rows_to_long_preserves_missing_country_values():
    rows = [{'date': date(2026, 6, 30), 'nepal_with_reentry': None, 'bangladesh_clearance': 100}]
    assert source._rows_to_long(rows) == [{
        'period': date(2026, 6, 30), 'series': 'bangladesh_clearance',
        'value': 100, 'quality_flag': None,
    }]


def test_refresh_preserves_uncovered_history(tmp_path, monkeypatch):
    monkeypatch.setattr(source, 'build_display_rows', lambda: [{
        'date': date(2026, 6, 30), 'nepal_with_reentry': 50, 'bangladesh_clearance': 100,
    }])
    with db.connect(':memory:') as con:
        db.init_schema(con)
        con.execute("INSERT INTO foreign_labour_monthly VALUES ('2020-01-31','nepal_with_reentry',20,NULL)")
        outcome = source.update(con, skip_download=True)
        assert outcome['rows'] == 2
        assert con.execute("SELECT count(*) FROM foreign_labour_monthly").fetchone()[0] == 3
        assert con.execute("SELECT value FROM foreign_labour_monthly WHERE period='2020-01-31'").fetchone()[0] == 20
        assert {r[0] for r in con.execute('SELECT DISTINCT series FROM foreign_labour_monthly').fetchall()} == set(source.ACTIVE_SERIES)


def test_database_roundtrip_keeps_missing_country_months():
    with db.connect(':memory:') as con:
        db.init_schema(con)
        con.execute("INSERT INTO foreign_labour_monthly VALUES ('2026-06-30','bangladesh_clearance',100,NULL)")
        assert source._rows_from_db(con) == [{
            'date': date(2026, 6, 30), 'nepal_with_reentry': None, 'bangladesh_clearance': 100,
        }]


def test_merge_uses_shared_workbook_protocol_and_preserves_other_sheets(tmp_path, monkeypatch):
    database = tmp_path / 'labour.duckdb'
    with db.connect(database) as con:
        db.init_schema(con)
        con.execute("INSERT INTO foreign_labour_monthly VALUES ('2026-06-30','nepal_with_reentry',50,NULL),('2026-06-30','bangladesh_clearance',100,NULL)")
    connect = db.connect
    monkeypatch.setattr(db, 'connect', lambda path=None, **kw: connect(path or database, **kw))
    book = Workbook()
    book.active.title = '保留'
    book.active['A1'] = 'preserved'
    workbook = tmp_path / 'report.xlsx'
    book.save(workbook)
    book.close()
    assert source.merge(workbook)['status'] == 'ok'
    book = load_workbook(workbook)
    try:
        sheet = book[source.SHEET_NAME]
        assert book['保留']['A1'].value == 'preserved'
        assert list(sheet.values)[1] == ('指标名称', '尼泊尔_DoFE批准_含再入境', '孟加拉国_BMET出境许可')
        assert sheet.cell(7, 2).value == 50
        assert sheet.cell(7, 3).value == 100
    finally:
        book.close()
