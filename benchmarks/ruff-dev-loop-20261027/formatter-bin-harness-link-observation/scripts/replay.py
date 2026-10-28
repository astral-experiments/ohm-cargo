"""Replay a retained official Ruff package build at its original paths using private storage."""
from pathlib import Path
import ast, collections, fcntl, hashlib, json, os, runpy, shutil, subprocess, sys
HERE=Path(__file__).resolve().parent
D=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/format-display-test-v4-20261028')
STATE=HERE/'state'; SOURCE=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027')
SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
C=Path.home()/'.cache/ohm-233-position-qualified-20261027/formatter-display-2b1d3c6-h2-v4'
A=runpy.run_path(str(C/'reproduce.py'),run_name='closed-formatter-observation')
J=lambda f:json.loads(f.read_bytes())
sha=A['sha']; put=A['put']
token='81814697f8234e3f'
os.umask(0o077)
def guard():
    assert os.sched_getaffinity(0)==set(range(16,24))
    assert shutil.disk_usage(HERE).free>10*2**30
    assert subprocess.check_output(['git','-C',SOURCE,'rev-parse','HEAD']).decode().strip()==A['PLAN']['ruff']
    assert not subprocess.check_output(['git','-C',SOURCE,'status','--porcelain','-z'])
def command(args, env, name):
    with (out/(name+'.stdout')).open('xb') as so,(out/(name+'.stderr')).open('xb') as se:
        c=subprocess.run([*ns,*args],env=env,stdout=so,stderr=se)
    if c.returncode:raise RuntimeError((name,c.returncode,(out/(name+'.stderr')).read_text()[-2500:]))
def installed():
    files={'cargo':SDK/'bin/cargo','rustc':SDK/'bin/rustc','driver':next((SDK/'lib').glob('librustc_driver-*.so')),'wild':SDK/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
    assert {k:sha(p) for k,p in files.items()}==A['TOOLS']
guard();installed()
lock=(HERE/'private-worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not STATE.exists()
STATE.mkdir()
for d in ['target','shared','cargo','home','rustup']:
    subprocess.run(['cp','-a','--reflink=auto',D/d,STATE/d],check=True)
(STATE/'tmp').mkdir()
diag=A['PLAN']['path']; unit_main=Path('crates/ruff_python_formatter/src/main.rs')
shutil.copy2(D/'source-view.rs',STATE/'diagnostics.rs')
assert sha(STATE/'diagnostics.rs')==A['PLAN']['file_sha256']['original']
native_test=b'\n#[test]\nfn linked_error_brand() {\n    println!("{}", ruff_formatter::FormatError::PoorLayout);\n}\n'
original_main=(SOURCE/unit_main).read_bytes()
(STATE/'test-main.rs').write_bytes(original_main+native_test)
common_env=dict(HOME=str(D/'home'),PATH=str(Path(shutil.which('rustup')).parent)+':/usr/local/bin:/usr/bin:/bin',USER=os.environ.get('USER','dev-user'),RUSTUP_HOME=str(D/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(D/'cargo'),CARGO_TARGET_DIR=str(D/'target'),CARGO_BUILD_BUILD_DIR=str(D/'shared'),CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',LC_ALL='C.UTF-8',LANG='C.UTF-8',CARGO_TERM_COLOR='never',TMPDIR=str(D/'tmp'),GIT_OPTIONAL_LOCKS='0',CARGO_LOG='cargo::compiler::ohm_early_tests=info',WILD_WRITE_LAYOUT='1')
phases=[('prime','original',False),('edit','reverse',False),('restore','original',False),('observing-main','original',True),('observing-edit','reverse',True),('observing-restore','original',True)]
rootbind=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(HERE),str(HERE)]
for d in ['target','shared','cargo','home','rustup','tmp']:
    rootbind+=['--bind',str(STATE/d),str(D/d)]
historical=J(D/'receipts/restore-repeat/products.json')
def physical(path):
    return STATE/Path(path).relative_to(D)
for phase,sp,additional in phases:
    guard();out=HERE/phase;out.mkdir();(out/'trace').mkdir()
    view=STATE/'diagnostics.rs';want=(C/(sp+'.rs')).read_bytes()
    if view.read_bytes()!=want:view.write_bytes(want)
    assert sha(view)==A['PLAN']['file_sha256'][sp]
    ns=[*rootbind,'--ro-bind',str(view),str(SOURCE/diag)]
    if additional: ns+=['--ro-bind',str(STATE/'test-main.rs'),str(SOURCE/unit_main)]
    ns+=['--chdir',str(SOURCE),'--']
    args=['cargo','+ohm','test','--no-run','-p','ruff_python_formatter','--locked','--offline','-j4','--message-format=json']
    command(['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',str(out/'trace/exec'),*args],common_env,'cargo')
    vals=[json.loads(s) for s in (out/'cargo.stdout').read_bytes().splitlines()]
    assert vals[-1]=={'reason':'build-finished','success':True}
    rows=[r for r in vals if r['reason']=='compiler-artifact'];assert len(rows)==218
    nat=A['native'](out/'trace',SDK);put(out/'native.json',nat)
    jobs=collections.Counter(r['kind'] for r in nat['jobs'])
    if nat['failed_compilers']:raise RuntimeError(nat['failed_compilers'][0]['name'])
    prod={n:sha(physical(n)) for n in historical}
    put(out/'products.json',prod)
    if phase=='prime':
        assert all(prod[n]==historical[n]['sha'] for n in prod)
        assert not nat['jobs'] and not nat['links'] and all(r['fresh'] for r in rows)
    else:
        assert not nat['configure'] and all(v['wild'] for v in nat['links'])
    if phase in ('edit','restore','observing-edit','observing-restore'):
        assert jobs=={'full':1,'link-only':4} and len(nat['links'])==4,jobs
    harness,=[r['executable'] for r in rows if r['target']['kind']==['bin'] and r['profile']['test']]
    assert token in harness
    cli,=[r['executable'] for r in rows if r['target']['kind']==['bin'] and not r['profile']['test']]
    linkrows=[]
    for l in nat['links']:
        f=physical(l['output']); assert f.is_file()
        lay=f.with_name(f.name+'.layout');assert lay.exists(),f
        shutil.copyfile(lay,out/(f.name+'.layout'))
        linkrows.append({'name':f.name,'elf':sha(f),'layout':sha(lay),'all_args_sha256':l['raw']})
    command([harness,'--list'],common_env,'harness-list')
    listings=(out/'harness-list.stdout').read_bytes();assert (b'linked_error_brand: test' in listings)==additional
    if additional:
        command([harness,'--exact','linked_error_brand','--nocapture'],common_env,'observed')
        assert (b'internal '+(b'Ruff' if sp=='original' else b'Rome')+b' error') in (out/'observed.stdout').read_bytes()
    archive,=[physical(k) for k in historical if Path(k).name.startswith('libruff_formatter-') and k.endswith('.rlib')]
    shutil.copyfile(archive,out/'formatter.rlib')
    binout=physical(harness).parent
    rlink,=binout.glob('*.rlink')
    shutil.copyfile(rlink,out/'harness.rlink')
    shutil.copyfile(next(binout.glob('*.rlink-cache.json')),out/'harness.rlink-cache.json')
    fp=binout.parent/'fingerprint'
    for f in fp.iterdir():
        if f.is_file() and f.name!='invoked.timestamp':shutil.copyfile(f,out/f.name)
    objs={o.name:sha(o) for o in next(binout.glob('*.rlink-objects')).glob('*.o')}
    assert objs
    data={'phase':phase,'source':sp,'test_reader_added':additional,'source_diagnostics_sha':sha(view),'source_bin_root_sha':hashlib.sha256(original_main+(native_test if additional else b'')).hexdigest(),'fresh':sum(r['fresh'] for r in rows),'units':len(rows),'rustc':dict(jobs),'wilds':linkrows,'compiler_diag':[(v.get('message',{}).get('level'),v.get('message',{}).get('message')) for v in vals if v['reason']=='compiler-message'],'bin_sha':sha(physical(harness)),'cli_sha':sha(physical(cli)),'formatter_archive':sha(archive),'bin_rlink':sha(rlink),'objects':objs,'harness_list':listings.decode(),'observed':(out/'observed.stdout').read_text() if additional else None}
    put(out/'row.json',data)
    print(phase,jobs,len(linkrows),data['fresh'],data['bin_sha'][:10],data['formatter_archive'][:10],flush=True)
put(HERE/'complete.json',{'phases':[p[0] for p in phases],'tools':A['TOOLS']})
