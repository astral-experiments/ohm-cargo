import ast,collections,hashlib,json,os,re,sys
from pathlib import Path
Y=Path(__file__).resolve().parent
D=Y/'archive-fs-restore';raw=D/'raw'
qre=re.compile(r'"((?:[^"\\]|\\.)*)"')
target_names=sorted(r['name']for r in json.loads((D/'all-jobs.json').read_bytes())['all_rustc_jobs'] if r['types']==['lib'] or r['types']==['cdylib','rlib'])
assert len(target_names)==32
patt=re.compile(r'lib('+'|'.join(map(re.escape,target_names))+r')(?:-[a-z0-9]+)?[.]rlib')
term=re.compile(r'\)\s+= ([0-9]+)(?:<[^\n]*>)?$')
linesha=lambda s:hashlib.sha256(s.encode('utf-8','surrogateescape')).hexdigest()
files={int(t.name.split('.')[-1]):t for t in raw.glob('exec.*')}
jobs=json.loads((D/'all-jobs.json').read_bytes())['all_rustc_jobs']; job={j['root']:j for j in jobs}
clones=collections.defaultdict(set);parents={}
events=[];pathmap={};execs=collections.defaultdict(list)
for tid,f in sorted(files.items()):
    for ix,line in enumerate(f.open(errors='surrogateescape'),1):
        s=line.rstrip();syscall=s.partition('(')[0]
        if syscall in ('clone','clone3','fork','vfork') and (m:=term.search(s)):
            child=int(m[1]);parents[child]={'parent':tid,'at_line':ix,'thread':'CLONE_THREAD' in s}
            if 'CLONE_THREAD' in s: clones[tid].add(child)
        if syscall=='execve' and s.endswith('= 0'):
            head=qre.search(s);exe=Path(head[1]).name if head else '?';execs[tid].append((ix,exe))
        if syscall not in ('open','openat','openat2','link','linkat','unlink','unlinkat','rename','renameat','renameat2'):continue
        if not patt.search(s):continue
        args=qre.findall(s)
        matches=[p for p in args if patt.fullmatch(Path(p).name)]
        if not matches:continue
        names={patt.fullmatch(Path(p).name)[1] for p in matches}
        assert len(names)==1
        opens=syscall.startswith('open')
        result=term.search(s);code=int(result[1]) if result else None
        err=re.search(r'= -1 ([A-Z0-9]+)',s)
        ev={'tid':tid,'line':ix,'syscall':syscall,'success':code is not None,
            'errno':err[1] if err else None,'paths':args,'crate':next(iter(names)),
            'file_line_sha256':linesha(s),'write_open':opens and ('O_WRONLY'in s or 'O_RDWR'in s),
            'read_open':opens and 'O_RDONLY'in s}
        events.append(ev)
all_threads={}
for top,j in job.items():
    fam={top};todo=[top]
    while todo:
        more=clones[todo.pop()]-fam;fam.update(more);todo.extend(more)
    for t in fam:
        assert t not in all_threads;all_threads[t]=j
for z in events:
    j=all_threads.get(z['tid'])
    if j:z['owner']={'crate':j['name'],'types':j['types'],'root':j['root']}
    else:
        t=z['tid']
        while t not in execs and t in parents:t=parents[t]['parent']
        z['owner']={'exe':execs.get(t,[['','?']])[-1][1],'root':t}

effective={}
for tid in files:
    parent=tid
    while parent in parents and parents[parent]['thread']:
        parent=parents[parent]['parent']
    effective[tid]=parent
lines={tid:files[tid].read_text().splitlines() for tid in set(effective.values())}
results=[]
regular={'ruff_python_parser','ruff_python_formatter','ruff_linter'}
for name in target_names:
    c=[ev for ev in events if ev['crate']==name]
    rust=next(j for j in jobs if j['name']==name and (j['pure'] or j['types']==['cdylib','rlib']))
    writes=[z for z in c if not z['syscall'].startswith('open') or z['write_open']]
    un=[z for z in writes if z['syscall']in ('unlink','unlinkat') and z['success']]
    hashed=[z for z in un if Path(z['paths'][0]).parent.name=='out']
    up=[z for z in un if Path(z['paths'][0]).parent.name=='debug']
    orig=[z for z in writes if z['syscall'].startswith('rename') and z['success'] and z['paths'][0].endswith('/tmp.a')]
    install=[z for z in writes if z['syscall']in ('link','linkat') and z['success'] and Path(z['paths'][-1]).parent.name=='debug' and Path(z['paths'][-1]).name=='lib'+name+'.rlib']
    assert len(hashed)==len(orig)==1, (name,hashed,orig,[(a['syscall'],a['paths'])for a in writes])
    assert orig[0]['paths'][-1]==hashed[0]['paths'][-1]
    hashed=hashed[0];orig=orig[0]
    path=hashed['paths'][0]
    assert hashed['owner']['exe']=='cargo' and orig['owner']['root']==rust['root']
    worker=hashed['tid']; top=rust['root']; chain=[]
    while top in parents:
        parent=parents[top]
        chain.append([top,parent['parent'],parent['at_line'],parent['thread']])
        if parent['parent']==worker:break
        top=parent['parent']
    assert chain[-1][1]==worker,(name,worker,chain)
    spawn=chain[-1][2]
    assert hashed['line']<spawn
    assert len(up)==len(install)<=1
    if up:
        assert up[0]['tid']==worker==install[0]['tid'] and up[0]['line']+1==install[0]['line'] and spawn<up[0]['line']
        assert install[0]['paths'][0]==path and install[0]['paths'][-1]==up[0]['paths'][0]
    other_first_path_mutations=[v for v in writes if v is not hashed and v is not orig and v not in up and v not in install and v['success']]
    assert not other_first_path_mutations,(name,other_first_path_mutations)
    fpaths=set(v['paths'][0]for v in c if v['syscall'].startswith('open') and v['read_open'])
    public='lib'+name+'.rlib'
    declared=[j for j in map(json.loads,(D/'stdout.jsonl').read_text().splitlines()) if j['reason']=='compiler-artifact' and j['target']['name']==name and j['target']['kind']in (['lib'],['cdylib','rlib'])]
    assert len(declared)==1
    before=[j for j in map(json.loads,(Y/'native-archive-inputs/cargo-stdout.jsonl').read_text().splitlines()) if j['reason']=='compiler-artifact' and j['target']['name']==name and j['target']['kind']in (['lib'],['cdylib','rlib'])]
    assert len(before)==1
    dec=[Path(k).name for k in declared[0]['filenames'] if k.endswith('.rlib')];prev=[Path(k).name for k in before[0]['filenames']if k.endswith('.rlib')];assert dec==prev
    dep=[z for z in c if z['read_open'] and path in z['paths']]
    def event(v):
        return {k:v[k] for k in ['tid','line','syscall','success','errno','file_line_sha256']} | {'names':[Path(a).name for a in v['paths']]}
    partial={'crate':name,'types':rust['types'],'unit_rlib':Path(path).name,'prior_reported_rlib':prev,'current_reported_rlib':dec,
        'cargo_root':hashed['owner']['root'],'rustc_root':rust['root'],'cargo_unlink':event(hashed),'spawn_branch':chain,
        'spawn_raw_line_sha256':linesha(files[worker].read_text().splitlines()[spawn-1]),'rustc_publish':event(orig),
        'cargo_unlink_old_uplift':event(up[0]) if up else None,'cargo_link_new_uplift':event(install[0]) if install else None,
        'reads_of_hashed_path':len(dep),'reads_of_prior_uplift':sum(z['read_open'] and Path(z['paths'][0]).parent.name=='debug' and public==Path(z['paths'][0]).name for z in c),
        'writes_other_than_unlinks_rename_reuplift':False}
    results.append(partial)
print('all, downstream, rooted uplifts, rooted prior, own reads',len(results),len(results)-1,sum(bool(v['cargo_unlink_old_uplift'])for v in results if v['crate']!='ruff_python_ast'),sum(v['prior_reported_rlib']==['lib'+v['crate']+'.rlib']for v in results if v['crate']!='ruff_python_ast'),sum(v['reads_of_prior_uplift']for v in results))
print('no uplift',[v['crate']for v in results if not v['cargo_unlink_old_uplift']])
out=D/'incumbent';out.mkdir(exist_ok=True)
(out/'result-v2.json').write_text(json.dumps({'dataset':'real full historical restoration','rows':results},sort_keys=True,indent=2)+'\n')
