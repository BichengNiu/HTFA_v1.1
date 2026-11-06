"""Local aggregates and the pinned Ts rendering retain calendar gaps."""
from contextlib import contextmanager
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import duckdb
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply import port_charts
from htfa.monitoring.energy_supply.portwatch_records import SHIP_TYPES


class PortChartsTest(unittest.TestCase):
    def test_calendar_windows_handle_leap_days_month_ends_and_available_history(self):
        earliest = date(2019,1,1)
        last = date(2026,10,9)
        expected = [date(2026,10,3),date(2026,9,10),date(2026,7,10),date(2026,4,10),
                    date(2025,10,10),date(2023,10,10),date(2021,10,10),earliest,earliest]
        self.assertEqual([port_charts.window_start(last,p,earliest) for p in port_charts.TIME_RANGES],expected)
        self.assertEqual(port_charts.window_start(date(2024,2,29),'近1年',earliest),date(2023,3,1))
        self.assertEqual(port_charts.window_start(date(2026,3,31),'近1个月',earliest),date(2026,3,1))

    def test_calendar_totals_clip_window_and_preserve_missing_values(self):
        rows = tuple((date(2025,12,29)+timedelta(days=i), *[1]*6) for i in range(8))
        for aggregation, totals in [('周度', [7,1]), ('月度', [3,5]), ('年度', [3,5])]:
            result = port_charts.aggregate_rows(rows, rows[0][0], aggregation)
            self.assertEqual([r['portcalls'] for r in result], totals)
            self.assertEqual(sum(r['portcalls'] for r in result), 8)
        clipped = port_charts.aggregate_rows(rows, date(2025,12,31), '周度')
        self.assertEqual([r['portcalls'] for r in clipped], [5,1])
        self.assertEqual(clipped[0]['period_start'], date(2025,12,31))
        self.assertEqual(clipped[-1]['period_end'], date(2026,1,5))
        incomplete = tuple(row for row in rows if row[0] != date(2026,1,2))
        self.assertIsNone(port_charts.aggregate_rows(incomplete, rows[0][0], '月度')[1]['portcalls'])
        missing = (*rows[:-1], (*rows[-1][:-1], None))
        yearly = port_charts.aggregate_rows(missing, rows[0][0], '年度')
        self.assertEqual(yearly[1]['portcalls'], 5)
        self.assertIsNone(yearly[1]['portcalls_tanker'])

    def test_annual_totals_render_as_bars(self):
        from Ts.TsPlots import plot_series
        seen = []
        def plot(*args, **kwargs):
            figure, axis = plot_series(*args, **kwargs)
            seen.append(([p.get_height() for p in axis.patches], len(axis.lines)))
            return figure, axis
        rows = tuple((date(2025,12,29)+timedelta(days=i), *[1]*6) for i in range(8))
        with patch('Ts.TsPlots.plot_series', side_effect=plot):
            images = port_charts.chart_images.__wrapped__(rows, rows[0][0], '年度')
        self.assertEqual(len(images), 6)
        self.assertEqual(seen, [([3,5], 0)]*6)

    def test_sql_complete_coverage_zero_gaps_invalid_values_and_cutoff(self):
        conn=duckdb.connect(':memory:')
        conn.execute(data_store.SCHEMA)
        @contextmanager
        def connection():
            yield conn
        rows=[]
        for day in ('2026-10-01','2026-10-02','2026-10-04','2026-10-05'):
            for pid in ('port1','port2'):
                record={'portid':pid,'date':day,'portcalls':0,
                        **{f'portcalls_{kind}':0 for kind in SHIP_TYPES}}
                if day=='2026-10-02' and pid=='port2':continue
                if day=='2026-10-04':
                    record['portcalls']=3
                    record['portcalls_tanker']=3 if pid=='port1' else -1
                rows.append(record)
        data_store.save_portwatch('ports',rows,'test',conn=conn)
        with patch('htfa.monitoring.energy_supply.data_store.connect',connection):
            result=data_store.portwatch_daily_totals(('port1','port2','port1'),date(2026,10,4))
        self.assertEqual([r['date'] for r in result],[date(2026,10,i) for i in range(1,5)])
        self.assertEqual(result[0]['portcalls'],0)
        self.assertIsNone(result[1]['portcalls'])
        self.assertIsNone(result[2]['portcalls'])
        self.assertEqual(result[3]['portcalls'],6)
        self.assertIsNone(result[3]['portcalls_tanker'])
        conn.close()

    def test_chart_calls_ts_and_keeps_missing_day_in_line(self):
        from Ts.TsPlots import plot_series
        import matplotlib.pyplot as plt
        seen=[]
        def plot(*args,**kwargs):
            figure,ax=plot_series(*args,**kwargs)
            seen.append((list(args[0].index.date),ax.lines[0].get_ydata().copy(),len(ax.lines),kwargs))
            return figure,ax
        rows=tuple((date(2026,10,day),*[value]*6) for day,value in [(1,0),(2,None),(3,6)])
        before=plt.get_fignums()
        with patch('Ts.TsPlots.plot_series',side_effect=plot):
            images=port_charts.chart_images.__wrapped__(rows,date(2026,10,1))
        self.assertEqual(len(images),6)
        self.assertTrue(all(image.startswith(b'\x89PNG') for image in images))
        self.assertEqual(len(seen),6)
        self.assertEqual([x[2] for x in seen],[1]*6)
        import numpy as np
        self.assertTrue(np.isnan(seen[0][1][1]))
        self.assertEqual(seen[0][0],[date(2026,10,i) for i in range(1,4)])
        self.assertFalse(seen[1][3]['auto_dual_y'])
        self.assertEqual(plt.get_fignums(),before)

    def test_year_background_clears_month_labels_and_stays_inside_image(self):
        from matplotlib.figure import Figure
        save = Figure.savefig
        checked = []

        def inspect(figure, *args, **kwargs):
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            axis = figure.axes[0]
            months = [text.get_window_extent(renderer) for text in axis.get_xticklabels() if text.get_text()]
            years = [text.get_bbox_patch().get_window_extent(renderer) for text in axis.texts
                     if text.get_text().strip().endswith('年')]
            self.assertTrue(years)
            self.assertLess(max(box.y1 for box in years)+5, min(box.y0 for box in months))
            self.assertGreaterEqual(min(box.y0 for box in years), 0)
            checked.append(True)
            return save(figure, *args, **kwargs)

        for days in (90, 365):
            rows = tuple((date(2026,10,9)-timedelta(days=offset), *[10]*6)
                         for offset in reversed(range(days)))
            with patch.object(Figure, 'savefig', autospec=True, side_effect=inspect):
                port_charts.chart_images.__wrapped__(rows, rows[0][0])
        self.assertEqual(len(checked), 12)
