"""Width-aware known-answer and selected-byte feasibility. No general cache correctness claim."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time,traceback
from runpy import run_path
pilot=Path(__file__).resolve().parent
d=pilot.parent
pre={'__file__':str(d/'layout-cohort.py'),'__name__':'donor'}
exec(compile((d/'layout-cohort.py').read_text().split('out=private/"products"')[0],str(d/'layout-cohort.py'),'exec'),pre)
sc=pre['sc'];env=pre['env'];root=pre['root'];sha=pre['sha'];save=pre['save']
ref=json.loads((d/'products/restored/row.json').read_bytes())
gold=pilot/'native-oracles-v2'
subject=pilot/'target/release/wild'
assert sha(subject)=='d86acbc7ad43299d9a2f9ae2d8609d1f1070b671a46a18dcad6e220d4e9f13ea'
assert sha(pilot/'pilot-plan.json')=='aa7646262ad696a5001360ee978481a56bfda1227b3abf90cd12e54224fd9ccc'
assert len(json.loads((pilot/'qualification-v2/complete.json').read_bytes()))==64
api=run_path(str(d/'audit.py'))
plan=json.loads((pilot/'pilot-plan.json').read_bytes()); args=['cargo','+ohm','test','--no-run','-p','ruff_python_parser','--locked','--offline','-j8']
base=dict(env,LD_PRELOAD=str(pilot/'stock-dispatch.so'),OHM_DEDENT_DIAGNOSTIC_WILD=str(subject),OHM_DEDENT_PILOT_ROOT=str(gold))
libs=[Path(p) for p in ref['artifacts'] if 'libruff_python_trivia-' in p and p.endswith('.rlib')];assert len(libs)==1
lib=libs[0];target_elf={Path(p).name:(Path(p),h) for p,h in ref['elf'].items()}
assert len(target_elf)==3
study=pilot/'whole-pilot-v2';phase=sys.argv[1];assert phase in ('qualify','score')
if phase=='qualify':study.mkdir()
baseout=study/phase;baseout.mkdir()
W=sc['W']
current='restored'
def source(st):
    if current==st:sc['gate'](st);return
    sc['adjust'](st)
def native_state(st):return 'original' if st=='restored' else st
def baseline_objects(st):
 m,i=api['archive']((d/'products'/st/'trivia.rlib').read_bytes());return {k:api['sha'](v[3]) for k,v in m.items() if k.endswith('.o')},i
expected={st:baseline_objects(st) for st in ['reversed','restored']}
def integrity(st,logs):
    p={}
    for name,(f,h) in target_elf.items():
        if name in logs:
            w=logs[name]['width'];h=sha(gold/(name+('.one' if w==1 else '.multi')))
        val=sha(f);assert val==h,(name,val,h)
        p[name]=val
    actual,idx=api['archive'](lib.read_bytes());bytes_expected,idx_expected=expected[st]
    assert {k:api['sha'](v[3]) for k,v in actual.items() if k.endswith('.o')}==bytes_expected and idx==idx_expected
    return p
def marks(out):
    hits={}
    for f in (out/'logs').iterdir():
        _pid,name=f.name.split('-',1);q=f.read_text().split()
        assert name in target_elf and name not in hits and 1<=int(q[0])<=8
        hits[name]={'width':int(q[0]),'mode':q[1],'admitted':q[2]=='true','selected':q[3] if len(q)>3 else None}
    return hits
def run(out,st,mode,action):
    out.mkdir();(out/'logs').mkdir()
    e=dict(base,OHM_DEDENT_PILOT_MODE=mode,OHM_DEDENT_PILOT_TRACE=str(out/'logs'))
    cmd=args if action=='ordinary' else args+['--message-format=json']
    if action=='trace':cmd=['strace','-ff','-qq','-e','trace=execve','-s','100000','-o',str(out/'exec')]+cmd
    t=time.perf_counter_ns()
    with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
        z=subprocess.run(cmd,env=e,cwd=W,stdout=so,stderr=se)
    n=time.perf_counter_ns()-t;save(out/'process.json',{'argv':cmd,'ns':n,'rc':z.returncode});assert z.returncode==0,(out,(out/'stderr').read_text()[-600:])
    h=marks(out);r={'source':st,'mode':mode,'action':action,'ns':n,'links':h}
    if action=='ordinary':
        assert 'Running ' not in (out/'stderr').read_text()
        assert len(h)==2 and all(v['mode']==mode and v['admitted']==(mode in ['oracle','selected']) for v in h.values()),(out,h)
        r['elf']=integrity(st,h)
    else:
        msgs=list(map(json.loads,(out/'stdout').read_bytes().splitlines()));assert msgs[-1]=={'reason':'build-finished','success':True}
        art=[m for m in msgs if m['reason']=='compiler-artifact'];r['total']=len(art);r['fresh']=sum(m['fresh'] for m in art)
        assert len(art)==148
        if action=='fresh':
            assert r['fresh']==148 and not h,(out,r['fresh'],h)
        else:
            r['roster']=sc['native_trace'](out)
            assert sorted(r['roster']['jobs'])==sorted(ref['processes']['jobs']) and sorted(r['roster']['wild'])==sorted(ref['processes']['wild'])
            assert r['fresh']==142 and len(h)==2 and all(v['mode']==mode and v['admitted']==(mode in ['oracle','selected']) for v in h.values()),(out,h)
            r['elf']=integrity(st,h)
    save(out/'receipt.json',r);return r
def ordinary_negative(out,st):
    out.mkdir();(out/'logs').mkdir();name=[n for n in target_elf if n.startswith('ruff_python_parser-')][0]
    e=dict(base,OHM_DEDENT_PILOT_MODE='selected',OHM_DEDENT_PILOT_TRACE=str(out/'logs'))
    orig=json.loads((root/'records/test/layout-restored/ordinary-0/argv.json').read_bytes());orig[-1]=str(out/name)
    flags=['-Clinker-features=-lld','-Clink-self-contained=-linker','-Clink-arg=-B'+str(pre['sdk']/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),'-Clink-arg=-fuse-ld=bfd']
    z=subprocess.run(orig+flags,env=e,cwd=W,capture_output=True);(out/'stderr').write_bytes(z.stderr);assert z.returncode==0,z.stderr
    hits=marks(out);assert len(hits)==1 and not hits[name]['admitted'],hits
    z=subprocess.run([str(out/name)],capture_output=True);assert z.returncode==0 and not z.stderr and z.stdout.decode()==sc['plan']['oracles'][native_state(st)]
    save(out/'receipt.json',{'argv':orig+flags,'links':hits,'stdout':z.stdout.decode(),'elf':sha(out/name)})
sc['gate']('original');results=[]
try:
    run(baseout/'initial-fresh',current,'full','fresh')
    if phase=='qualify':
        for n,(st,m) in enumerate([('reversed','full'),('restored','selected'),('reversed','oracle'),('restored','full')]):
            sc['adjust'](st);current=st
            r=run(baseout/f'trace-{n}-{m}',st,m,'trace');results.append(r);print('qualified',st,m,{k:(v['width'],v['admitted']) for k,v in r['links'].items()},flush=True)
            run(baseout/f'fresh-{n}',st,m,'fresh')
            if n<2:ordinary_negative(baseout/f'negative-{n}',st)
    else:
        assert (study/'qualify/complete.json').is_file()
        # At each scored slot the current source actually changes. When necessary, insert
        # a normal full opposite-direction reset and check it is fully fresh first.
        for block in plan['schedule']:
            st=block['direction'];other='restored' if st=='reversed' else 'reversed'
            for j,m in enumerate(block['order']):
                k=f"{block['block']:02}-{j}"
                if current!=other:
                    sc['adjust'](other);current=other
                    run(baseout/('reset-'+k),other,'full','ordinary')
                run(baseout/('pre-fresh-'+k),other,'full','fresh')
                sc['adjust'](st);current=st
                r=run(baseout/('slot-'+k),st,m,'ordinary')
                r.update(block=block['block'],slot=j);results.append(r)
                run(baseout/('after-fresh-'+k),st,m,'fresh')
                print(k,m,st,r['ns'],[a['width'] for a in r['links'].values()],flush=True)
    save(baseout/'complete.json',results)
finally:
    if current=='reversed':sc['adjust']('restored');current='restored';run(baseout/'final-restoration',current,'full','trace')
    sc['gate']('original')
