"""Validate reached integration-test compilers, actual linkers and executables for both workflows."""
from pathlib import Path
import ast
import collections
import hashlib
import importlib.util
import json
import mmap
import os
import re
import shutil
import socket
import struct
import subprocess
import traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
base=p/'run-ruff-v1/run.py'
assert hashlib.sha256(base.read_bytes()).hexdigest()=='8c45186586ccad4906a2e6bf1fd1e6248b4da2cdb5a5b8266aa348f55be5879e'
spec=importlib.util.spec_from_file_location('fixture',base);q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
o=p/'matching-scheduler-native-v1'
roles=dict(A='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568',
           B='eea47e1d637a96d0d91dee825cf6a029d5123396ea1af1389aad187555fe2af3',
           C='46d8d787ab0e8f346f9fc5186e6a9bbad6ccd8c822c193deed51e8c9e9452afd')
executables={'A':q.sdk/'bin/cargo',**{arm:p/'release-pair-v1'/('cargo-'+tag) for arm,tag in [('B','parent'),('C','candidate')]}}
special='crates/ty_server/tests/e2e/main.rs'
def canonical(n):
    f=Path(n);return str(f.relative_to(q.src)) if f.is_absolute() and f.is_relative_to(q.src) else n
def load(f):return json.loads(f.read_bytes())
def audit(out):
    done={};calls=[];traces={}
    for f in sorted((out/'trace').glob('exec.*')):
        pid=int(f.suffix[1:]);b=f.read_bytes();pending=None
        traces[str(pid)]=[hashlib.sha256(b).hexdigest(),len(b)]
        for row in b.splitlines():
            ts,_,line=row.partition(b' ');time=int(ts.split(b'.')[0])*10**9+int(ts.split(b'.')[1].ljust(9,b'0'))
            if fin:=re.match(rb'^\+\+\+ exited with (\d+) \+\+\+$',line):done[pid]=[time,int(fin[1])]
            if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
                assert pending is None;pending=(time,line.removesuffix(b'<unfinished ...>'));continue
            if m:=re.match(rb'^<\.\.\. (execve(?:at)?) resumed>(.*)$',line):
                assert pending;time,at=pending;line=at+m[2];pending=None
            if not line.startswith((b'execve(',b'execveat(')) or not re.search(rb'\)\s+= 0$',line):continue
            m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m,(pid,line[:110])
            image=ast.literal_eval(m[1].decode());args=ast.literal_eval(m[2].decode());assert isinstance(args,list) and all(isinstance(v,str) for v in args)
            calls.append(dict(pid=pid,start=time,image=image,argv=args,original_line=hashlib.sha256(row).hexdigest()))
        assert not pending
    product=load(out/'product.json')
    assert not set(product['executables']).intersection(z['image'] for z in calls)
    groups=collections.defaultdict(list);links=collections.defaultdict(list);native=collections.Counter()
    for rec in calls:
        pid=rec['pid'];args=rec['argv'];img=Path(rec['image']);name=img.name
        if name in ('gcc','cc','collect2','ld.bfd'):native[name]+=1
        if name=='rustc' and '--crate-name' in args and '--out-dir' in args and '--print=file-names' not in args:
            crate=args[args.index('--crate-name')+1]
            if crate in ('___','__'):continue
            key=q.digest([rec['image'],args])
            source=next((canonical(v) for v in args if v.endswith('.rs') and not v.startswith('-')),None)
            assert source or 'link-only' in args or '-Zlink-only' in args or (crate.startswith('autocfg_') and '-' in args)
            groups[key].append(dict(pid=pid,start=rec['start'],end=done.get(pid),source=source,test='--test' in args,crate=crate,
                kind='link' if ('link-only' in args or '-Zlink-only' in args) else 'full',signature=key,
                ty_extern=[a for a in args if a.startswith('ty_server=') and a.endswith('.rlib')]))
        if name=='ld.bfd' and 'wild-ld' in img.parts:
            assert '-o' in args and done.get(pid)[1]==0
            links[args[args.index('-o')+1]].append(dict(pid=pid,start=rec['start'],end=done[pid],
                argv=q.digest(args),ty_rlibs=[v for v in args if Path(v).name.startswith('libty_server-') and v.endswith('.rlib')]))
    witnesses=[v for group in groups.values() for v in group];assert all(z['end'] is not None for z in witnesses)
    bysrc=collections.defaultdict(list)
    for v in witnesses:
        if v['test'] and v['source'] and '/tests/' in v['source']:bysrc[v['source']].append(v)
    for vs in bysrc.values():vs.sort(key=lambda z:z['start'])
    result=dict(rustc=collections.Counter(v['kind'] for v in witnesses),total=len(witnesses),distinct=len(groups),
        repeated={k:g for k,g in groups.items() if len(g)>1},native=native,actual_wild=sum(map(len,links.values())),
        distinct_wild=len(links),target_link_groups=links,integration=bysrc,typed_compilers=witnesses,
        policy=[s.split('ohm_early_tests: ',1)[1] for s in (out/'stderr').read_text(errors='replace').splitlines() if 'ohm_early_tests: ' in s])
    q.put(out/'successful-executables.json',calls);q.put(out/'original-trace-index.json',traces);q.put(out/'physical.json',result)
    return result

def normalize(path):
    with path.open('rb') as s,mmap.mmap(s.fileno(),0,access=mmap.ACCESS_READ) as b:
        assert b[:6]==b'\x7fELF\x02\x01'
        sh=struct.unpack_from('<Q',b,40)[0];size,num,idx=struct.unpack_from('<HHH',b,58);assert size==64 and num>idx
        entries=[struct.unpack_from('<IIQQQQIIQQ',b,sh+size*i) for i in range(num)];strings=entries[idx][4]
        sections={b[strings+k[0]:b.index(0,strings+k[0])].decode():(i,k) for i,k in enumerate(entries)}
        i,ro=sections['.rodata'];_,note=sections['.note.gnu.build-id'];off=note[4];n,ds,kind=struct.unpack_from('<III',b,off)
        assert note[1]==7 and n==4 and kind==3 and b[off+12:off+16]==b'GNU\x00' and 8<=ds<=64
        assert ro[9] in (0,1,2,4,8,16,32,64,128,256)
        hi=hashlib.sha256();lo=0
        for start,length in sorted([(off+16,ds),(sh+i*size+56,8)]):
            assert start>=lo and start+length<=len(b)
            hi.update(memoryview(b)[lo:start]);hi.update(bytes(length));lo=start+length
        hi.update(memoryview(b)[lo:])
        return dict(bytes=len(b),normalized=hi.hexdigest(),build_id=b[off+16:off+16+ds].hex(),rodata_entsize=ro[9])

def compare(a,b,t1,t2):
    assert a['roster']==b['roster'] and a['diagnostics']==b['diagnostics'] and a['executables']==b['executables']
    assert a['native'].keys()==b['native'].keys() and len(a['native'])==110
    changed={}
    for n,h in a['native'].items():
        if h==b['native'][n]:continue
        x,y=normalize(q.printed(t1,n)),normalize(q.printed(t2,n));assert x['normalized']==y['normalized'] and x['bytes']==y['bytes'],n
        assert x['rodata_entsize']==y['rodata_entsize'] or min(x['rodata_entsize'],y['rodata_entsize'])==0
        changed[n]=[x,y]
    return dict(exact=110-len(changed),allowed=changed)

def list_test(t,exe,product,out,overlay):
    args,env=q.opts(t,exe,overlay);args+=['--chdir',str(q.src),'--',product['e2e'][0],'--list','--format','terse']
    r=subprocess.run(args,env=env,capture_output=True,stdin=subprocess.DEVNULL)
    assert r.returncode==0 and b'inlay_hints::default_inlay_hints: test' in r.stdout
    (out/'test-list.stdout').write_bytes(r.stdout);(out/'test-list.stderr').write_bytes(r.stderr)
    return dict(exit=r.returncode,stdout=hashlib.sha256(r.stdout).hexdigest(),stderr=hashlib.sha256(r.stderr).hexdigest())

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024' and (p/'run-ruff-v1/exit').read_text()=='0'
    assert (p/'release-pair-v1/complete.json').is_file() and q.sha(p/'release-pair-v1/cargo-parent-repeat')==roles['B']
    assert {k:q.sha(v) for k,v in executables.items()}==roles and q.sha(p/'inputs/subject.json')==q.binding
    os.sched_setaffinity(0,set(range(16)));q.source_gate();assert not o.exists();o.mkdir(mode=0o700)
    source=q.lab/'official-before-selection';historical=p/'inputs/ruff-edited-inlay-hints.rs'
    sd=load(q.lab/'complete.json')['seed_rlib']
    results={};states={};comparisons={}
    for workflow in ('selection','cold'):
        results[workflow]={};states[workflow]={}
        for arm in 'ABC':
            print(workflow,arm,flush=True)
            if workflow=='selection' and arm=='A':
                t=q.lab/'official-selection-control';out=q.lab/'official-selection';r=load(out/'product.json')
            else:
                assert shutil.disk_usage(p).free>65*2**30
                t=o/(workflow+'-state-'+arm);out=o/(workflow+'-'+arm)
                if workflow=='selection':
                    subprocess.run(['cp','-a','--reflink=auto','--',str(source),str(t)],check=True)
                    f=q.printed(t,sd['path'])
                    assert not f.samefile(q.printed(source,sd['path'])) and q.sha(f)==sd['sha256']
                    prior=load(q.lab/'official-selection/product.json')
                    assert not q.printed(t,prior['e2e'][0]).exists()
                else:q.state(t)
                r=q.run(t,executables[arm],q.select,out,historical if workflow=='selection' else None,trace=True)
            v=audit(out);test_list=list_test(t,executables[arm],r,out,historical if workflow=='selection' else None)
            own=r['ty_server'];calls=v['integration'][special];links=v['target_link_groups'][r['e2e'][0]]
            assert len(calls) in (1,2) and set(i['signature'] for i in calls)=={calls[0]['signature']}
            assert all(i['ty_extern']==['ty_server='+own['path']] or (len(i['ty_extern'])==1 and Path(i['ty_extern'][0].split('=',1)[1]).name==Path(own['path']).name) for i in calls)
            if workflow=='selection':
                assert own['fresh'] and (own['path'],own['sha256'])==(sd['path'],sd['sha256'])
                assert len(calls)==len(links)==(1 if arm=='C' else 2) and all(i['end'][1]==0 for i in calls)
                assert all(len(l['ty_rlibs'])==1 and Path(l['ty_rlibs'][0]).name==Path(own['path']).name for l in links)
            else:
                assert len(r['dirty'])==619 and not own['fresh']
            states[workflow][arm]=t
            results[workflow][arm]=dict(physical=dict(compiles=v['rustc'],count=v['total'],distinct=v['distinct'],wild=v['actual_wild'],distinct_wild=v['distinct_wild'],
                duplicated_sources=sorted(g[0]['source'] for g in v['repeated'].values())),test_list=test_list,e2e_calls=calls,e2e_links=links,
                product=q.sha(out/'product.json'),roster=r['roster'],e2e=r['native'][r['e2e'][0]],ty_server=own)
            if arm=='A':left=r
            else:
                comparisons[workflow+'/'+arm]=compare(left,r,states[workflow]['A'],t)
                assert results[workflow]['A']['test_list']==test_list
            q.put(o/'progress.json',dict(results=results,comparisons=comparisons))
        if workflow=='cold':
            b=results[workflow]['B']['physical'];cc=results[workflow]['C']['physical']
            assert b['distinct']==cc['distinct'] and b['distinct_wild']==cc['distinct_wild']
            assert b['count']>cc['count'] and b['wild']>cc['wild']
    assert all(results['selection'][a]['e2e']!=results['cold'][a]['e2e'] for a in 'ABC')
    q.source_gate();q.put(o/'complete.json',dict(results=results,comparisons=comparisons,all_tests_executed_during_build=0))
    print('all three matched arms and two workflows passed',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException:
        if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
        raise
