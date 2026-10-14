import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from benchmark.session import initialize, append_event, status, session_dir
from benchmark.reporting import report


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'cases').mkdir()
        (self.root / 'cases/core.json').write_text(json.dumps({'cases':[
            {'id':'summary-01','turns':['<script>hi</script>'],'fixture_ids':[]},
            {'id':'pending-01','turns':['pending'],'fixture_ids':[]}]}))
        initialize(self.root, 'test-run')
        self.event = dict(kind='reserve',request_id='mono-summary',service='monogpt',
            model='common-model',reasoning='low',case_id='summary-01',
            ui_evidence='UI selected low',authorization_scope='limited pilot acknowledged',
            prompt='<script>hi</script>',prompt_sha256=hashlib.sha256(b'<script>hi</script>').hexdigest(),
            comparison_tier='ui_matched',fixtures={},feature_settings={'search':'off'},
            request_limit=2,cost_mode='request_limited_unknown_price',unknown_price_acknowledged=True)
    def test_round_trip_and_escape(self):
        append_event(self.root,'test-run',self.event)
        self.assertEqual(status(self.root,'test-run')['reserved'],1)
        append_event(self.root,'test-run',dict(kind='result',request_id='mono-summary',status='success',
            answer='<script>alert(1)</script>',cost_status='unavailable',cost=None))
        path=Path(report(self.root,'test-run')['report'])
        self.assertNotIn('<script>',path.read_text())
        self.assertIn('pending-01',path.read_text())
    def test_duplicate_and_unresolved_block(self):
        append_event(self.root,'test-run',self.event)
        with self.assertRaises(ValueError): append_event(self.root,'test-run',self.event)
        other=dict(self.event,request_id='other')
        with self.assertRaises(ValueError): append_event(self.root,'test-run',other)
    def test_prompt_hash(self):
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(self.event,prompt_sha256='bad'))
    def test_unknown_reasoning(self):
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(self.event,reasoning='not_exposed'))
    def test_condition_mismatch(self):
        append_event(self.root,'test-run',self.event)
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(self.event,request_id='timely-summary',service='timely',reasoning='high'))
    def test_cost_unavailable_not_zero(self):
        append_event(self.root,'test-run',self.event)
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(kind='result',request_id='mono-summary',status='timeout',cost_status='unavailable',cost=0))
    def test_no_path_escape_or_overwrite(self):
        with self.assertRaises(ValueError): session_dir(self.root,'../outside')
        with self.assertRaises(FileExistsError): initialize(self.root,'test-run')
    def test_limit(self):
        append_event(self.root,'test-run',dict(self.event,request_limit=1))
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(self.event,request_id='timely-summary',service='timely'))
    def test_result_requires_reservation(self):
        with self.assertRaises(ValueError): append_event(self.root,'test-run',dict(kind='result',request_id='absent',status='timeout',cost_status='unavailable'))
