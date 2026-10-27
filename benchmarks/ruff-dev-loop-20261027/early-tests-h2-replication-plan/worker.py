"""Independent -16 Ruff first-selection replication under one prebuilt producer per pair."""
from pathlib import Path
import collections,fcntl,gzip,hashlib,json,os,re,shutil,socket,subprocess,sys,time,tomllib,traceback
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here))
from products import digest,products,put,sha
from storage import archive,cleanup,commitment,guard,ram,restore,root,watch
from trace import audit
read=lambda p:json.loads(p.read_bytes()); X=Path.home()/'.cache/ohm-233-position-qualified-20261027';shared=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
src=Path.home()/'code/oss/ruff-ohm-whole-native-20261027';file=Path('crates/ty_server/tests/e2e/inlay_hints.rs')
original='a025b90170c496d6336023fa8857c4d2cb2ef77c2e601bf119e9feb3c1a71624';edit='24d443ea2c65e5879884b32e761fea2d5e0f3cd198fd0ea9a44bd27e52078fad'
pin='93526150df078af7dd8fc4226cdcc469539d2001';base='eea47e1d637a96d0d91dee825cf6a029d5123396ea1af1389aad187555fe2af3';cand='46d8d787ab0e8f346f9fc5186e6a9bbad6ccd8c822c193deed51e8c9e9452afd'
A='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568';sdkpath=X/'build-script-current-stock-sdk-v1/official.json';sdk=Path(read(sdkpath)['sdk_root']);canon=ram/'canonical';rustup=ram/'rustup'
seed=['test','--no-run','--workspace','--exclude','ty_server'];select=['test','--no-run','--workspace']
frozen=X/'finished-producer-first-selection-h2-v1/inputs'
bins={'A':sdk/'bin/cargo','B':frozen/'cargo-parent','C':frozen/'cargo-candidate'};images=dict(A=A,B=base,C=cand)
def source_gate():
    git=lambda *a:subprocess.check_output(['git','--no-optional-locks','-C',src,*a])
    assert git('rev-parse','HEAD').decode().strip()==pin and not git('status','--porcelain','-z') and sha(src/file)==original
    assert hashlib.sha256(git('ls-files','-s','-z')).hexdigest()=='fc84f15ac7401cd9bdc362e4574c6d395529766c16be2e6b032ac47fa63d21cd' and git('rev-parse','HEAD^{tree}').decode().strip()=='62d3f106c5e41f6022847f26ff8c7dc00139f7b1'
def tools_gate():
    assert socket.gethostname()=='charlie-ohm-relink-b-1024' and os.sched_getaffinity(0)==set(range(16))
    j=read(sdkpath);assert j['archive_sha256']=='957ca8144205008ddaee75ef35f9775b2e428271c6b044e38bbdd8196c6bbf3e'
    paths={'cargo':sdk/'bin/cargo','driver':sdk/'lib'/j['driver_name'],'frontend':sdk/'bin/rustc','wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
    assert j['hashes']=={'cargo':A,'driver':'c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4','frontend':'b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}
    assert {k:sha(p) for k,p in paths.items()}==j['hashes'] and {a:sha(p) for a,p in bins.items()}==images
    source_gate();guard();return {'toolchain':j['hashes'],'cargo_arms':images,'host':socket.gethostname(),'cpu':sorted(os.sched_getaffinity(0)),'kernel':os.uname().release,'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'media':subprocess.check_output(['stat','-f','-c','%T',ram],text=True).strip()}
def initialize():
    assert not ram.exists();ram.mkdir(mode=0o700);canon.mkdir();rustup.mkdir();(rustup/'toolchains').mkdir();(rustup/'toolchains/ohm').symlink_to(sdk,target_is_directory=True);(rustup/'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
    for n in ('target','shared','cargo','home'):(canon/n).mkdir()
    assert sha(here/'historical.patch')=='a463e443b38886e1e9eacc34d77776e6c2f37c8e50263bebd12f400b4701dc48'
    tr=ram/'patch-context';(tr/file).parent.mkdir(parents=True);shutil.copy2(src/file,tr/file)
    subprocess.run(['git','apply','--no-index','--reverse',here/'historical.patch'],cwd=tr,check=True)
    assert sha(tr/file)==edit
def registry(t):
    assert not t.exists();t.mkdir(mode=0o700)
    for n in ('target','shared','cargo','home'):(t/n).mkdir(mode=0o700)
    reg=shared/'registry-home/registry';cache,=list((reg/'cache').iterdir());idx=reg/'index'/cache.name
    pkg=[s for s in tomllib.loads((src/'Cargo.lock').read_text())['package'] if s.get('source','').startswith('registry+')];assert len(pkg)==498
    ns=t/'cargo/registry';cc=ns/'cache'/cache.name;ci=ns/'index'/cache.name;cc.mkdir(parents=True);ci.mkdir(parents=True)
    out={}
    for v in pkg:
        name=v['name'];q=cache/(name+'-'+v['version']+'.crate');assert sha(q)==v['checksum'];shutil.copy2(q,cc/q.name);out['crate/'+q.name]=sha(cc/q.name)
        name=name.lower();k= ('1/'+name if len(name)==1 else '2/'+name if len(name)==2 else '3/'+name[0]+'/'+name if len(name)==3 else name[:2]+'/'+name[2:4]+'/'+name);srcindex=idx/'.cache'/k;dest=ci/'.cache'/k
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(srcindex,dest);out['sparse/'+k]=sha(dest)
    shutil.copy2(idx/'config.json',ci/'config.json');out['config']=sha(ci/'config.json');assert len(out)==498+458+1
    return digest(out)
def opts(t,arm,overlay):
    env=dict(HOME=str(canon/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',USER='dev-user',RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(canon/'cargo'),CARGO_TARGET_DIR=str(canon/'target'),CARGO_BUILD_BUILD_DIR=str(canon/'shared'),CARGO_BUILD_JOBS='8',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0',LANG='C.UTF-8',LC_ALL='C.UTF-8')
    args=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
    args+=['--ro-bind',rustup,rustup]
    for n in ('target','shared','cargo','home'):args+=['--bind',t/n,canon/n]
    if arm!='A':args+=['--ro-bind',bins[arm],sdk/'bin/cargo']
    if overlay:args+=['--ro-bind',overlay,src/file]
    return args,env
def printed(t,n):return t/Path(n).relative_to(canon)
def command(t,arm,argv,out,overlay=None,trace=False,timed=False):
    assert not (trace and timed);out.mkdir(mode=0o700,parents=True);w,env=opts(t,arm,overlay);w+=['--bind',out,out,'--chdir',src,'--']
    assert subprocess.check_output([*w,'/usr/bin/sha256sum',sdk/'bin/cargo'],env=env).decode().split()[0]==images[arm]
    real=['cargo','+ohm',*argv,'--locked','--offline','-j8','--message-format=json'];cmd=real
    if trace:
        env['CARGO_LOG']='cargo::compiler::ohm_early_tests=info,cargo::compiler::job_queue=debug';(out/'trace').mkdir()
        cmd=['strace','-q','-ff','-ttt','-s','1048576','-e','trace=execve,execveat','-e','signal=SIGCHLD','-o',out/'trace/exec',*real]
    if timed:cmd=['/usr/bin/python3','-IB',here/'inside.py',out/'elapsed_ns',*real]
    with (out/'stdout').open('xb') as a,(out/'stderr').open('xb') as b:watch([*w,*cmd],stdin=subprocess.DEVNULL,stdout=a,stderr=b,env=env)
    put(out/'command.json',dict(command=real,arm=arm,cargo=images[arm],source=pin,overlay=sha(overlay) if overlay else original,traced=trace,elapsed_ns=int((out/'elapsed_ns').read_text()) if timed else None,stdout=sha(out/'stdout'),stderr=sha(out/'stderr')))
    rec=products(out,t,printed,argv,select)
    # The official release emits this legitimate diagnostic on the cold and all fresh phases.
    diag=[m.replace(str(src),'$RUFF') for m in rec['diagnostics']]
    assert digest(diag)=='6d465066830c855472a3d30b1d88e0bdeb5961feac9f319f445db562ad24fa11',(out,'unexpected compiler diagnostic',digest(diag))
    return rec
def caller(t,arm,overlay,rec,d):
    exe,=rec['e2e'];w,e=opts(t,arm,overlay);w+=['--chdir',src/'crates/ty_server','--'];e.update(INSTA_UPDATE='no')
    cp=subprocess.run([*w,exe,'--list'],capture_output=True,env=e,timeout=60,check=True)
    names=[v.removesuffix(': test') for v in cp.stdout.decode().splitlines() if v.endswith(': test')]
    possible=[v for v in names if v.endswith('inlay_hints::default_inlay_hints')];assert len(possible)==1,(len(names),possible)
    name,=possible;r=subprocess.run([*w,exe,'--exact',name,'--nocapture'],capture_output=True,env=e,timeout=90)
    (d/'oracle.stdout').write_bytes(r.stdout);(d/'oracle.stderr').write_bytes(r.stderr);assert name in r.stdout.decode(errors='replace')
    status='pass' if r.returncode==0 and b'1 passed' in r.stdout else 'old-snapshot-mismatch' if r.returncode==101 and b'1 failed' in r.stdout and b'snapshot' in r.stderr.lower() else 'unsupported'
    assert status!='unsupported',(r.returncode,r.stdout[-400:],r.stderr[-400:]);assert status=='pass' or sha(overlay)==edit
    # The registered caller is a real test, with the missing or valid old snapshot treated as its observable result.
    return dict(test=name,registered=len(names),list_sha256=hashlib.sha256(cp.stdout).hexdigest(),status=status,rc=r.returncode)
def linkgate(out,rec,arm,phase,expected=None):
    a=audit(out,src);w=a['typed_compilers'];lk=a['target_link_groups']
    if phase=='first':
        assert a['rustc']=={'full':3 if arm!='C' else 2} and a['actual_wild']==(3 if arm!='C' else 2)
        exe,=rec['e2e'];z=a['integration']['crates/ty_server/tests/e2e/main.rs'];links=lk[exe];assert len(links)==len(z)==(2 if arm!='C' else 1) and len({k['signature'] for k in z})==1
        lib=Path(rec['ty_server']['path']).name
        assert all(i['end'][1]==0 and len(i['ty_extern'])==1 and Path(i['ty_extern'][0].split('=',1)[1]).name==lib for i in z) and all(len(i['ty_rlibs'])==1 and Path(i['ty_rlibs'][0]).name==lib for i in links)
    elif phase in ('settled','restored-settled'):assert not w and not lk and not rec['dirty']
    assert all(i['end'][1]==0 for i in w)
    return dict(actual_rustc=a['rustc'],actual_wild=a['actual_wild'],distinct_wild=a['distinct_wild'],sources=[i['source'] for i in w],trace_index=sha(out/'original-trace-index.json'))
def assertion(t,post,prior):
    assert post['roster']==prior['roster'] and post['diagnostics']==prior['diagnostics'] and post['native']==prior['native'] and not post['dirty']
    assert post['ty_server']['features']==prior['ty_server']['features'] and post['ty_server']['sha256']==prior['ty_server']['sha256']
def seed_store(key,loc):
    t=ram/('work-seed-'+key);reg=registry(t);first=command(t,'A',seed,loc/'seed-0');assert not first['ty_server']['fresh']
    for i in range(1,6):
        later=command(t,'A',seed,loc/('seed-'+str(i)));assert later['ty_server']['sha256']==first['ty_server']['sha256']
        if not later['dirty']:break
    assert later['units']==617 and not later['dirty'] and len(later['native'])==108 and len(later['executables'])==100
    out=ram/('snapshot-'+key+'.tar.zst');manifest=loc/'snapshot.manifest.json.gz';sig=archive(t,out,manifest);checksum=sha(out);assert content_record_verified(manifest,sig)
    info=dict(registry_content=reg,seed_steps=i+1,uncompressed_inputs=sig,seed_file_manifest=sha(manifest),tar_sha256=checksum,archive_bytes=out.stat().st_size,seed_products=sha(loc/('seed-'+str(i))/'product.json'))
    put(loc/'seed.json',info);cleanup(t);guard();return out,later,info
def content_record_verified(f,sig):return commitment(json.loads(gzip.decompress(f.read_bytes())))==sig
def elf_seed_absent(sd,first):
    # Membership is independently checked against all native products and the complete
    # regained input manifest for the seed even though its full physical state was retired.
    n,=first['e2e'];return n not in sd['native'] and n not in sd['executables']
def arm_run(key,arm,loc,starchive,sd,info,traced):
    dest=loc/arm;dest.mkdir();t=ram/('work-'+key+'-'+arm)
    assert sha(starchive)==info['tar_sha256'];actual=restore(starchive,t,info['uncompressed_inputs']);assert actual==info['uncompressed_inputs']
    readback=command(t,arm,seed,dest/'preselect-fresh');assertion(t,readback,sd)
    prior_e2e_paths={str(q.relative_to(t)) for part in ('target','shared') for q in (t/part).rglob('e2e-*') if q.is_file() and q.suffix==''}
    overlay=t/'source-payload';overlay.write_bytes((ram/'patch-context'/file).read_bytes());assert sha(overlay)==edit
    first=command(t,arm,select,dest/'first',overlay,trace=traced,timed=not traced)
    assert first['ty_server']['fresh'] and (first['ty_server']['path'],first['ty_server']['sha256'])==(sd['ty_server']['path'],sd['ty_server']['sha256'])
    assert elf_seed_absent(sd,first) and str(printed(t,first['e2e'][0]).relative_to(t)) not in prior_e2e_paths
    assert first['native'].keys()>=sd['native'].keys() and all(first['native'][f]==v for f,v in sd['native'].items())
    assert collections.Counter(tuple(z[0:1]) for z in first['dirty'])=={('ty_server',):1,('e2e',):1},first['dirty']
    elf,=first['e2e'];assert elf not in sd['native'];ordinary={'first':caller(t,arm,overlay,first,dest/'first')};physical={}
    if traced:physical['first']=linkgate(dest/'first',first,arm,'first')
    fresh=command(t,arm,select,dest/'settled',overlay,trace=traced);assertion(t,fresh,first)
    if traced:physical['settled']=linkgate(dest/'settled',fresh,arm,'settled')
    overlay.write_bytes((src/file).read_bytes());os.utime(overlay,None);assert sha(overlay)==original
    restored=command(t,arm,select,dest/'restore',overlay,trace=traced)
    assert first['native'].keys()==restored['native'].keys() and [k for k,v in first['native'].items() if v!=restored['native'][k]]==[elf] and restored['ty_server']['fresh']
    assert restored['dirty']==[['e2e',['test']]] or restored['dirty']==[('e2e',['test'])],restored['dirty']
    ordinary['restore']=caller(t,arm,overlay,restored,dest/'restore');assert ordinary['restore']['registered']==ordinary['first']['registered'] and ordinary['restore']['list_sha256']==ordinary['first']['list_sha256']
    if traced:physical['restore']=linkgate(dest/'restore',restored,arm,'restore')
    last=command(t,arm,select,dest/'restored-settled',overlay,trace=traced);assertion(t,last,restored)
    if traced:physical['restored-settled']=linkgate(dest/'restored-settled',last,arm,'restored-settled')
    ans=dict(snapshot=actual,cargo=images[arm],ordinary=ordinary,processes=physical,first=dict(native=first['native'],dirty=first['dirty'],roster=first['roster'],diagnostics=first['diagnostics'],e2e=elf,exes=len(first['executables'])),restore=dict(native=restored['native'],dirty=restored['dirty'],roster=restored['roster'],diagnostics=restored['diagnostics']),elapsed_ns=read(dest/'first/command.json')['elapsed_ns'],capture={ph:[sha(dest/ph/'command.json'),sha(dest/ph/'product.json')] for ph in ('preselect-fresh','first','settled','restore','restored-settled')})
    put(dest/'complete.json',ans);cleanup(t);source_gate();return ans
def history(key,order,qualifying):
    dest=root/'histories'/key;dest.mkdir(parents=True);env=tools_gate();assert env['media']=='tmpfs';put(dest/'environment.json',env)
    st,sd,info=seed_store(key,dest);results={}
    for arm in order:
        print('starting history',key,arm,flush=True);results[arm]=arm_run(key,arm,dest,st,sd,info,qualifying);print('passed history',key,arm,flush=True)
    z=next(iter(results.values()))
    for a,v in results.items():
        assert all(v[k]==z[k] for k in ('ordinary','first','restore','snapshot')),(key,a,'full raw ELF/roster/diagnostic/caller equivalence')
    assert sha(st)==info['tar_sha256']
    rec=dict(mode='unscored' if qualifying else 'wall',order=order,initial=env,seed=info,arms={a:sha(dest/a/'complete.json') for a in order},ordinary=z['ordinary'],raw_selected_elf_agreement=len(z['first']['native']),raw_restored_elf_agreement=len(z['restore']['native']))
    put(dest/'complete.json',rec);cleanup(st);guard();return results
def main():
    mode=sys.argv[1];assert mode in ('qualify','score');os.sched_setaffinity(0,set(range(16)))
    with (shared/'native-measure.lock').open('r') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);guard();source_gate()
        subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=here,check=True)
        plan=read(here/'plan.json');assert all(sha(here/n)==h for n,h in plan['scripts'].items())
        if mode=='qualify':
            assert not (root/'histories').exists() and not (root/'times.json').exists();initialize();a=history('qualify','ABC',True)
            put(root/'qualified.json',dict(qualification=sha(root/'histories/qualify/complete.json'),plan=sha(here/'plan.json'),runner=sha(here/'SHA256SUMS'),elapsed_observations=0));return
        assert read(root/'score-grant.json')==dict(plan=sha(here/'plan.json'),qualification=sha(root/'qualified.json'),runner=sha(here/'SHA256SUMS')) and not (root/'times.json').exists()
        observations=[];control=read(root/'histories/qualify/complete.json');initial_boot=control['initial']['boot']
        for block,order in enumerate(plan['orders'],1):
            assert tools_gate()['boot']==initial_boot
            r=history('block-%02d'%block,order,False);ns={a:v['elapsed_ns'] for a,v in r.items()};assert min(ns.values())>0 and all(v['ordinary']==control['ordinary'] for v in r.values())
            observations.append(dict(block=block,order=order,ns=ns,complete=sha(root/'histories'/('block-%02d'%block)/'complete.json')))
            put(root/'times.part.json',observations)
        assert len(observations)==12;put(root/'times.json',observations);put(root/'finished.json',dict(times=sha(root/'times.json'),plan=sha(here/'plan.json'),runner=sha(here/'SHA256SUMS'),paired_slots=12,commands=24))
if __name__=='__main__':
    try:main()
    except BaseException:
        (root/(sys.argv[1]+'-first-failure.txt')).write_text(traceback.format_exc());raise
