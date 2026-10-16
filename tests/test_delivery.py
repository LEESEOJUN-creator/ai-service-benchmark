"""Synthetic 40-cell integration regression. No browser, accounts or paid calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmark.session import initialize, append_event, read_session
from benchmark.audit import audit_session
from benchmark.reporting import report


def build_demo(root):
    source = Path(__file__).resolve().parents[1]
    (root / 'cases').mkdir(parents=True)
    (root / 'config').mkdir()
    (root / 'fixtures').mkdir()
    cases = json.loads((source / 'cases/core.json').read_text())
    config = json.loads((source / 'config/benchmark.json').read_text())
    for case in cases['cases']:
        case['enabled'] = True
    (root / 'cases/core.json').write_text(json.dumps(cases))
    (root / 'config/benchmark.json').write_text(json.dumps(config))
    fixture = root / 'fixtures/synthetic.txt'
    fixture.write_text('SYNTHETIC TEST ONLY. Never upload this placeholder as a real image.')
    fixture_info = {'path':'fixtures/synthetic.txt', 'sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    'reviewed':True, 'allowed_services':['monogpt','timely','chatgpt']}
    run = 'synthetic-validation'
    initialize(root, run)
    append_event(root, run, {'kind':'note','text':'합성 회귀 검증 데이터. 실제 서비스 응답·비용·품질·속도 결과가 아닙니다.'})
    idx = 0
    for model in config['models']:
        for case in cases['cases']:
            if case['id'] not in model.get('case_ids', [c['id'] for c in cases['cases']]):
                continue
            observations = []
            for service in model['services']:
                idx += 1
                key = f'synthetic-{idx}'
                prompt = case['turns'][0]
                append_event(root, run, {'kind':'reserve', 'request_id':key, 'candidate_id':model['id'],
                    'service':service, 'model':model['report_label'], 'model_group':model['report_label'],
                    'reasoning':'low', 'case_id':case['id'], 'prompt':prompt,
                    'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(), 'ui_evidence':'Synthetic only',
                    'authorization_scope':'Synthetic test: no UI calls authorized', 'request_limit':40,
                    'comparison_tier':'ui_matched', 'feature_settings':{'search':'off'},
                    'fixtures':{f:fixture_info for f in case['fixture_ids']},
                    'excluded_services':model.get('excluded_services', {}),
                    'cost_mode':'request_limited_unknown_price', 'unknown_price_acknowledged':True})
                for phase, delta in [('start', 0), ('complete', 10000 + idx * 100)]:
                    with patch('benchmark.timing.clock_sample', return_value={'epoch_ms':1000000 + delta, 'monotonic_ms':delta}):
                        append_event(root, run, {'kind':'timing','request_id':key,'phase':phase,'evidence':'Synthetic clock'})
                append_event(root, run, {'kind':'result','request_id':key,'status':'success',
                    'answer':'합성 답변: 보고서 데이터 연결과 레이아웃 검증용이며 실제 모델 답변이 아닙니다.',
                    'answer_capture_verified':True,'capture_evidence':'Synthetic fixture, no live UI',
                    'cost':None if service == 'chatgpt' else idx, 'cost_unit':'credits',
                    'cost_status':'unavailable' if service == 'chatgpt' else 'balance_observed'})
                append_event(root, run, {'kind':'assessment','request_id':key,'evaluator':'Synthetic test','blind':False,
                    'summary':{'strength':'합성 예시: 요구 조건을 확인한 근거가 요약과 상세 표에 연결되는지 검사한다.',
                               'weakness':'실제 모델 답변이 아니므로 이 점수를 서비스 평가로 사용할 수 없다.',
                               'practical_impact':'새 세션이 동일한 출력 구성으로 결과를 생성하는 코드 경로를 검증하는 용도다.',
                               'evidence_ref':'test_delivery.py의 합성 평가 데이터'},
                    'criteria':[{'criterion':c,'score':3,'observation':'합성 관찰: 출력 시 각 기준과 근거 위치가 연결된다.',
                                 'judgement':'합성 점수 3은 실제 품질 평가가 아니라 셀·표 전달 검증값이다.',
                                 'evidence_ref':'합성 답변과 테스트 정의'} for c in case['rubric']]})
                observations.append({'request_id':key,'observation':'합성 서비스 관찰. 실제 결과로 해석하지 않는다.',
                                     'evidence_ref':'합성 답변'})
            append_event(root, run, {'kind':'comparison','model_group':model['report_label'],'case_id':case['id'],
                'conclusion':'합성 비교: 같은 점수에서도 해설을 생략하지 않는 출력 경로를 검사한다.',
                'common_ground':'모든 칸에 동일한 합성 평가 기준을 사용했다.',
                'differences':'실제 답변 차이는 측정하지 않았다. 금액·시간은 그래프 검증용 가상 수치다.',
                'practical_impact':'실사용 판단에는 쓰지 않고 실제 측정 보고서의 누락 방지 회귀 검사에만 사용한다.',
                'observations':observations})
    for service in config['services']:
        append_event(root, run, {'kind':'ux','service':service,'observations':[
            {'aspect':'합성 UX','observation':'실제 화면을 사용하지 않음','evidence':'테스트 정의'}]})
    return run


@unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('openpyxl'),
                     'Optional report dependencies needed')
class DeliveryTests(unittest.TestCase):
    def test_forty_cells_three_models_three_files_no_missing_time(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = build_demo(root)
            audit = audit_session(read_session(root, run))
            self.assertEqual(audit['issues'], [])
            self.assertEqual((audit['successes'], audit['timed']), (40, 40))
            self.assertEqual([c['expected'] for c in audit['coverage']], [24, 8, 8])
            output = report(root, run, credit_rates={'monogpt':1,'timely':2}, output_dir=root/'exports')
            self.assertEqual(len(list((root/'exports').iterdir())), 3)
            self.assertEqual(output['timing_missing'], [])
            book = load_workbook(output['workbook'], data_only=True)
            self.assertEqual(len(book.sheetnames), 6)
            ledger = book['실측 원장']
            self.assertEqual(ledger.max_row - 4, 40)
            self.assertTrue(all('초' in ledger.cell(i, 15).value for i in range(5, 45)))
            labels = {book['모델별 요약'].cell(i, 1).value for i in range(5, book['모델별 요약'].max_row + 1)}
            self.assertTrue({'GPT-6 Sol', 'Claude Sonnet 5.5', 'Gemini'} <= labels)
            self.assertIn('사용 시 영향', book['서비스 비교']['C5'].value)
            self.assertIn('사용 전 수정', book['서비스 비교']['F5'].value)


if __name__ == '__main__':
    # Optional disposable preview. Never writes into the user's report folder.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run = build_demo(root)
        print(json.dumps(report(root, run, credit_rates={'monogpt':1,'timely':2},
                                output_dir=sys.argv[1]), ensure_ascii=False, indent=2))
