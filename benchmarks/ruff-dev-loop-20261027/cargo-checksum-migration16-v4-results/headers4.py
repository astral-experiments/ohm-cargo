"""Decode true crate headers from every retained changed workspace .rmeta using the unchanged stock rustc."""
from pathlib import Path
import collections,hashlib,json,re,runpy,subprocess,sys
here=Path(__file__).resolve().parent;g=runpy.run_path(here/'runner.py');D,O,SDK,translate,h,save,env=[g[k]for k in('D','O','SDK','translate','h','save','environment')]
load=lambda p:json.loads(p.read_text())
def hdr(p):
    q=subprocess.run(['rustc','+ohm','--sysroot',str(SDK),'-Zls=root',str(p)],env=env(),capture_output=True,timeout=30)
    s=q.stdout.decode(errors='replace');m=re.search(r'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',s,re.M)
    return {'status':q.returncode,'private':m[1]if m else None,'stable_id':m[2]if m else None,'public':m[3]if m else None,'stdout_sha':hashlib.sha256(q.stdout).hexdigest(),'stderr_sha':hashlib.sha256(q.stderr).hexdigest(),'bytes':p.stat().st_size,'sha':h(p)}
allout={}
for mode in ('check','build','test'):
    base=O/mode/'final-v4/first';pairs=load(base/'products-changed-vs-seed.json');old=D/'states'/mode/'stock-repeat';new=D/'states'/mode/'final-v4';groups=collections.Counter();results={};names=collections.Counter()
    for name,ds in sorted(pairs.items()):
        n=Path(name);a=ds.get('before');b=ds.get('after')
        if not a or not b:groups['added-or-missing']+=1;continue
        if n.suffix!='.rmeta':names[n.suffix or '<no suffix>']+=1;continue
        x=hdr(translate(n,old));y=hdr(translate(n,new));assert [x['sha'],y['sha']]==[a['sha256'],b['sha256']]
        k='undecoded' if any(not u['private'] for u in [x,y])else ('same-private-public-id' if all(x[n]==y[n]for n in ['public','private','stable_id']) else ('same-public-id-different-private' if x['public']==y['public'] and x['stable_id']==y['stable_id']else 'different-public-or-id'))
        groups[k]+=1;results[str(n.relative_to(D))]={'original':x,'retrained':y,'class':k}
    allout[mode]={'header-classification':dict(groups),'other_changed_file_types':dict(names),'pairs':results};print(mode,dict(groups),dict(names),flush=True)
save(O/'changed-rmeta-headers-v4.json',allout)
