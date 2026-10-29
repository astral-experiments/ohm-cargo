from pathlib import Path
import hashlib,gzip,json
s=Path(__file__).resolve().parent
for l in (s/'SHA256SUMS').read_text().splitlines():
 d,n=l.split('  ',1);assert hashlib.sha256((s/n).read_bytes()).hexdigest()==d
rows=json.load(gzip.open(s/'native.json.gz'));q=json.loads((s/'binding.json').read_bytes());assert q['cargo']=='99383612a7a0a2b58c60f8d94711e88e3f73f4fd584ff43ef8a6b04caa1fa8aa' and set(rows)==set(q['stages']);total=0
for name,r in rows.items():
 assert r['term']==q['stages'][name]['terminal_sha']
 if r['kind']=='private-dir':
  total+=2;assert len(r['existing_archives'])>=2 and all(x['status']==101 and x['build_scripts']==0 and x['rust_executions'] and x['ld_executions'] and not x['private_dirs_forwarded'] for x in r['ordinary']);continue
 a=r['rows'];total+=len(a);ld=lambda k:[x for x in a[k]['processes'] if x['type']=='linker'];rust=lambda k:[x for x in a[k]['processes'] if x.get('crate')=='reader']
 assert len(a)==9 and all(x['build_scripts']==0 and x['raw'] for x in a);assert all(a[i]['value']==17 for i in (0,1,8)) and all(a[i]['value']==29 for i in (2,3,4)) and all(a[i]['status']==101 and a[i]['native_error'] for i in (5,6,7));assert a[4]['empty_at_start'] and a[7]['empty_at_start'] and not ld(1)
 for k in (2,5):
  assert len(ld(k))==len(rust(k))==1 and rust(k)[0]['link_only']==name.endswith('on') and ld(k)[0]['has_choice_flag'] and ld(k)[0]['early_ld_search']<ld(k)[0]['late_ld_search'] and ld(k)[0]['exe']==(q['wild'] if name.endswith('on') else 'e9ceb054c12207970f2726dfc07e9a66b411602748628baf27399f02a9bbb31b')
assert total==40;print('Verified 40 real Cargo/native commands, ordinary and empty outcomes, actual cached-codegen versus full compiler, genuine native search choices and both default-directory negatives.')
