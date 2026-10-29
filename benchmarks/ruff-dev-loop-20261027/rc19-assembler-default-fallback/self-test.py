"""Try mutually inconsistent file, native output, compiler mode, origin and Cargo receipt claims."""
import base64,copy,json,runpy
from pathlib import Path
root=Path(__file__).resolve().parent
v=runpy.run_path(str(root/'verify.py')); db=v['unzip'](root/'ledgers.json.gz');blobs={h:base64.b64decode(b) for h,b in v['unzip'](root/'streams.json.gz').items()}
case=db['integration']['integration-used'];s=v['j'](root/'subjects.json');img=s['development']['candidate']|{'wild':s['official']['19']['images']['wild']}
def edited(r):r.update(native=17)
def compiler(r):next(p for p in r['processes'] if p.get('unit')=='reader')['link_only']=True
def absent(r):r['asset_opens'].clear()
def ancestry(r):r['asset_opens'][0]['nearest_compiler']='assembler_reader'
def typed(r):r['typed'][-1][1]=True
def drop_input(r):r['asset']=None
def pretend_success(r):r['status']=0
def stale_missing(r):r['asset_opens'][0]['missing']=False
for phase,mutate in [('03-edit-and-new-asset',f) for f in (edited,compiler,absent,ancestry,typed,drop_input)]+[('07-source-restore-missing-asset',f) for f in (pretend_success,stale_missing)]:
    item=case['phases'][phase];data=json.loads(blobs[item['result'][2]]);v['check_phase'](phase[:2],False,True,data,item['files'],item['lines'],blobs,img)
    mutate(data)
    try:v['check_phase'](phase[:2],False,True,data,item['files'],item['lines'],blobs,img)
    except AssertionError:pass
    else:raise RuntimeError('accepted mutation '+mutate.__name__)
print('rejected 8 changed-value, missing-input, compiler and evidence mutations')
