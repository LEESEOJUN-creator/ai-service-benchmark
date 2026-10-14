"""Narrow checks for the fixed code and generated-XLSX cases.

Not a general sandbox. Review code before use; reject unsupported syntax rather
than widening the allowlist to execute arbitrary service output.
"""
import ast
import copy
import re
import zipfile
import xml.etree.ElementTree as ET


def check_order_function(answer):
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", answer, re.S)
    source = blocks[0] if blocks else answer
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "summarize_orders"]
    if len(functions) != 1:
        raise ValueError("Exactly one summarize_orders function required")
    fn = functions[0]
    allowed = {ast.FunctionDef,ast.arguments,ast.arg,ast.Assign,ast.For,ast.Name,ast.Load,ast.Store,
               ast.Dict,ast.Subscript,ast.Constant,ast.If,ast.UnaryOp,ast.Not,ast.BoolOp,ast.Or,ast.And,
               ast.Call,ast.Attribute,ast.Compare,ast.IsNot,ast.Is,ast.Lt,ast.Gt,ast.Eq,ast.NotEq,
               ast.Raise,ast.Return,ast.BinOp,ast.Add,ast.Try,ast.ExceptHandler,ast.Tuple,ast.Pass}
    if fn.decorator_list or fn.args.defaults or fn.args.kw_defaults:
        raise ValueError("Decorators/default expressions are not allowed")
    for node in ast.walk(fn):
        if type(node) not in allowed:
            raise ValueError("Unsupported syntax: " + type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise ValueError("Dunder access blocked")
        if isinstance(node, ast.Attribute) and node.attr not in {'get','strip'}:
            raise ValueError("Unsupported attribute")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in {'isinstance','type','ValueError'}:
                raise ValueError("Unsupported function call")
            if not isinstance(node.func, (ast.Name,ast.Attribute)):
                raise ValueError("Indirect call blocked")
    module = ast.Module(body=[fn],type_ignores=[])
    namespace = {'__builtins__':{'isinstance':isinstance,'type':type,'str':str,'int':int,'bool':bool,
                                'ValueError':ValueError,'KeyError':KeyError,'TypeError':TypeError}}
    exec(compile(module,'<reviewed-benchmark-function>','exec'),namespace)
    f=namespace['summarize_orders']
    rows=[{'category':' food ','amount':10},{'category':'food','amount':5},{'category':'book','amount':0}]
    prior=copy.deepcopy(rows)
    checks={'sum_trim_zero':f(rows)=={'food':15,'book':0},'input_unchanged':rows==prior,'empty':f([])=={}}
    for key,value in [('bool',True),('negative',-1),('float',1.5),('string_amount','1')]:
        try:f([{'category':'a','amount':value}]);checks[key]=False
        except ValueError:checks[key]=True
    for key,value in [('empty_category',' \t '),('invalid_category',123)]:
        try:f([{'category':value,'amount':1}]);checks[key]=False
        except ValueError:checks[key]=True
    return {'checks':checks,'passed':all(checks.values()),'scope':'fixed function only; provided test code not executed'}


def check_sales_xlsx(path):
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 10_000_000:
            raise ValueError('Unexpected archive size')
        if any('vbaProject' in n or 'externalLinks/' in n for n in z.namelist()):
            raise ValueError('Unexpected active/external content')
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        sheets=wb.find('m:sheets',ns)
        sheet=next((s for s in sheets if s.attrib['name']=='매출분석'),None)
        if sheet is None: return {'passed':False,'reason':'missing required sheet'}
        rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target=next(r.attrib['Target'] for r in rels if r.attrib['Id']==rid)
        target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        cells={}
        for c in ET.fromstring(z.read(target)).findall('.//m:c',ns):
            v=c.find('m:v',ns);f=c.find('m:f',ns);kind=c.get('t','n')
            value=v.text if v is not None else None
            if kind=='s':value=shared[int(value)]
            if kind=='inlineStr':value=''.join(c.find('m:is',ns).itertext())
            cells[c.attrib['r']]={'value':value,'type':kind,'formula':f.text if f is not None else None}
        checks={}
        for col,value in zip('ABCD',['월','매출','비용','이익']):checks['header_'+col]=cells.get(col+'1',{}).get('value')==value
        for row,value in [(2,'1월'),(3,'2월'),(4,'3월'),(5,'합계')]:
            checks[f'A{row}_label']=cells.get(f'A{row}',{}).get('value')==value
        for row,revenue,cost in [(2,1200000,750000),(3,980000,630000),(4,1450000,910000)]:
            for col,value in [('B',revenue),('C',cost)]:
                cell=cells.get(f'{col}{row}',{});checks[f'{col}{row}_numeric']=cell.get('type')=='n' and float(cell.get('value') or 'nan')==value
            checks[f'D{row}_formula']=(cells.get(f'D{row}',{}).get('formula') or '').replace('$','').replace(' ','').upper()==f'B{row}-C{row}'
        for col in 'BCD':checks[col+'5_sum']=(cells.get(col+'5',{}).get('formula') or '').replace('$','').replace(' ','').upper()==f'SUM({col}2:{col}4)'
        for cell,expected in [('D2',450000),('D3',350000),('D4',540000),('B5',3630000),('C5',2290000),('D5',1340000)]:
            value=cells.get(cell,{}).get('value');checks[cell+'_cached']=None if value is None else float(value)==expected
        return {'passed':all(v for v in checks.values() if v is not None),'checks':checks,'cells':cells,
                'note':'Missing cached values require independent recalculation; formulas and numeric inputs checked separately'}
