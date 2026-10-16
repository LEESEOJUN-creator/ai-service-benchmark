import unittest
from benchmark.charts import chart_groups, _observed_time
from benchmark.costs import normalize_rates


class ChartTests(unittest.TestCase):
    def row(self, service, case, *, cost=None, score=3, status='success'):
        return {'group':'model','case':{'id':case},
                'request':{'service':service,'model':'model','reasoning':'low','comparison_tier':'ui_matched'},
                'result':{'status':status,'cost':cost,'cost_unit':'credits'},
                'assessment':{'criteria':[{'score':score}]}}

    def test_question_alignment_and_missing_cost_not_zero(self):
        rows=[self.row('monogpt','a',cost=58),self.row('monogpt','b',cost=10),
              self.row('timely','b',cost=43),self.row('chatgpt','a')]
        group=chart_groups(rows,normalize_rates({'monogpt':1,'timely':2}))['model']
        self.assertEqual(group['cases'],['a','b'])
        self.assertEqual(group['services']['timely']['b']['cost'],86)
        self.assertNotIn('a',group['services']['timely'])
        self.assertIsNone(group['services']['chatgpt']['a']['cost'])

    def test_failed_request_keeps_cost_but_has_no_quality_point(self):
        row=self.row('timely','a',cost=38,status='service_error')
        point=chart_groups([row],normalize_rates({'timely':2}))['model']['services']['timely']['a']
        self.assertEqual(point['cost'],76)
        self.assertIsNone(point['quality'])

    def test_duplicate_final_question_requires_resolution(self):
        row=self.row('monogpt','a')
        with self.assertRaisesRegex(ValueError,'중복 최종 결과'):
            chart_groups([row,row],{})

    def test_time_preserves_observation_interval_in_seconds(self):
        row=self.row('monogpt','a')
        row['result'].update(last_generating_observed_ms=23100,first_complete_observed_ms=32500)
        point=chart_groups([row],{})['model']['services']['monogpt']['a']
        self.assertEqual((point['time'],point['time_lower'],point['time_label']),
                         (32.5,23.1,'23.1–32.5'))

    def test_upper_only_missing_and_failed_times_are_distinct(self):
        self.assertEqual(_observed_time({'status':'success','first_complete_observed_ms':26400}),
                         (26.4,None,'≤26.4'))
        self.assertEqual(_observed_time({'status':'success'}),(None,None,None))
        self.assertEqual(_observed_time({'status':'service_error','first_complete_observed_ms':7100}),
                         (None,None,None))
        self.assertEqual(_observed_time({'status':'success','first_complete_observed_ms':0,
                                        'last_generating_observed_ms':0}),(0,0,'0.0–0.0'))

    def test_all_missing_time_has_explanation_not_fake_zero_to_one_axis(self):
        import importlib.util
        if not importlib.util.find_spec('reportlab'):self.skipTest('reportlab not installed')
        from benchmark.charts import _panel
        drawing=_panel(['a'],{'monogpt':{'a':{'time':None}}},'time','Helvetica')
        labels=[getattr(s,'text','') for s in drawing.contents]
        self.assertTrue(any('시간 측정 미완료' in s for s in labels))
        self.assertNotIn('0.25',labels)
