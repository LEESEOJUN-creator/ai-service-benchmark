import unittest
from benchmark.validation import check_order_function

GOOD='''def summarize_orders(rows):
    result = {}
    for row in rows:
        category = row['category']
        amount = row['amount']
        if not isinstance(category,str) or not category.strip():
            raise ValueError('category')
        if type(amount) is not int or amount < 0:
            raise ValueError('amount')
        key=category.strip()
        result[key]=result.get(key,0)+amount
    return result
'''

class ValidationTests(unittest.TestCase):
    def test_fixed_function(self):
        self.assertTrue(check_order_function(GOOD)['passed'])
    def test_bool_rejection_is_tested(self):
        bad=GOOD.replace('type(amount) is not int','not isinstance(amount,int)')
        self.assertFalse(check_order_function(bad)['checks']['bool'])
    def test_dangerous_call_rejected(self):
        with self.assertRaises(ValueError):check_order_function("def summarize_orders(rows):\n    return open('secret')")
    def test_import_rejected(self):
        with self.assertRaises(ValueError):check_order_function("def summarize_orders(rows):\n    import os\n    return {}")
    def test_unrelated_top_level_not_executed(self):
        self.assertTrue(check_order_function(GOOD+"\nraise RuntimeError('must not run')")['passed'])

if __name__=='__main__':unittest.main()
