"""Verify all original timed rows and outside-timing source/roster/list/ELF/physical-process outcomes."""
from pathlib import Path
from collections import Counter
import csv,hashlib,itertools,json,subprocess,sys
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda n:json.loads((root/n).read_bytes())
def verify():
 if (root/'SHA256SUMS').is_file():
  for l in (root/'SHA256SUMS').read_text().splitlines():
   h,n=l.split('  ',1);assert h==sha(root/n),n
 plan=load('plan.json');assert sha(root/'plan.json')=='6dfd1b505f0ef72e101cea247d5bb669bec3f1eb6ef8058c685caabca9e38841'
 result=load('complete.json');assert result['plan']==sha(root/'plan.json') and result['dirty_csv']==sha(root/'dirty.csv') and result['fresh_csv']==sha(root/'fresh.csv') and result['commands_timed']==64
 out=load('commands.json');new=load('supplemental-stock.json');allowed=load('preflight-allowed.json');actual={k:list(csv.DictReader((root/(k+'.csv')).open())) for k in ('dirty','fresh')}
 assert all(len(rows)==32 for rows in actual.values())
 for k,rows in actual.items():
  for r in rows:
   ed=r['endpoint'];arm=r['arm'];i=int(r['pair']);schedule=plan['schedule'][ed][i-1];assert schedule['order'][int(r['slot'])-1]==arm and r['direction']==schedule['direction']
   q=out[ed][arm][k+f'-pair-{i:02}'];assert int(r['elapsed_ns'])==q['elapsed_ns'] and q['elapsed_ns']>0 and q['exit']==0 and not q['traced'] and q['command']==plan['commands']
   assert q['binary']['cargo']==plan['subjects'][arm]['pgo'] and q['binary']['rustc']==plan['rustc_driver_sha256'] and q['binary']['wild']==plan['wild_sha256']
 for v in new.values():
  x=v['certificate'];keys=allowed[x['ed']][x['rev']]['elfs'];keys[x['path']]=sorted(set(keys[x['path']])|set(x['stock_full']))
 for ed in plan['endpoint_order']:
  for label,a in out[ed]['A'].items():
   c=out[ed]['C'][label]
   assert (a['units'],a['executables'],a['elf_count'])==(619,102,110) and all(c[k]==a[k] for k in ['units','executables','elf_count','dirty','messages','roster','kind','traced','source'])
   if a['kind']=='fresh' or label.endswith('fresh'):
    assert not a['dirty']
   else:
    assert a['listing']==c['listing']==dict.fromkeys(['ruff_wasm','ty_wasm'],'0 tests, 0 benchmarks')
    assert a['cli']==c['cli'] and a['caller']==c['caller'] and len(a['elfs'])==len(c['elfs'])==110
    bounds=allowed[ed][a['source']]['elfs']
    assert a['elfs'].keys()==c['elfs'].keys()==bounds.keys()
    for k in bounds:assert a['elfs'][k] in bounds[k] and c['elfs'][k] in bounds[k],(ed,label,k)

   if a['traced']:
    xa,xc=a['successful_processes'],c['successful_processes'];assert Counter(tuple(x[1:]) for x in xa['native_links'])==Counter(tuple(x[1:]) for x in xc['native_links'])
    assert Counter(tuple(x[1:]) for x in xa['rustc'] if x[1]!='api')==Counter(tuple(x[1:]) for x in xc['rustc'] if x[1]!='api')
    if not label.endswith('fresh'):
     n=len(plan['edits'][ed]['expected_cached_jobs'])
     assert sum(x[1:3]==['api','full'] for x in xa['rustc'])==n and sum(x[1:3]==['api','link-only'] for x in xc['rustc'])==n and not xa['native_probes'] and not xc['native_probes']
    else:assert not xa['rustc'] and not xc['rustc'] and not xa['native_links'] and not xc['native_links']
 for k,g in new.items():
  c=g['certificate'];unchanged=c['masked'];assert len(g['physical_stock_full_commands'])>=2
  for digest,o in g['physical_stock_full_commands'].items():
   assert o['elf']['raw']==digest and o['elf']['content_with_two_wild_fields_masked']==unchanged and o['state']==c['rev']
   assert len(o['stock_full_rustc'])==1 and o['stock_full_rustc'][0][2]=='full' and len(o['stock_wild'])==1 and o['stock_wild'][0][2:]==[True,False]
 for kind in actual:
  computed=json.loads(subprocess.check_output([sys.executable,'-B',root/'analyze.py',root/(kind+'.csv')],cwd=root))
  assert computed==load(kind+'-analysis.json')
 print('Exactly 32 edited and 32 immediate no-op timings, registered slots/sources, 110 native products, traced before/after physical modes and independent raw stock witnesses verified.')
if __name__=='__main__':verify()
