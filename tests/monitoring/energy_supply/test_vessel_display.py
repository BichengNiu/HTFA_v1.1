"""Consistent display labels without altering source observations."""
import unittest
from unittest.mock import patch
from htfa.monitoring.energy_supply import map_renderer
from htfa.monitoring.energy_supply import dashboard_rows
from htfa.monitoring.energy_supply import vessel_charts
from htfa.monitoring.energy_supply.vessel_display import destination_text, reception_time, source_label


class VesselDisplayTest(unittest.TestCase):
    def test_known_names_abbreviations_and_uncertain_text(self):
        self.assertEqual(destination_text('AEJEA'), '杰贝阿里')
        self.assertEqual(destination_text(' ZAKUM_FIELD '), '扎库姆油田')
        self.assertEqual(destination_text('FOR ORDERS'), '等待指令')
        self.assertEqual(destination_text('AEJEA>AEFJR'), '杰贝阿里 → 富查伊拉')
        self.assertEqual(destination_text('unknown'), '未知目的地')
        self.assertEqual(destination_text('UNVERIFIED-42'), '目的地待核（UNVERIFIED-42）')

    def test_reception_time_uses_dubai_hour_with_date_rollover(self):
        self.assertEqual(reception_time('2026-10-24T23:59:59Z'), '2026年10月25日3时')
        self.assertEqual(reception_time('2026-10-24T04:00:26+00:00'), '2026年10月24日8时')
        self.assertEqual(reception_time(None), '—')

    def test_shared_labels_across_filter_table_and_map_preserve_source(self):
        row = {'mmsi':'123','lat':26,'lon':53,'destination':'ZAKUM FIELD',
               'received_at':'2026-10-24T04:00:26Z', 'data_source':'Open Waters · udp:receiver'}
        original = dict(row)
        self.assertEqual(vessel_charts.destination_label(row), '扎库姆油田')
        self.assertTrue(vessel_charts.matches(row,['未知船籍'],['扎库姆油田']))
        record=dashboard_rows.vessel_rows([row])[0]
        self.assertEqual(record['目的地'], '扎库姆油田')
        self.assertEqual(record['接收时间（迪拜）'], '2026年10月24日8时')
        self.assertEqual(record['数据源'], 'openwaters')
        with patch('htfa.monitoring.energy_supply.map_renderer.compressed_document',side_effect=lambda html:html):
            html=map_renderer.build_map_html([],[],[],[row],'','',asset_popup=lambda r:'',
                port_popup=lambda r:'',chokepoint_popup=lambda r:'')
        self.assertIn('扎库姆油田',html)
        self.assertIn('2026年10月24日8时',html)
        self.assertEqual(source_label({'data_source':'AISStream'}),'AISStream')
        self.assertEqual(row,original)


if __name__=='__main__':
    unittest.main()
