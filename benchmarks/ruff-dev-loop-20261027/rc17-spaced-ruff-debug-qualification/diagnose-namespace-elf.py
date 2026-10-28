"""Inspect the unscored rejection and independently check both exact artifact trees."""
from pathlib import Path
import json
import subprocess
import sys

here = Path(__file__).resolve().parent
worker = r"""
from pathlib import Path
import fcntl, hashlib, json, os, socket, sys, types
assert socket.gethostname() == 'charlie-ohm-cargo5-build-1025'
p=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
k=p/'rc17-spaced-wall-protocol-v2'
out=p/'rc17-spaced-wall-v2'
assert (k/'outer.exit').read_text()=='1' and 'b.roster==c.roster' in (out/'failure.txt').read_text()
assert not list(out.rglob('clock.json')) and not list(out.glob('ledger-*.json')) and not (out/'priming').exists()
assert not (p/'rc17-spaced-wall-v3').exists()
sys.path.insert(0,str(k))
import score
N=types.ModuleType('namespace_paths');source=sys.stdin.buffer.read()
payload=json.loads(source);source=payload['paths'].encode();exec(compile(source,'namespace_paths.py','exec'),N.__dict__);D=types.ModuleType('explain_elf');exec(compile(payload['diagnose'],'explain_elf.py','exec'),D.__dict__)
assert N.selftest()
os.sched_setaffinity(0,{22,23})
grant=score.read(k/'grant.json')
record={'prior_exit':1,'prior_stderr':(k/'outer.stderr').read_text(),'prior_failure':(out/'failure.txt').read_text(),
        'prior_clock_files':0,'prior_ledger_files':0,'prior_grant':score.sha(k/'grant.json'),
        'helper_sha256':hashlib.sha256(source).hexdigest(),'native':{}}
with (p/'matched-qualify.lock').open('a') as guard:
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for w in N.LAYOUT:
        arms={a:score.Arm(w,a,grant['arms'][a]) for a in 'BC'}
        b,c=arms.values()
        assert b.diagnostics==c.diagnostics and b.report['oracle']==c.report['oracle']
        assert b.roster!=c.roster and N.units(w,'B',b.roster)==N.units(w,'C',c.roster)
        assert sorted(N.key(w,'B',n) for n in b.report['executables'])==sorted(N.key(w,'C',n) for n in c.report['executables'])
        l,r=[N.products(w,a,arm.products) for a,arm in arms.items()]
        assert l.keys()==r.keys()
        mismatches={}
        for n,x in l.items():
            y=r[n];bh=b.products[x];ch=c.products[y]
            if bh!=ch:
                files=(b.t/'state/target'/x,c.t/'state/target'/y)
                assert [score.sha(f) for f in files]==[bh,ch]
                left,right=map(score.elf.normalize,files)
                mismatches[n]=dict(raw=[bh,ch],original=[left,right],strict_elf_pass=left['normalized']==right['normalized'] and left['bytes']==right['bytes'],difference=D.explain(files,w,N.LAYOUT))
        record['native'][w]={'units':len(b.roster),'files':len(l),'exact':len(l)-len(mismatches),
            'diagnostics':len(b.diagnostics),'runnable':len(b.report['executables']),
            'harness':b.report['oracle'],'differences':mismatches}
print(json.dumps(record))
"""
assert len(sys.argv)==1
cmd = ['dbox','ssh','charlie-ohm-cargo5-build-1025','--no-tmux','--','/usr/bin/python3','-B','-c',worker]
with (here/'native-elf-diagnostic.stderr').open('wb') as log:
    result=subprocess.run(cmd,input=json.dumps({'paths':(here/'namespace_paths.py').read_text(),'diagnose':(here/'explain-native-difference.py').read_text()}).encode(),stdout=subprocess.PIPE,stderr=log)
assert not result.returncode, (here/'native-elf-diagnostic.stderr').read_text()[-1250:]
receipt=json.loads(result.stdout)
(here/'native-elf-diagnostic.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
print({w:(v['units'],v['files'],v['exact']) for w,v in receipt['native'].items()})
