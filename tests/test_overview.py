import unittest
from benchmark.overview import report_groups, coverage_text, summaries, assessment_warnings
from benchmark.charts import chart_groups
from benchmark.costs import normalize_rates


def row(service, case='education-01', score=4, status='success', group='GPT'):
    return {'group':group,'case':{'id':case},
            'request':{'service':service,'model':group,'reasoning':'medium','request_id':service+'-'+case,
                       'candidate_id':'gpt','comparison_tier':'ui_matched'},
            'result':{'status':status,'cost':10,'cost_unit':'credits','first_complete_observed_ms':2000},
            'assessment':{'criteria':[{'criterion':str(i),'score':score,'observation':'구체적인 관찰',
                                      'judgement':'요구 조건을 확인함','evidence_ref':'답변 1행'} for i in range(5)]}}


class OverviewTests(unittest.TestCase):
    def doc(self):
        return {'cases':[{'id':'education-01'},{'id':'file-generation-01'}],
                'report_scope':{'origin':'init_snapshot','models':[
                    {'id':'gpt','requested_name':'GPT','report_label':'GPT','enabled':True,
                     'services':['monogpt','timely']},
                    {'id':'claude','requested_name':'Claude','enabled':True,'services':['monogpt','timely']}]}}

    def test_unmeasured_model_does_not_disappear(self):
        groups=report_groups([row('monogpt'),row('timely')],self.doc())
        self.assertEqual(len(groups),2)
        self.assertIn('미실측',coverage_text(groups[1]))
        self.assertIn('부분 실측',coverage_text(groups[0]))

    def test_summary_uses_common_questions_and_excludes_file_tools(self):
        rows=[row('monogpt'),row('timely'),row('monogpt','file-generation-01'),row('timely','file-generation-01')]
        group=report_groups(rows,self.doc())[0]
        data=summaries(group,normalize_rates({'monogpt':1,'timely':2}))
        self.assertEqual([d['n'] for d in data],[1,1])
        self.assertEqual([d['cost'] for d in data],['10원','20원'])
        rows[1]['result']['model_match']=False
        self.assertEqual(summaries(group,normalize_rates({'monogpt':1,'timely':2}))[0]['n'],0)

    def test_no_common_rows_never_looks_free(self):
        group=report_groups([row('monogpt')],self.doc())[0]
        self.assertEqual(summaries(group,normalize_rates({'monogpt':1}))[0]['cost'],'미확인')

    def test_vague_assessment_warns_without_blocking_output(self):
        item=row('monogpt')
        item['assessment']['criteria'][0]['judgement']='부분 충족'
        self.assertTrue(any('보완 필요' in s for s in assessment_warnings([item])))

    def test_explicit_candidate_id_wins_over_display_name(self):
        item=row('monogpt',group='Different UI Label')
        groups=report_groups([item],self.doc())
        self.assertEqual(len(groups),2)
        self.assertEqual(len(groups[0]['rows']),1)
