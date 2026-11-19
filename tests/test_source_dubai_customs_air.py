"""Unused freight measures must not change the retained weights or bill counts."""

import csv
from datetime import date
import gzip

from htfa.monitoring.uae.jobs import source_dubai_customs_air as source


def _shard(path):
    rows = []
    for i, (bill, weight, origin, destination) in enumerate([
        ('A', 500, 'LONDON', 'DUBAI'),
        ('A', 500, 'LONDON', 'DUBAI'),
        ('B', 500, 'LONDON', 'DUBAI'),
        ('C', 2000, 'DUBAI', 'LONDON'),
        ('D', 300, 'LONDON', 'MUMBAI'),
        ('E', 200, 'DUBAI', 'DUBAI'),
        ('B', -250, 'LONDON', 'DUBAI'),
    ]):
        row = {key: '' for key in source.COLUMNS}
        row.update(airwaybilldetailid=str(i), airwaybillid=bill, createddate='2026-06-10',
                   originairportcityname=origin, destairportcityname=destination,
                   weight=str(weight), weighttypename='KILOS',
                   numberofpieces='10', volume='123', volumetypename='CUBIC FEET')
        rows.append(row)
    with gzip.open(path, 'wt', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=source.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_retained_freight_totals_include_domestic_and_keep_negative_adjustments(tmp_path, monkeypatch):
    monkeypatch.setattr(source, 'RAW_DIR', tmp_path)
    path = tmp_path / 'shard.csv.gz'
    _shard(path)
    records, audit = source.collect_rows([path])
    values = {row['indicator']: row['value'] for row in records}
    assert values == {
        '迪拜航空货运_进口总量(吨)': 1.25,
        '迪拜航空货运_出口总量(吨)': 2,
        '迪拜航空货运_转运总量(吨)': .3,
        '迪拜航空货运_合计总量(吨)': 3.75,
        '迪拜航空货运_进口运单数(张)': 2,
        '迪拜航空货运_出口运单数(张)': 1,
    }
    assert audit['rows_read'] == 7
    assert audit['neg_weight_rows'] == 1
    assert all(row['period'] == date(2026, 6, 1) for row in records)


def test_retired_bill_count_groups_are_not_computed(tmp_path, monkeypatch):
    monkeypatch.setattr(source, 'RAW_DIR', tmp_path)
    path = tmp_path / 'shard.csv.gz'
    _shard(path)
    assert source._distinct_awb_counts([path]) == {
        ((2026, 6), 'import'): 2, ((2026, 6), 'export'): 1,
    }
