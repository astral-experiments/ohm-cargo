"""Qualify original/full same-source variants of actual ELF products at two stock Cargo job budgets."""
from pathlib import Path
import collections,fcntl,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from shared import *
from replay_processes import parsed
from roster import audit_json
from elf import elf
ARM='StockProbe';expected='dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1'
def snapshots(ed):
    root=P/'results'/ed;return [load(root/arm/'complete.json') for arm in ['Stock11','A11']]
def selected(ed,phase):
    stock,cand=snapshots(ed);assert stock[phase]['state']==cand[phase]['state'];sa,sc=[x[phase]['elfs'] for x in (stock,cand)]
    need(sa.keys()==sc.keys() and len(sa)==110,('roster',ed,phase));out={}
    for path,a in sa.items():
        c=sc[path];need(a['content_with_two_wild_fields_masked']==c['content_with_two_wild_fields_masked'],('genuine product divergence',ed,phase,path,a,c))
        required={a['raw'],c['raw']}
        if phase=='edit-again':
            xx=stock['edit']['elfs'][path];yy=cand['edit']['elfs'][path]
            need(xx['content_with_two_wild_fields_masked']==yy['content_with_two_wild_fields_masked']==a['content_with_two_wild_fields_masked'],('first actual state to trained',ed,path))
            required |= {xx['raw'],yy['raw']}
        if len(required)>1:out[path]={'A':a,'C':c,'required':sorted(required)}
    return out
def prepare(ed,out):
    st=state(ed,ARM);base=state(ed,'Stock11');need(not st.exists() and not out.exists(),'new independent reference state');floors(16*2**30);st.mkdir(parents=True);out.mkdir(parents=True)
    subprocess.run(['cp','-a','--reflink=auto','--',*[str(base/n) for n in ['target','build','home','rustup','inputs','source-state']],str(st)],check=True)
def cargo(out,envs,width,controlled):
    d=out;d.mkdir();cmd=plan()['command']
    with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
        import signal,time
        read,write=os.pipe();os.write(write,b'+'*(width-1))
        e=dict(envs)
        if controlled:e['MAKEFLAGS']=f'-j --jobserver-auth={read},{write}'
        try:
            p=subprocess.Popen(['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(d/'exec'),*cmd],cwd=WT,env=e,stdin=subprocess.DEVNULL,stdout=so,stderr=se,pass_fds=(read,write) if controlled else (),start_new_session=True)
            while p.poll() is None:
                if controlled and sum(x.lstrip().startswith('Compiling ') for x in (d/'stderr').read_text(errors='replace').splitlines())>1:
                    os.killpg(p.pid,signal.SIGTERM);p.wait();raise RuntimeError('stock single-unit oracle unexpectedly changed the unit namespace')
                time.sleep(0.2)
        finally:os.close(read);os.close(write)
    need(p.returncode==0,('ordinary Cargo',d,(d/'stderr').read_text()[-900:]))
    j=audit_json(d/'stdout','test');return j,parsed(d,j)
def inside(ed,phase,case,width,ix):
    base=P/'results'/ed/ARM;out=base/f'{phase}-{case}-{width}-v2-{ix}';edited=phase=='edit-again';view(ed,edited);trusted()
    need(sha(FROZEN/'bin/cargo')==expected and sha(FROZEN/'lib'/SONAME)==plan()['baseline_rustc'],'stock images')
    diff=load(base/(phase+'.differences.json'));paths={TARGET/k for k in diff} if ix=='all' else {TARGET/sorted(diff)[int(ix)]}
    if case=='force':
        moved=base/(out.name+'-withheld');moved.mkdir()
        for i,path in enumerate(sorted(paths)):
            parent=path.parent.parent
            need(parent.parent.name not in ('deps','debug') and parent.is_relative_to(TARGET),'controlled output path')
            # One normal unit fingerprint binary (the bare record), not either JSON/dep-info.
            fps=[p for p in (parent/'fingerprint').iterdir() if p.is_file() and not p.is_symlink() and p.suffix=='' and not p.name.startswith(('dep-','output-','ohm-','invoked.timestamp'))]
            need(len(fps)==1 and fps[0].stat().st_nlink==1,('normal Cargo per-unit fingerprint',parent,[x.name for x in fps]))
            shutil.copy2(fps[0],moved/(str(i)+'-'+fps[0].name));need(sha(fps[0])==sha(moved/(str(i)+'-'+fps[0].name)),'preserve private record');fps[0].unlink()
    j,r=cargo(out,env(),width,case=='force')
    if case=='force':
        need(len(r['rustc'])==1 and all(x[2]=='full' for x in r['rustc']),('true full stock reference',r))
        observed={x[1] for x in r['native_links'] if x[2] and not x[3]};need(all(p.name in observed for p in paths),('ordinary Wild missing requested target',paths,observed))
    if case=='fresh':need(not j['dirty'] and not r['rustc'] and not r['native_links'],'witness not fresh')
    results={str(x.relative_to(TARGET)):{k:v for k,v in elf(x).items() if k in ('raw','content_with_two_wild_fields_masked','rodata_entsize','gnu_build_id','size')} for x in paths}
    dump(out/'data.json',{'source':phase,'case':case,'stock_jobs':width,'dirty':j['dirty'],'rustc':r['rustc'],'wild':r['native_links'],'elfs':results})
    print(ed,phase,case,width,len(r['rustc']),len(r['native_links']),flush=True)
def run(ed):
    base=P/'results'/ed/ARM;st=state(ed,ARM)
    if st.exists():need(ed=='__no_existing_private_target__' and not (base/'complete.json').exists() and (base/'edit-again-settle-8/data.json').is_file() and not list(base.glob('*force-1/exec.*')),'specifically identified unmodified stock reference')
    else:prepare(ed,base)
    for phase in ['edit-again','restore']:
        diff=selected(ed,phase);dump(base/(phase+'.differences.json'),diff)
        if not diff:continue
        mark(st,fixture(ed),phase=='edit-again')
        jobs=[('settle',8,'all')]+[('force',w,str(i)) for i in range(len(diff)) for w in (1,8)]+[('fresh',8,'all')]
        for case,w,ix in jobs:
            subprocess.run([*shell(ed,ARM),sys.executable,'-B',__file__,'inside',ed,phase,case,str(w),ix],check=True,env=env())
        cold=state('parser','A')/'target';proof={}
        for i,path in enumerate(sorted(diff)):
            v=diff[path];obs=[load(base/f'{phase}-force-{w}-v2-{i}'/'data.json') for w in (1,8)]
            witnessed={z['elfs'][path]['raw'] for z in obs}
            original=sha(cold/path) if (cold/path).is_file() else None
            if all(z['elfs'][path]['content_with_two_wild_fields_masked']==v['A']['content_with_two_wild_fields_masked'] for z in obs) and original in v['required']:witnessed.add(original)
            need(set(v['required'])<=witnessed,('no exact independent stock oracle',ed,phase,path,v,witnessed))
            proof[path]={'required_raw':v['required'],'forced_full_jobs_1_8':[z['elfs'][path]['raw'] for z in obs],'independent_cold_full_original':original}
        dump(base/(phase+'.qualified.json'),proof)
    dump(base/'complete.json',{'source':'unmodified FIFO-safe stock Cargo, exact retained same-path inputs','phases':{p:(load(base/(p+'.qualified.json')) if (base/(p+'.qualified.json')).is_file() else {}) for p in ['edit-again','restore']}})
if sys.argv[1:2]==['inside']:inside(*sys.argv[2:-2],int(sys.argv[-2]),sys.argv[-1]);sys.exit(0)
with (P/'bench.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    need(not (P/'results/A11-screen-grant').is_file(),'scores already started')
    if not (TRANSFER/ARM).exists():shutil.copy2(TRANSFER/'A',TRANSFER/ARM)
    need(sha(TRANSFER/ARM)==expected,'stock');run(sys.argv[1])
