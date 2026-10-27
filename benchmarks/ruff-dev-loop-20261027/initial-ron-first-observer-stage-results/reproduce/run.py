"""Run consecutive unmodified test builds in independent physical states at fixed paths."""
import collections, fcntl, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');sys.path.insert(0,str(P/'runner'))
from shared import BUILD,CH,FROZEN,FRONT,SONAME,TARGET,TRANSFER,WT,dump,env,floors,git,load,need,sha,skeleton,trusted
from replay_processes import parsed,records
import replay_processes
from roster import audit_json
# GNU ld without an explicit -o creates a.out; the exact default-trust build script uses this form.
# Preserve raw argv and distinguish this successful system link from bundled Wild.
def links_with_default_output(where):
    for pid,exe,argv in records(where):
        if exe=='/usr/bin/ld' and '-o' not in argv and '--help' not in argv and '--version' not in argv:
            need(any(s.endswith('/crti.o') for s in argv) and any(s.endswith('/crtn.o') for s in argv) and any(s.startswith('/tmp/') and s.endswith('.o') for s in argv),('unknown link',pid))
            yield pid,exe,[*argv,'-o','a.out']
        else:yield pid,exe,argv
replay_processes.records=links_with_default_output

HERE=Path(__file__).resolve().parent; registration=load(HERE/'plan.json'); R=P/'results/cold-ron-stage-v2'; ST=P/'states/cold-ron-stage-v2';TINY=P/'scratch-untouched-ron'

def tiny(path):
    (path/'src').mkdir(parents=True);(path/'tests').mkdir()
    (path/'Cargo.toml').write_text('[package]\nname="ohm_ron_convergence"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n')
    (path/'src/lib.rs').write_text('pub fn text(x: u32) -> String { ron::to_string(&x).unwrap() }\n')
    for n in range(4): (path/'tests'/f'pack_{n}.rs').write_text(f'#[test] fn ordinary_rust_caller() {{ assert_eq!(ohm_ron_convergence::text({n}),"{n}"); }}\n')
    shutil.copy2(WT/'Cargo.lock',path/'Cargo.lock')

def setup(small,policy):
    tag=('tiny' if small else 'whole')+'-'+policy;st=ST/tag; floors((1 if small else 16)*2**30);need(not st.exists(),('earlier state',st));st.mkdir(parents=True,mode=0o700)
    for name in ('target','build','home'):(st/name).mkdir(mode=0o700)
    shutil.copytree(P/'rustup',st/'rustup',symlinks=True)
    subprocess.run(['cp','-a','--reflink=auto','--',str(CH/'registry'),str(st/'home/registry')],check=True)
    for nm in ('config','config.toml'):
        if (CH/nm).is_file():shutil.copy2(CH/nm,st/'home'/nm)
    cmd=skeleton(st)
    for src,dst in [(P/'results',P/'results'),(st/'target',TARGET),(st/'build',BUILD),(st/'home',CH),(st/'rustup',P/'rustup')]:cmd+=['--bind',str(src),str(dst)]
    if small:
        tiny(st/'tiny');cmd+=['--bind',str(st/'tiny'),str(TINY)]
    cmd+=['--ro-bind',str(P/'first-proof-stage1'/'sysroot'),str(FROZEN),'--ro-bind',str(P/'first-proof-stage1'/'candidate-cargo'),str(FROZEN/'bin/cargo'),'--ro-bind',str(P/'first-proof-stage1'/'candidate-driver-v2'),str(FROZEN/'lib/librustc_driver-15d35e5526bb94f8.so'),'--','taskset','-c','0-23',sys.executable,'-B',str(HERE/'run.py'),'inside',tag]
    subprocess.run(cmd,cwd=WT,check=True,env=env())

def inside(tag):
    small=tag.startswith('tiny-');policy=tag.split('-')[-1];cwd=TINY if small else WT; e=env();e['CARGO_LOG']='cargo::compiler::fingerprint=info'
    if policy=='default':
        e.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');e.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST')
    need(not any(TARGET.iterdir()) and not any(BUILD.iterdir()) and not git('status','--porcelain') and git('rev-parse','HEAD').decode()==registration['source'],'fresh/unmodified start')
    trusted();need(sorted(os.sched_getaffinity(0))==list(range(24)) and sha(FROZEN/'bin/cargo')==registration['cargo'] and sha(FROZEN/'lib/librustc_driver-15d35e5526bb94f8.so')==registration['rustc_driver'] and sha(FROZEN/'bin/rustc')==registration['rustc_frontend'] and sha(P/load(TRANSFER/'installation.json')['bundled_wild'])==registration['wild'],'runtime identity')
    if small:subprocess.run(['cargo','+ohm','metadata','--format-version','1','--offline'],cwd=cwd,env=e,check=True,stdout=subprocess.DEVNULL)
    for phase in ('cold','unchanged-1','unchanged-2'):
        dest=R/tag/phase;dest.mkdir(parents=True);floors();argv=registration['command'];trace=['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(dest/'exec')];
        before=time.monotonic_ns()
        with (dest/'stdout').open('wb') as so,(dest/'stderr').open('wb') as se:
            proc=subprocess.run(trace+argv,cwd=cwd,env=e,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
        elapsed=time.monotonic_ns()-before;dump(dest/'status.json',{'status':proc.returncode,'elapsed_ns':elapsed});need(proc.returncode==0,('Cargo failed',dest))
        rows=[json.loads(line) for line in (dest/'stdout').read_bytes().splitlines()];arts=[r for r in rows if r.get('reason')=='compiler-artifact'];need(rows[-1]=={'reason':'build-finished','success':True},'incomplete Cargo output')
        if small:
            exes=sorted(r['executable'] for r in arts if r['executable']);need(len(exes)==5,'tiny test roster');j={'units':len(arts),'dirty':sorted(r['target']['name'] for r in arts if not r['fresh']),'executables':exes,'elf':exes,'roster':[],'messages':[]}
        else:j=audit_json(dest/'stdout','test')
        procs=parsed(dest,j);dump(dest/'processes.json',procs); refl=[r for r in arts if r['target']['name']=='ron'];need(len(refl)==1,'ron unit');ron=refl[0];rl,=[Path(p) for p in ron['filenames'] if p.endswith('.rlib')];rm,=[Path(p) for p in ron['filenames'] if p.endswith('.rmeta')];d,=rl.parent.glob('ron-*.d');fp=rl.parent.parent/'fingerprint';cp=dest/'ron';cp.mkdir()
        for p in [rl,rm,d,*fp.iterdir()]:
            if p.is_file():shutil.copy2(p,cp/p.name)
        native={str(p):sha(p) for p in j['elf']}; dump(dest/'raw-native.json',native)
        argv_r=[{'pid':pid,'args':a} for pid,x,a in records(dest) if Path(x).name=='rustc' and '--crate-name' in a and a[a.index('--crate-name')+1]=='ron'];dump(dest/'ron-argv.json',argv_r)
        s={'units':j['units'],'fresh':sum(r['fresh'] for r in arts),'dirty':j['dirty'],'full':[cr for _,cr,m,*_ in procs['rustc'] if m=='full'],'link_only':[cr for _,cr,m,*_ in procs['rustc'] if m=='link-only'],'wild':len(procs['native_links']),'elf_count':len(native),'executables':len(j['executables']),'all_wild':all(z[2] for z in procs['native_links']),'ron_files':{p.name:sha(p) for p in cp.iterdir()},'depinfo_checksum_count':sum(q.startswith('# checksum:') for q in d.read_text().splitlines()),'depinfo_markers':sorted(set(q for x in d.read_text().splitlines() for q in ('ohm-foreign-span-bytes','ohm-untrackable-foreign-span') if q in x)),'messages':hashlib.sha256(json.dumps(j['messages'],sort_keys=True).encode()).hexdigest(),'elapsed_ns':elapsed,'free':floors()};dump(dest/'summary.json',s);print(tag,phase,s['units'],s['fresh'],len(s['full']),len(s['link_only']),s['wild'],flush=True)
    need(not git('status','--porcelain'),'Ruff changed')
if sys.argv[1]=='inside':inside(sys.argv[2]);sys.exit(0)
with (P/'bench.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    need(not R.exists() and not ST.exists(),'nonempty independent stage whole state')
    small_bind=P/'first-proof-stage1/controls-v2'
    need(all((small_bind/(name+'.rc')).read_text().strip()=='0' for name in ('matrix','binary','permanent')),'prior small guards failed')
    need((P/'first-proof-stage1/proof-check-v2/receipts.json').is_file(),'no physical four-arm proof')
    R.mkdir(mode=0o700)
    setup(False,'default')
