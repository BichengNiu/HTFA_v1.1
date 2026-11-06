"""Port views share calendar-week counts, missingness without operating status."""
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import htfa.monitoring.energy_supply.ui.dashboard_rows as dashboard_rows
import htfa.monitoring.energy_supply.processing.portwatch as portwatch
from htfa.monitoring.energy_supply.ui.map_popups import port_popup
from htfa.monitoring.energy_supply.contracts.records import PORT_METRICS


class PortPopupTest(unittest.TestCase):
    def week(self, day=date(2026,10,9), missing_day=False):
        rows = {day - timedelta(days=i): {**{field:0 for field in PORT_METRICS},
                'portcalls': i+1, 'portcalls_tanker':i+1} for i in range(7)}
        if missing_day:
            rows.pop(day-timedelta(days=1))
        with patch('htfa.monitoring.energy_supply.processing.portwatch._activity_rows', return_value={'port105':rows}):
            return portwatch.week_to_date_activity(day,('port105',))['port105']

    def test_calendar_week_excludes_previous_week_and_popup_is_compact(self):
        weekly = self.week()
        self.assertEqual(weekly['week_start'],'2026-10-05')
        self.assertEqual(weekly['week_calls'],15)
        port = {**weekly,'name':'Das Island','name_cn':'达斯岛港','has_data':True,
                'portcalls':1,'port_operating_status':'normal','port_operating_status_as_of':'2026-10-09'}
        html = port_popup(port,'2026-10-09')
        for text in ('达斯岛港（Das Island）','当日进港艘次','本周累计艘次','15 艘次','15艘次（100.0%）','width:100.0%'):
            self.assertIn(text,html)
        for text in ('class="basis"','class="country"','class="source"','活动指数','过去7天','风险运力','统计覆盖','运行状态','经营状态','正常','停运','未知'):
            self.assertNotIn(text,html)
        self.assertEqual(html.count('class="mix-row"'),5)
        self.assertEqual(self.week(date(2026,10,12))['week_calls'],1)
        self.assertEqual(self.week(date(2026,1,1))['week_start'],'2025-12-29')
        self.assertEqual(self.week(date(2026,1,1))['week_calls'],10)

    def test_gap_is_missing_and_zero_calls_do_not_imply_closed(self):
        weekly = self.week(missing_day=True)
        self.assertIsNone(weekly['week_calls'])
        html = port_popup({**weekly,'name':'Test','has_data':True,'portcalls':0},'2026-10-09')
        self.assertNotIn('运行状态',html)
        self.assertIn('0 艘次',html)
        self.assertIn('本周累计艘次</span><strong>— 艘次',html)
        self.assertNotIn('停运',html)
        html = port_popup({'name':'Test','port_operating_status':'closed','port_operating_status_as_of':'2026-10-10'},'2026-10-09')
        self.assertNotIn('运行状态',html)
        self.assertNotIn('停运',port_popup({'name':'Test','port_operating_status':'closed'},'2026-10-09'))

    def test_table_order_chinese_country_and_weighted_metric_shares(self):
        one={'statistics_available':True,'has_data':True,'portcalls':1,'week_calls':9,
             **{f'week_calls_{kind}':9 if kind=='tanker' else 0 for kind in portwatch.SHIP_TYPES}}
        two={**one,'portcalls':2,'week_calls':91,'week_calls_tanker':0,'week_calls_container':91}
        no_stats={'statistics_available':False,'portcalls':999,'week_calls':999}
        metrics=dict(dashboard_rows.port_metrics([one,two,no_stats]))
        self.assertEqual(len(metrics),8)
        self.assertEqual(metrics['港口总数'],3)
        self.assertEqual(metrics['当日进港艘次'],'3')
        self.assertEqual(metrics['本周累计艘次'],'100')
        self.assertEqual(metrics['本周油轮/液货船艘次/占比'],'9（9.0%）')
        rows=dashboard_rows.port_rows([{**one,'name':'Dubai','name_cn':'迪拜港','country':'United Arab Emirates'}],date(2026,10,9))
        self.assertEqual(list(rows[0]),['港口名','港口类型','业务特点','国家','水域','日期','当日进港艘次','本周累计艘次',
            '本周集装箱船累计艘次','本周干散货船累计艘次','本周普通货船累计艘次','本周滚装船累计艘次','本周油轮/液货船累计艘次','本月累计艘次','本月集装箱船累计艘次','本月干散货船累计艘次','本月普通货船累计艘次','本月滚装船累计艘次','本月油轮/液货船累计艘次','纬度','经度','来源'])
        self.assertEqual(rows[0]['国家'],'阿联酋')
        self.assertNotIn('经营状态', rows[0])
        self.assertEqual(rows[0]['港口名'],'迪拜港（Dubai）')


    def test_missing_port_does_not_blank_available_metrics_and_shares_use_one_cohort(self):
        available = {'statistics_available': True, 'has_data': True, 'portcalls': 3,
                     'week_calls': 10,
                     **{f'week_calls_{kind}': 10 if kind == 'tanker' else 0 for kind in portwatch.SHIP_TYPES}}
        missing = {'statistics_available': True, 'has_data': False}
        partial = {**available, 'portcalls': 2, 'week_calls': 99, 'week_calls_tanker': None}
        values = [value for _, value in dashboard_rows.port_metrics([available, missing, partial])]
        self.assertEqual(values[:3], [3, '5', '10'])
        self.assertEqual(values[-1], '10（100.0%）')
        self.assertEqual(values[3], '0（0.0%）')
        absent = [value for _, value in dashboard_rows.port_metrics([missing])]
        self.assertEqual(absent[1:3], ['—', '—'])

    def test_metric_labels_use_actual_day_and_calendar_week(self):
        labels = [label for label, _ in dashboard_rows.port_metrics([], date(2026, 1, 1))]
        self.assertEqual(labels[1], "当日进港艘次\n（2026年01月01日）")
        self.assertEqual(labels[2], "本周累计艘次\n（2025年12月29日-2026年01月01日）")
        self.assertTrue(all(label.endswith("（2025年12月29日-2026年01月01日）") for label in labels[2:]))

    def test_types_use_reviewed_facilities_not_observed_traffic(self):
        from htfa.monitoring.energy_supply.processing.port_types import port_type_label, port_business_label
        self.assertIn("综合港 / 油品枢纽", port_business_label({'portid':'port362'}))
        self.assertIn("综合港 / 集装箱枢纽", port_business_label({'portid':'port744'}))
        self.assertIn('液化石油气', port_type_label({'portid':'wpi48406','name':'Khawr Al Zubair Lng Terminal'}))
        self.assertIn('液化石油气', port_type_label({'portid':'port22','name':'Al Hamriyah LPG Terminal'}))
        self.assertRegex(port_type_label({'portid':'wpi48265','name':'Fateh Oil Terminal'}), '原油|油品')
        self.assertEqual(port_type_label({'name':'Unknown', 'week_calls_tanker':100}), '待核实')

    def test_month_cumulative_requires_complete_days_without_operating_status(self):
        day=date(2026,6,29)
        rows={day-timedelta(days=i):{**{field:0 for field in PORT_METRICS},'portcalls':2,'portcalls_tanker':2} for i in range(29)}
        with patch('htfa.monitoring.energy_supply.processing.portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity(day,('port105',))['port105']
        self.assertEqual(result['month_calls'],58)
        self.assertEqual(result['month_calls_tanker'],58)
        self.assertEqual(result['week_calls'],2)
        self.assertNotIn('recent_daily_activity_normal', result)
        rows.pop(day-timedelta(days=12))
        with patch('htfa.monitoring.energy_supply.processing.portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity(day,('port105',))['port105']
        self.assertIsNone(result['month_calls'])
        self.assertEqual(result['week_calls'],2)
        self.assertNotIn('recent_daily_activity_normal', result)
        rows[day]['portcalls']=0
        with patch('htfa.monitoring.energy_supply.processing.portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity(day,('port105',))['port105']
