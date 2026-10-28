from pathlib import Path
import hashlib,json,tarfile
p=Path(__file__).resolve().parent
for line in (p/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ');assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
def j(t,p):return json.load(t.extractfile(p))
with tarfile.open(p/'whole-cargo.tgz') as t:
 for arm,driver,old,expected in [('shipped','c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4',True,(0,0,101)),('prototype','38a4e039de5d1ee3a653dc7f79058b070c1b85b8ab91a7783737870381418584',False,(0,101,101))]:
  pref='lossy-true-cargo-run3/check-'+arm+'/';i=j(t,pref+'identity.json');assert i['driver']==driver
  data=j(t,pref+'result.json')
  for mode,code in zip(['ab','ba','only-valid'],expected):
   rows=data[mode];changed=rows['changed'];ref=rows['empty'];assert changed['exit']==code and ref['exit']==101 and any(d['code']['code']=='E0308' for d in ref['diagnostics'])
   if code==0:
    assert changed['fresh'] and changed['complete']==1 and len(changed['replacement_checksums'])==1
    encoded=t.extractfile(pref+mode+'/records/changed/fingerprint').read();assert encoded[5]==(2 if old else 3) and encoded[-41:-37]==b'OBS1' and encoded[-33]==1
    assert rows['unchanged']['real']!=changed['real'] and rows['unchanged']['shadow']==changed['shadow']
    argv=t.extractfile(pref+mode+'/records/changed/exec').read();assert b'"--crate-name", "hold_direct"' not in argv
   else:assert changed['diagnostics']==ref['diagnostics']
 with t.extractfile('lossy-true-cargo/shipped/ab/records/first/stderr') as s:assert b'CompiledModules>::serialize_rlink' in s.read()
for label,ns in [('lossy-external-stock16-sdk',(1,1)),('lossy-external-raw-rc17-final-fixed',(1,0)),('lossy-external-reversed-rc17',(0,1))]:
 with tarfile.open(p/'direct-rustc.tgz') as t:
  d=j(t,label+'/result.json');assert d['absolute-invalid']['returncode']==1 and d['relative']['returncode']==101
  for n,ex in zip(('ab','ba'),ns):
   x=d[n];assert x['returncode']==0 and x['native']=='17 29' and x['raw_input_sha']!=x['valid_input_sha'] and len(x['matching_checksums'])==ex
print('Verified 30 ordinary Cargo checks, six direct linked programs, native build boundaries, and three stale Cargo successes.')
