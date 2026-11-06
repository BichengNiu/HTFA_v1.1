"""Shared report/map cards with daily counts and confirmed sea-passage totals."""
from calendar import monthrange
from datetime import date, timedelta
from html import escape
import math


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def fmt(value):
    return '—' if value is None else f'{value:,.0f}'


def change(current, previous):
    return '—' if current is None or previous in (None, 0) else f'{(current / previous - 1) * 100:+.1f}%'


SEA_MONITORING_AREAS = ('波斯湾', '红海', '阿曼湾', '亚丁湾')


def windows(day):
    month = day.replace(day=1)
    previous = month - timedelta(days=1)
    prior_end = previous.replace(day=min(day.day, previous.day))
    year_end = day.replace(year=day.year - 1, day=min(day.day, monthrange(day.year - 1, day.month)[1]))
    monday = day - timedelta(days=day.weekday())
    return [(monday - timedelta(days=7), monday - timedelta(days=1)),
            (monday - timedelta(days=14), monday - timedelta(days=8)),
            (month, day), (previous.replace(day=1), prior_end),
            (year_end.replace(day=1), year_end)]


def total(rows, ids, metric, start, end):
    cells = {(str(r.get('portid')), str(r.get('date'))[:10]): number(r.get(metric)) for r in rows}
    values = [cells.get((node, (start + timedelta(days=i)).isoformat()))
              for node in ids for i in range((end - start).days + 1)]
    return sum(values) if values and all(v is not None for v in values) else None


def activity_card(label, catalog, rows, metric, verb, day, statistical=False):
    ids = {str(r['portid']) for r in catalog if not statistical or r.get('statistics_available', False)}
    dates = [date.fromisoformat(str(row['date'])[:10]) for row in rows
             if str(row.get('portid')) in ids and row.get('date')
             and day and str(row['date'])[:10] <= day.isoformat()]
    if not dates:
        return (label, '—', '暂无可用周数据', f'监测{len(catalog):,}个，独立统计{len(ids):,}个')
    end = max(dates)
    start = end - timedelta(days=end.weekday())
    cells = {}
    for row in rows:
        key = str(row.get('portid')), str(row.get('date'))[:10]
        if key[0] not in ids or not start.isoformat() <= key[1] <= end.isoformat():
            continue
        value = number(row.get(metric))
        if key in cells and cells[key] != value:
            raise ValueError(f'同节点同日数据冲突：{key}')
        cells[key] = value
    known = [value for value in cells.values() if value is not None]
    expected = len(ids) * ((end - start).days + 1)
    coverage = len(known) / expected * 100 if expected else 0
    partial = '（未满周）' if end.weekday() != 6 else ''
    return (label, f'{fmt(sum(known) if known else None)}艘次',
            f'已披露{verb}艘次｜{start.isoformat()}—{end.isoformat()}{partial}',
            f'监测{len(catalog):,}个，独立统计{len(ids):,}个',
            f'日记录覆盖{coverage:.1f}%（{len(known):,}/{expected:,}）')


def asset_card(assets):
    from htfa.monitoring.energy_supply import production_units as production
    if not all('production_rows' in asset for asset in assets):
        chosen, rows, _, _ = production.statistical_view(assets)
        assets = production.map_units(assets, chosen, rows)
    scopes = {}
    for asset in assets:
        scopes.setdefault(asset['scope_id'], asset)
    producing = pending = 0
    records = {}
    for scope, asset in scopes.items():
        states = set(asset.get('operating_states') or ['unknown'])
        producing += states == {'producing'}
        pending += len(states) != 1 or bool(states & {'unknown', 'historical_unverified'})
        for row in asset['production_rows']:
            key = scope, row['商品']
            if key in records and records[key] != row:
                raise ValueError(f'同资产同商品产量冲突：{key}')
            records[key] = row
    values = {label: [] for label in production.STATISTICAL_PRODUCTS.values()}
    years, undated = set(), False
    for row in records.values():
        column = next((key for key in row if key.startswith('日产量（')), None)
        value = number(row.get(column))
        if row['商品'] not in values or value is None:
            continue
        values[row['商品']].append(value)
        year = str(row.get('数据时间', ''))
        if year.isdigit() and len(year) == 4:
            years.add(year)
        else:
            undated = True
    lines = ['各资产最新披露日产量合计（非同日）']
    for label, unit in [('原油', '万桶/日'), ('天然气', '百万立方米/日')]:
        if label in {row['商品'] for row in records.values()}:
            amount = f'{sum(values[label]):,.4f}'.rstrip('0').rstrip('.') if values[label] else '—'
            lines.append(f'{label} {amount} {unit}')
    basis = f'{min(years)}—{max(years)}年' if len(years) > 1 else f'{next(iter(years))}年' if years else '年份未明确'
    if undated and years:
        basis += '，部分年份未明确'
    lines.append(f'产量数据：{basis}；可汇总{sum(map(len, values.values()))}/{len(records)}条')
    count = len(scopes)
    lines.append(f'在产比例 {producing / count * 100:.1f}%（{producing}/{count}）' if count else '在产比例 —')
    lines.append(f'待确认比例 {pending / count * 100:.1f}%（{pending}/{count}）' if count else '待确认比例 —')
    return ('油田监测', f'{count:,}个', *lines)


def sea_activity_card(history, day):
    """Sum verified daily entry events across all four seas.

    Rows contain sea, date, and passages. Repeated confirmed entries by the
    same MMSI are separate passages. A reported zero is valid; missing sea/day
    records remain unavailable. AIS position samples are not passage events.
    """
    rows = [{'portid': row.get('sea'), 'date': row.get('date'),
             'passages': row.get('passages')} for row in history]
    values = [None] * 5
    if day:
        periods = windows(day)
        values[:2] = [total(rows, set(SEA_MONITORING_AREAS), 'passages', *window)
                      for window in periods[:2]]
        # Provider history consists of completed natural days. Use the latest
        # common completed day within THIS month, without moving the week anchor
        # backwards on Monday or silently presenting a previous month as current.
        coverage = {sea: {str(r.get('date'))[:10] for r in history
                          if r.get('sea') == sea and number(r.get('passages')) is not None}
                    for sea in SEA_MONITORING_AREAS}
        common = set.intersection(*coverage.values())
        current = sorted(d for d in common if day.replace(day=1).isoformat() <= d <= day.isoformat())
        if current:
            month_day = date.fromisoformat(current[-1])
            values[2:] = [total(rows, set(SEA_MONITORING_AREAS), 'passages', *window)
                          for window in windows(month_day)[2:]]
    week, prior_week, month, prior_month, prior_year = values
    return ('海域监测', f'{len(SEA_MONITORING_AREAS)}个',
            f'上周累计通过{fmt(week)}艘次（环比 {change(week, prior_week)}）',
            f'本月累计通过{fmt(month)}艘次（环比 {change(month, prior_month)}，同比 {change(month, prior_year)}）')


def build_cards(port_catalog, choke_catalog, port_history, choke_history,
                port_day, choke_day, vessel_day=None, assets=(), sea_passage_history=(), sea_observation_card=None):
    cards = [activity_card('港口监测', port_catalog, port_history, 'portcalls', '进港', port_day, True),
             activity_card('咽喉点监测', choke_catalog, choke_history, 'n_total', '通过', choke_day)]
    cards.append(asset_card(assets))
    return cards


def cards_html(cards, css_class='monitoring-cards'):
    def visible_lines(label, lines):
        if label in {'港口监测', '咽喉点监测', '油田监测'}:
            return []
        return lines
    return f'<div class="{css_class}">' + ''.join(
        '<div class="monitoring-card">' + f'<span>{escape(label)}</span>'
        + (f'<strong>{escape(value)}</strong>' if value else '')
        + ''.join(f'<div class="monitoring-card-detail">{escape(line)}</div>' for line in visible_lines(label, lines)) + '</div>'
        for label, value, *lines in cards) + '</div>'
