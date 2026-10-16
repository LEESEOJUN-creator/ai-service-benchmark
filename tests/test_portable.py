import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.session import append_event, read_session, status
from benchmark.audit import audit_session, summary_text, comparison_text
from benchmark.reporting import _rows, _time
from benchmark.charts import chart_groups
import test_session


class PortableTests(unittest.TestCase):
    def setUp(self):
        test_session.SessionTests.setUp(self)
        append_event(self.root, 'test-run', self.event)

    def timer(self, phase, at):
        with patch('benchmark.timing.clock_sample', return_value={'epoch_ms': 100000 + at, 'monotonic_ms': at}):
            return append_event(self.root, 'test-run', dict(kind='timing', request_id='mono-summary',
                                phase=phase, evidence='Synthetic UI observation for this request'))

    def finish(self, **fields):
        return append_event(self.root, 'test-run', dict(kind='result', request_id='mono-summary',
            status='success', answer='Synthetic answer', cost_status='unavailable', **fields))

    def test_null_custom_fields_are_filled_from_saved_clock(self):
        self.timer('start', 100)
        self.timer('generating', 800)
        self.timer('complete', 2500)
        result = self.finish(first_complete_observed_ms=None, last_generating_observed_ms=None)
        self.assertEqual(result['first_complete_observed_ms'], 2400)
        self.assertIsNone(result['last_generating_observed_ms'])
        self.assertIn('≤2.4초', _time(result))
        self.assertEqual(status(self.root, 'test-run')['timing_missing_do_not_resend'], [])

    def test_fresh_processes_preserve_timer_to_report_data(self):
        # No REPL state survives any boundary. The third process supplies null.
        script = ('import sys; from benchmark.session import append_event; '
                  'import json; append_event(sys.argv[1], "test-run", json.loads(sys.argv[2]))')
        for event in [dict(kind='timing', request_id='mono-summary', phase='start', evidence='ready'),
                      dict(kind='timing', request_id='mono-summary', phase='complete', evidence='answer end and complete control'),
                      dict(kind='result', request_id='mono-summary', status='success', answer='Synthetic',
                           cost_status='unavailable', first_complete_observed_ms=None)]:
            subprocess.run([sys.executable, '-c', script, str(self.root), json.dumps(event)], check=True,
                           cwd=Path(__file__).resolve().parents[1], capture_output=True)
        append_event(self.root, 'test-run', test_session.SessionTests.assessment(self))
        rows = _rows(read_session(self.root, 'test-run'))
        self.assertGreater(rows[0]['result']['first_complete_observed_ms'], 0)
        point = chart_groups(rows, {})['common-model']['services']['monogpt']['summary-01']
        self.assertGreater(point['time'], 0)
        self.assertTrue(point['time_label'].startswith('≤'))

    def test_repeated_start_or_completion_never_resets_clock(self):
        self.timer('start', 0)
        with self.assertRaises(ValueError): self.timer('start', 5)
        self.timer('complete', 100)
        with self.assertRaises(ValueError): self.timer('complete', 200)
        self.assertEqual(self.finish()['first_complete_observed_ms'], 100)

    def test_missing_completion_and_clock_anomaly_are_not_fabricated(self):
        self.timer('start', 100)
        with patch('benchmark.timing.clock_sample', return_value={'epoch_ms': 999999, 'monotonic_ms': 200}):
            append_event(self.root, 'test-run', dict(kind='timing', request_id='mono-summary', phase='complete', evidence='end'))
        result = self.finish()
        self.assertIsNone(result['first_complete_observed_ms'])
        self.assertIn('시계 불일치', result['timing_unavailable_reason'])

    def test_missing_completion_keeps_answer_no_paid_retry(self):
        self.timer('start', 100)
        self.assertIsNone(self.finish()['first_complete_observed_ms'])
        audit = audit_session(read_session(self.root, 'test-run'))
        self.assertIn('timing_missing', {i['code'] for i in audit['issues']})
        self.assertFalse(audit['automatic_retry'])

    def test_no_late_start_and_no_conflicting_manual_value(self):
        with self.assertRaises(ValueError): self.timer('complete', 100)
        self.timer('start', 0)
        self.timer('complete', 100)
        with self.assertRaises(ValueError): self.finish(first_complete_observed_ms=999)
        self.finish()
        with self.assertRaises(ValueError): self.timer('start', 200)

    def test_summary_and_revision_are_read_without_new_paid_request(self):
        self.finish()
        old = append_event(self.root, 'test-run', test_session.SessionTests.assessment(self))
        new = dict(test_session.SessionTests.assessment(self), supersedes_sequence=old['sequence'], revision_reason='Add answer evidence',
                   summary={'strength': '3개 항목을 구분', 'weakness': '기한 하나 누락',
                            'practical_impact': '누락 기한 보완 후 공유', 'evidence_ref': '답변 2행'})
        append_event(self.root, 'test-run', new)
        rows = _rows(read_session(self.root, 'test-run'))
        self.assertIn('누락 기한', summary_text(rows[0]['assessment']))
        self.assertEqual(status(self.root, 'test-run')['reserved'], 1)
        with self.assertRaises(ValueError): append_event(self.root, 'test-run', new)

    def test_audit_finds_sparse_comparison_capture_and_scope(self):
        self.finish()
        a = test_session.SessionTests.assessment(self)
        a['criteria'][0]['judgement'] = '좋음'
        append_event(self.root, 'test-run', a)
        codes = {i['code'] for i in audit_session(read_session(self.root, 'test-run'))['issues']}
        self.assertTrue({'scope_missing', 'vague_assessment', 'answer_summary_missing', 'capture_unverified', 'ux_missing'} <= codes)

    def test_model_coverage_includes_missing_gemini(self):
        doc = read_session(self.root, 'test-run')
        doc['report_scope'] = {'origin':'init_snapshot', 'models':[
            {'id': 'gemini', 'enabled': True, 'services': ['monogpt', 'timely'], 'case_ids': ['summary-01']}]}
        review = audit_session(doc)
        self.assertEqual(len(review['coverage'][0]['missing']), 2)

    def test_capture_verified_requires_actual_evidence_field(self):
        with self.assertRaises(ValueError): self.finish(answer_capture_verified=True)
        self.finish(answer_capture_verified=True, capture_evidence='UI final line compared to saved answer')

    def test_comparison_text_preserves_explicit_practical_impact(self):
        self.assertIn('사용 전 수정', comparison_text({'conclusion':'같은 점수', 'practical_impact':'담당자 지정 필요'}))
        source = Path(__file__).resolve().parents[1]
        example = json.loads((source/'examples/review-example.json').read_text())
        cases = json.loads((source/'cases/core.json').read_text())['cases']
        rubric = next(c['rubric'] for c in cases if c['id'] == example['case_id'])
        self.assertEqual([c['criterion'] for c in example['assessment']['criteria']], rubric)
        self.assertTrue(all(len(answer.splitlines()) == 3 for answer in example['answers'].values()))
