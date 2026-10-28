"""Replay all scheduler edge removals and literal queue operations independently of Cargo."""
from pathlib import Path
from collections import Counter
import json,gzip,hashlib
d=Path(__file__).resolve().parent
def gz(path):return json.loads(gzip.decompress(path.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=d/'SHA256SUMS'
if manifest.exists():
    for row in manifest.read_text().splitlines():
        digest,file=row.split('  ',1);assert sha(d/file)==digest
allstats=[]
for idx in [1,2,3]:
    stem='instrumented'+str(idx);v=gz(d/(stem+'.json.gz'));record=gz(d/(stem+'-links.json.gz'));reg={};deps={};ready={};deq={};pending=[];served={};actual={};u_jobs={};sources=json.loads((d/'raw.json').read_bytes())[stem]
    assert sources==v['source_sha256'] and v['cargo']['units']==619 and v['cargo']['fresh']==563
    assert len(v['events']) and all(t2>=t1 for (t1,_),(t2,_)in zip(v['events'],v['events'][1:]))
    for now,e in v['events']:
        op=e[0]
        if op=='register':
            _,i,pkg,name,mode,kind,dirty,edges,outputs=e;assert i not in reg;reg[i]=(pkg,name,mode,kind,dirty,outputs);deps[i]=set(map(tuple,edges));assert len(edges)==len(deps[i])
        if op=='initial':assert now==0;ready={i:0 for i,de in deps.items()if not de}
        if op=='edge':
            _,i,a,claimed=e;new=[]
            for j,de in deps.items():
                if (i,a) in de:
                    de.remove((i,a))
                    if not de:assert j not in ready;ready[j]=now;new.append(j)
            assert set(new)==set(claimed)
        if op=='dequeue':
            _,i,p,at,active,cap=e;assert i in ready and i not in deq;deq[i]=(now,p);assert at==sum(q<=p for j,q in pending);pending.insert(at,(i,p))
        if op=='service':
            _,i,p,active,cap,n,job=e;assert i not in served and active<cap and pending.pop()==(i,p) and n==len(pending)
            served[i]=(now,[j for j,pr in pending if pr==p],job);assert job not in u_jobs;u_jobs[job]=i
        if op=='process':_,i,j=e;assert u_jobs[j]==i
    assert len(reg)==len(deq)==len(ready)==len(served)==689 and not pending and not any(deps.values())
    assert Counter(u[2] for u in reg.values())=={'Build':535,'Test':84,'RunCustomBuild':51,'Doctest':19}
    edges=sum(len(e[7])for _,e in v['events']if e[0]=='register');assert edges==29419
    links=record['links'];assert len(links)==50
    if v['execs'] is not None:
        ex=v['execs'];assert Counter(x['role']for x in ex)=={'cargo':1,'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50}
        assert all(x['status']==0 and len(x['argv_sha256'])==64 for x in ex)
        wild={x['output']:x for x in ex if x['role']=='stock-wild'};assert len(wild)==50 and set(wild)=={x['target']for x in links}
        for x in links:
            z=wild[x['target']];assert z['argv_sha256']==x['raw_wild_argv_sha256'] and z['start_rel_ns']>served[x['unit']][0] and (z['exit_rel_ns']-z['start_rel_ns'])/1e6==x['wild_ms']
    else:assert idx==2
    eligible={x['unit']:x for x in links};edges=0;choices=0
    for u,observed in eligible.items():
        pkg,name,mode,kind,dirty,outs=reg[u];ts,waiting,job=served[u];out,=[a for a in outs if a[0]==observed['target'] and a[1]=='Normal' and a[2]>0 and not a[3]and not a[4]]
        assert out[2]==observed['old_len'] and observed['pkg']==pkg and observed['name']==name and dirty and mode=='Test' and deq[u][1]==200
        assert observed['ready_service_ms']==(ts-ready[u])/1e6
        bigger=[eligible[j]['target'] for j in waiting if j in eligible and eligible[j]['old_len']>out[2]];assert bigger==observed['larger_available']
        edges+=len(bigger);choices+=bool(bigger)
    assert (choices,edges)==[(46,511),(47,458),(46,541)][idx-1] and choices==record['selects_with_larger_same_priority_native_alternative']
    allstats.append([choices,edges])
print('Verified 3 x 689 units, 29,419 dependency edges per run, 2 x 50 stock native links and the untraced native-order control.',allstats)
