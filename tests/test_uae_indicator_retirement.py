"""Explicit indicator retirement preserves all retained observations and inputs."""

from datetime import date

from openpyxl import Workbook, load_workbook
import pytest

from htfa.jobs.uae_data import db, source_dld as dld
from htfa.jobs.uae_data.retired_sources import (
    RETIRED_INDICATORS, RETIRED_WEEKLY_COLUMNS, retire_database, retire_workbook,
)


def test_retirement_cleans_old_tables_aliases_rows_and_columns_idempotently():
    with db.connect(":memory:") as con:
        db.init_schema(con)
        con.execute("CREATE TABLE detail.emirates_post_monthly(value INTEGER)")
        con.execute("CREATE VIEW main.emirates_post_monthly AS SELECT * FROM detail.emirates_post_monthly")
        con.execute("CREATE TABLE detail.eurostat_air_monthly(value INTEGER)")
        for table in ("uaewps_monthly", "dld_lease_monthly", "ded_official_news_candidates",
                      "ded_official_news_scan_state"):
            con.execute(f"CREATE TABLE {table}(value INTEGER)")
        con.execute("CREATE TABLE public_market_daily(indicator VARCHAR,value DOUBLE)")
        con.execute("INSERT INTO public_market_daily VALUES ('美元兑阿联酋迪拉姆',3.67),('人民币兑阿联酋迪拉姆',0.51)")
        con.execute("INSERT INTO ded_monthly VALUES ('2026-09-30','enterprises',10),('2021-02-28','official_new_licenses',99)")
        for column in RETIRED_WEEKLY_COLUMNS:
            con.execute(f"ALTER TABLE dld_investment_pipeline_weekly ADD COLUMN {column} DOUBLE")
        con.execute("INSERT INTO dld_investment_pipeline_weekly(week_end,confirmed_new_projects_28d,active_projects_28d) VALUES ('2026-09-27',4,7)")
        for _ in range(2):
            retire_database(con)
        assert con.execute("SELECT * FROM public_market_daily").fetchall() == [("人民币兑阿联酋迪拉姆",0.51)]
        assert con.execute("SELECT series,value FROM ded_monthly").fetchall() == [("enterprises",10)]
        assert con.execute("SELECT * FROM dld_investment_pipeline_weekly").fetchall() == [(date(2026,9,27),4,7)]
        assert not con.execute("SELECT * FROM information_schema.tables WHERE table_name IN ('emirates_post_monthly','eurostat_air_monthly','uaewps_monthly','dld_lease_monthly','ded_official_news_candidates','ded_official_news_scan_state')").fetchall()
        assert sum(map(len, RETIRED_INDICATORS.values())) == 182


def test_workbook_retirement_resolves_names_after_column_reordering(tmp_path, monkeypatch):
    import htfa.jobs.uae_data.uae_metadata as metadata

    database = tmp_path / "uae.duckdb"
    with db.connect(database) as con:
        db.init_schema(con)
        retire_database(con)
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda **kw: connect(database, **kw))
    monkeypatch.setattr(metadata, "sync_workbook_dictionary", lambda path: {})
    path = tmp_path / "book.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "日度_Wind"
    for col, name, value in [(2,"人民币兑阿联酋迪拉姆",0.51),(3,"美元兑阿联酋迪拉姆",3.67),
                             (4,"阿联酋DFM综合股票指数",6000)]:
        sheet.cell(2,col,name)
        sheet.cell(7,col,value)
    unused = book.create_sheet("月度_Wind")
    unused.cell(2,2,RETIRED_INDICATORS["月度_Wind"][0])
    book.save(path)
    book.close()
    assert len(retire_workbook(path)) == 2
    assert retire_workbook(path) == []
    book = load_workbook(path)
    assert "月度_Wind" not in book.sheetnames
    assert [book.active.cell(2,c).value for c in (2,3)] == ["人民币兑阿联酋迪拉姆","阿联酋DFM综合股票指数"]
    assert [book.active.cell(7,c).value for c in (2,3)] == [0.51,6000]
    book.close()


def test_retirement_does_not_touch_tables_in_an_attached_backup(tmp_path):
    backup = tmp_path / "old.duckdb"
    with db.connect(backup) as con:
        con.execute("CREATE TABLE public_market_daily(indicator VARCHAR,value DOUBLE)")
        con.execute("INSERT INTO public_market_daily VALUES ('美元兑阿联酋迪拉姆',3.67)")
        con.execute("CREATE SCHEMA detail")
        con.execute("CREATE TABLE detail.emirates_post_monthly(volume INTEGER)")
        con.execute("INSERT INTO detail.emirates_post_monthly VALUES (42)")
    with db.connect(":memory:") as con:
        db.init_schema(con)
        location = backup.as_posix().replace("'", "''")
        con.execute(f"ATTACH '{location}' AS previous")
        retire_database(con)
        assert con.execute("SELECT * FROM previous.main.public_market_daily").fetchall() == [
            ("美元兑阿联酋迪拉姆",3.67),
        ]
        assert con.execute("SELECT volume FROM previous.detail.emirates_post_monthly").fetchone() == (42,)


def test_retained_project_counts_keep_confirmation_windows_and_complete_months():
    with db.connect(":memory:") as con:
        con.execute("CREATE SCHEMA detail")
        con.execute("CREATE TABLE detail.dld_transactions(transaction_id VARCHAR,instance_date DATE,project_number VARCHAR,reg_type_en VARCHAR,trans_group_en VARCHAR)")
        rows = [(str(i),date(2026,8,3+i),"A","Off-Plan Properties","Sales") for i in range(10)]
        rows += [(str(20+i),date(2026,9,21+i),"B","Off-Plan Properties","Sales") for i in range(3)]
        rows += [(str(30+i),date(2026,9,20),"C","Off-Plan Properties","Sales") for i in range(10)]
        rows += [("last",date(2026,10,7),None,"Existing Properties","Mortgages")]
        con.executemany("INSERT INTO detail.dld_transactions VALUES (?,?,?,?,?)",rows)
        result = dld.to_weekly_table_rows(dld._fetch_raw_weekly(con))
    by_date = {r["week_end"]:r for r in result}
    assert by_date[date(2026,8,30)]["confirmed_new_projects_28d"] == 1
    assert by_date[date(2026,9,27)]["confirmed_new_projects_28d"] == 0
    assert by_date[date(2026,9,27)]["active_projects_28d"] == 2
    assert max(by_date) == date(2026,9,27)
    with pytest.raises((TypeError,ValueError)):
        dld.to_weekly_table_rows([dict(week_start=date(2026,9,21),week_end=date(2026,9,27),
                                     confirmed_new_projects_28d="1",active_projects_28d=2)])
