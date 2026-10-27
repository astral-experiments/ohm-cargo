"""One-bit marker corruption repro, with both downstream programs and a clean oracle."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paired import Study, getargs, log_json
s=Study(getargs()); s.references()
arm=s.init('candidate')
r=s.run(arm,'C','pending-receipts',trace=True)
for key,value in r['readers'].items():
    f=arm/key; b=f.read_bytes(); pos=b.rindex(b'OBS1')+8; assert b[pos]==0
    f.write_bytes(b[:pos]+b'\x01'+b[pos+1:])
s.edit(arm,True)
r=s.run(arm,'C','corrupted-early-edit',trace=True)
passed=all(e==s.gold[True]['native_products'][n] for n,e in r['native_products'].items())
log_json(s.logs/'result.json',{'matches_empty':passed,'warm':r,'gold':s.gold[True]})
print('matches_empty',passed,flush=True)
