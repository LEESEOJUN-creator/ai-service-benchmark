import unittest
from benchmark.charts import chart_groups
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
