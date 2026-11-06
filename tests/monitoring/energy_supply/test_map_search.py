"""Search retains stable identities and enables only the selected map layer."""
import json
from pathlib import Path
from unittest.mock import patch
from htfa.monitoring.energy_supply.ui import pipeline_popups
import unittest

import htfa.monitoring.energy_supply.data.storage as data_store
import htfa.monitoring.energy_supply.ui.map_renderer as map_renderer
import htfa.monitoring.energy_supply.processing.pipeline_catalog as pipeline_catalog
import htfa.monitoring.energy_supply.ui.map_panel as dashboard_views
ROOT = Path(__file__).resolve().parents[1]


class MapSearchTest(unittest.TestCase):
    def test_same_names_keep_distinct_source_keys_and_only_mapped_features_are_searchable(self):
        rows = map_renderer.search_objects(
            [{'name':'Same','country':country,'map_drawable':True} for country in ('Iran','Iraq')],
            [{'portid':pid,'name':'Same'} for pid in ('port1','port2')],
            [{'mmsi':str(pid),'name':'Same'} for pid in (1,2)])
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row['key'] for row in rows}), 6)
        self.assertFalse(any(row['key']=='pipeline:ADNOC_WEST_EAST_2026' for row in rows))
        self.assertTrue(any('· 1' in row['label'] for row in rows if row['key']=='vessel:1'))

    def test_focus_callback_enables_hidden_layer_before_widgets_render(self):
        state = {'energy_supply_map_search_object':'port:port1','energy_supply_map_show_ports':False,'energy_supply_map_show_vessels':False}
        with patch.object(dashboard_views.st, 'session_state', state):
            dashboard_views.queue_map_focus({'port:port1':'energy_supply_map_show_ports'})
        self.assertTrue(state['energy_supply_map_show_ports'])
        self.assertFalse(state['energy_supply_map_show_vessels'])
        self.assertEqual(state['energy_supply_map_search_request'], {'key':'port:port1','revision':1})

    def test_unmapped_record_preserves_unknown_capacity_and_has_no_invented_route(self):
        document = data_store.read_json('data/pipeline_projects.json')
        with patch('htfa.monitoring.energy_supply.data.storage.read_json', return_value=document):
            projects = pipeline_catalog.load_unmapped_projects()
        self.assertEqual(projects[0]['status'], 'construction')
        self.assertIsNone(projects[0]['geometry'])
        self.assertIsNone(projects[0]['capacity_million_bpd'])
        self.assertIn('2027', pipeline_popups.unmapped_popup(projects[0]))
        self.assertIn('百万桶/日', pipeline_popups.unmapped_popup(projects[0]))
        document['projects'][0]['geometry'] = {'type':'LineString','coordinates':[[1,2],[3,4]]}
        with patch('htfa.monitoring.energy_supply.data.storage.read_json', return_value=document):
            with self.assertRaisesRegex(ValueError, '证据无效'):
                pipeline_catalog.load_unmapped_projects()
