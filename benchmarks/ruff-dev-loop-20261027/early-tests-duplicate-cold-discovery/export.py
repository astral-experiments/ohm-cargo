"""Identify literal repeated full-rustc invocations, and separately verify actual exit outcomes if traced."""
from pathlib import Path
import collections,json,hashlib,re,sys
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');r=p/'ron-first-replication-release-v1';bound=r/'bound-runner-b7b47a85';sys.path.insert(0,str(bound/'support'))
from replay_processes import records
def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
def take(argv,flag):
    return [argv[i+1] for i,v in enumerate(argv[:-1]) if v==flag]
def idv(argv,flag):
    value=take(argv,flag);return value[-1] if value else None
def suffix(argv):
    return next((a.split('=',1)[1] for a in argv if a.startswith('extra-filename=')),'')
def clean(s):return s.replace(str(p),'$RUN').replace('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027','$RUFF')
o={}
for arm in ('D','C'):
 d=r/'results'/('qualify-'+arm)/'cold';jobs=json.loads((d/'processes.json').read_bytes());expected={y[0] for y in jobs['rustc'] if y[2]=='full'};wild={z[0] for z in jobs['native_links'] if z[2]}
 sig=collections.defaultdict(list);args={};wi=collections.defaultdict(list);rcs=collections.defaultdict(set);sdk_ids=set()
 for f,exe,argv in records(d):
    if f in expected and '--crate-name' in argv and Path(exe).name=='rustc':
        dg=digest([exe,argv]);sig[dg].append(f);args[dg]=argv
    if f in wild and 'wild-ld' in exe and '-o' in argv:
        wi[idv(argv,'-o')].append((f,digest([exe,argv])))
 assert sum(map(len,sig.values()))==len(expected)==636
 duplicates={k:v for k,v in sig.items() if len(v)>1}
 allpids={int(i.split('.')[-1]) for prev in duplicates.values() for i in prev}|{int(i.split('.')[-1]) for v in wi.values() if len(v)>1 for i,_ in v}
 for f in d.glob('exec.*'):
    for l in f.read_bytes().splitlines():
        if b'si_status=' not in l:continue
        for code,pid,status in re.findall(br'si_code=(CLD_\w+), si_pid=(\d+),[^}]*?si_status=([\w]+)',l):
            pid=int(pid)
            if pid in allpids:rcs[pid].add((code.decode(),status.decode()))
 arts=[]
 for l in (d/'stdout').read_bytes().splitlines():
    x=json.loads(l)
    if x.get('reason')=='compiler-artifact':
        arts.append(x)
 assert len(arts)==619
 out=[]
 for k,ids in duplicates.items():
    a=args[k];extra=suffix(a);name=idv(a,'--crate-name');target=next((v for v in a if v.endswith('.rs') and not v.startswith('-')),None)
    output_dir=idv(a,'--out-dir')
    outputs=[(n,v) for n,v in wi.items() if n.startswith(output_dir+'/') and (Path(n).stem==name+extra or Path(n).stem.startswith('lib'+name+extra))]
    aj=[x for x in arts if any(fn.startswith(output_dir+'/') and extra in Path(fn).name for fn in x['filenames'])]
    cat=[dict(package=clean(x['package_id']),target=x['target']['name'],kind=x['target']['kind'],src=clean(x['target']['src_path']),features=x['features'],profile=x['profile'],fresh=x['fresh']) for x in aj]
    role=next((x['package_id'].rsplit('#',1)[0].rsplit('/',1)[-1] for x in aj if x['package_id'].startswith('path+')),'').replace('-','_')
    ex=take(a,'--extern')
    out.append(dict(crate=name,target=target,unit_metadata=next((v.split('=',1)[1] for v in a if v.startswith('metadata=')),None),extra_filename=extra,output_dir=clean(output_dir),
                    has_test='--test' in a,own_extern=[z.split('=',1)[0] for z in ex if z.split('=',1)[0]==role],extern_count=len(ex),rustc_complete_argv_sha256=k,rustc_ids=ids,rustc_exit_signal_observations={f:sorted(rcs.get(int(f.split('.')[-1]),())) for f in ids},cargo_rows=cat,
                    native_links=[dict(out=clean(n),successful_execs=[{'pid':f,'argv_sha256':h,'terminal':sorted(rcs.get(int(f.split('.')[-1]),()))} for f,h in v]) for n,v in outputs]))
 o[arm]=dict(total_compilers=636,distinct_argv=len(sig),duplicate_calls=sum(len(x)-1 for x in duplicates.values()),duplicate_groups=len(duplicates),groups=out,total_wild=len(wild),distinct_wild_output_paths=len(wi),duplicate_wild_output_calls=sum(len(v)-1 for v in wi.values() if len(v)>1),source_commitment=digest(sorted(expected)),source_status='strace execve with SIGCHLD where retained; an empty terminal array means no observed status, not success')
print(json.dumps(o,separators=(',',':')))
