import copy
import hashlib
import importlib.util
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
            {'id':'summary-01','turns':['<script>hi</script>'],'fixture_ids':[],
             'rubric':['정확성','근거']},
            {'id':'pending-01','turns':['pending'],'fixture_ids':[],
             'rubric':['정확성','근거'] }]}))
        initialize(self.root, 'test-run')
        self.event = dict(kind='reserve',request_id='mono-summary',service='monogpt',
            model='common-model',reasoning='low',case_id='summary-01',
            ui_evidence='UI selected low',authorization_scope='limited pilot acknowledged',
            prompt='<script>hi</script>',prompt_sha256=hashlib.sha256(b'<script>hi</script>').hexdigest(),
            comparison_tier='ui_matched',fixtures={},feature_settings={'search':'off'},
            request_limit=2,cost_mode='request_limited_unknown_price',unknown_price_acknowledged=True)
    def success(self):
        append_event(self.root,'test-run',self.event)
        append_event(self.root,'test-run',dict(kind='result',request_id='mono-summary',status='success',
            answer='=HYPERLINK("bad") <script>alert(1)</script>',cost_status='unavailable',cost=None))
    def assessment(self):
        return dict(kind='assessment',request_id='mono-summary',evaluator='test reviewer',blind=False,
                    criteria=[dict(criterion='정확성',score=3,observation='핵심 내용을 확인함',
                                   judgement='한 조건이 누락됨',evidence_ref='답변 첫 문장'),
                              dict(criterion='근거',score=4,observation='근거 위치가 명시됨',
                                   judgement='요구 근거를 충족함',evidence_ref='답변 둘째 문장')])
    def test_assessment_requires_success_and_evidence(self):
        append_event(self.root,'test-run',self.event)
        with self.assertRaises(ValueError):
            append_event(self.root,'test-run',self.assessment())
        append_event(self.root,'test-run',dict(kind='result',request_id='mono-summary',status='success',
            answer='answer',cost_status='unavailable',cost=None))
        bad=self.assessment()
        bad['criteria'][0]['evidence_ref']=''
        with self.assertRaises(ValueError):
            append_event(self.root,'test-run',bad)
        append_event(self.root,'test-run',self.assessment())
        with self.assertRaises(ValueError):
            append_event(self.root,'test-run',self.assessment())
    def test_ux_requires_observation_and_evidence(self):
        with self.assertRaises(ValueError):
            append_event(self.root,'test-run',dict(kind='ux',service='monogpt',
                observations=[dict(aspect='가독성',observation='좋음',evidence='')]))
        append_event(self.root,'test-run',dict(kind='ux',service='monogpt',
            observations=[dict(aspect='가독성',observation='표의 제목과 숫자가 구분됨',evidence='화면 캡처 1')]))
    def test_report_blocks_unassessed_success(self):
        self.success()
        with self.assertRaises(ValueError):
            report(self.root,'test-run',report_date='2026-10-15')
    @unittest.skipUnless(importlib.util.find_spec('openpyxl') and importlib.util.find_spec('reportlab'),
                         'PDF/XLSX optional dependencies not installed')
    def test_dated_pdf_xlsx_and_literal_answer(self):
        from openpyxl import load_workbook
        self.event['excluded_services']={'chatgpt':'synthetic not offered'}
        self.success()
        append_event(self.root,'test-run',self.assessment())
        output=report(self.root,'test-run',report_date='2026-10-15')
        pdf,xlsx=Path(output['report']),Path(output['workbook'])
        self.assertEqual(pdf.parent,xlsx.parent)
        self.assertEqual(sorted(p.suffix for p in pdf.parent.iterdir()),['.pdf','.xlsx'])
        self.assertIn('2026-10-15',pdf.name)
        self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
        book=load_workbook(xlsx)
        self.assertEqual(book['기준별 평가']['F5'].value,3)
        self.assertIn('모델 없음',book['서비스 비교']['E5'].value)
        self.assertEqual(book['실측 원장']['I5'].value,"=SUM('기준별 평가'!F5:F6)")
        self.assertEqual(load_workbook(xlsx,data_only=True)['실측 원장']['I5'].value,7)
        self.assertEqual(book['답변 원문']['F5'].data_type,'s')
        self.assertTrue(book['답변 원문']['F5'].value.startswith('=HYPERLINK'))
        with self.assertRaises(FileExistsError):
            report(self.root,'test-run',report_date='2026-10-15')
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
