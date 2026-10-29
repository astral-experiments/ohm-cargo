from pathlib import Path
import gzip,hashlib,json
s=Path(__file__).resolve().parent
for l in (s/'SHA256SUMS').read_text().splitlines():
 d,p=l.split('  ',1);assert hashlib.sha256((s/p).read_bytes()).hexdigest()==d,p
rows=json.load(gzip.open(s/'observations.json.gz'));keys={'on','off','baseline','official-18'};assert rows.keys()==keys
sids=json.loads((s/'subjects.json').read_text());assert sids['on']['cargo']==sids['off']['cargo']=='00d75d89b28ac122fa18d41fbfd054e50fbef0e2a64ccb4786ea146cccc29b20' and sids['baseline']['cargo'].startswith('a9c1b18b') and sids['official-18']['cargo']!=sids['baseline']['cargo']
for case,series in rows.items():
 assert len(series)==9
 def a(n):return next(y for x,y in series.items() if x.startswith(f'{n:02d}-'))
 def ld(n):return [e for e in a(n)['processes'] if e['type']=='linker']
 def rust(n):return [e for e in a(n)['processes'] if e['type']=='rustc' and e['crate']=='reader']
 assert all(x['build_scripts']==0 and x['raw'] for x in series.values()) and a(1)['source']==a(6)['source']!=a(3)['source']
 assert a(1)['value']==a(2)['value']==a(9)['value']==17 and not ld(2)
 assert all(a(n)['value']==29 and ld(n) for n in (4,5)) and all(a(n)['status']==101 and a(n)['native_error'] and ld(n) for n in (7,8))
 assert a(5)['empty_at_start'] and a(8)['empty_at_start']
 for v in series.values():
  for e in v['processes']:
   if e['type']=='linker':assert e['has_choice_flag'] and e['early_ld_search'] is not None and e['early_ld_search']<e['late_ld_search'] and e['exe']==(sids[case]['stock_wild'] if case!='off' else 'e9ceb054c12207970f2726dfc07e9a66b411602748628baf27399f02a9bbb31b')
 if case=='off':assert a(3)['value']==29 and ld(3) and rust(3) and a(6)['status']==101 and ld(6) and rust(6)
 else:assert a(3)['value']==17 and a(3)['elf']==a(1)['elf'] and not ld(3) and not rust(3) and a(6)['status']==0 and a(6)['elf']==a(4)['elf'] and not ld(6) and not rust(6) and 'native_input_env' in a(1)['unused_names']
print('Verified 36 real Cargo commands, three affected default images, GNU defaults-off, constant search order, both fresh target oracles and native 17/29/101 verdicts.')
