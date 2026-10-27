"""Qualify the same small span-dependent program on the distributed, unmodified Ohm -15 Linux toolchain."""
from pathlib import Path
import hashlib, json, subprocess, sys
HERE=Path(__file__).resolve().parent
PKG_REPO=Path('/home/dev-user/code/oss/ohm-native-wild-package-20261027')
GH='/home/dev-user/.local/bin/gh-auto'
HOST='charlie-ohm-relink-perf-1024'
NAME='ohm-1.99.0-15-x86_64-unknown-linux-gnu.tar.gz'
PACKAGE_SHA='bd17067e6ca3343050bf4c3c64bb1959b996479a82868d01fbec29c4c4f79bf4'
PACKAGE_SIZE=359640412
TOP=Path('/dev/shm/ohm-packaged-15-macro-20261027')
FIXTURE=HERE.parent/'mixed-workspace-pairs/result-tools/minimal-transient-positions-v2.py'
def gh(*a):return subprocess.check_output([GH,*a],cwd=PKG_REPO)
def ssh(code,*a,**k):return subprocess.check_output(['dbox','ssh',HOST,'--no-tmux','--','/usr/bin/python3','-B','-c',code,*map(str,a)],**k)
def save(n,out):
    p=HERE/(n+'.json');p.write_bytes(out);print(out.decode()[:1200],flush=True)
mode,=sys.argv[1:];base='''import sys,os,json,hashlib,shutil,subprocess,socket
from pathlib import Path
r=Path(sys.argv[1]);sha=sys.argv[2];ss=int(sys.argv[3]);assert socket.gethostname()=='charlie-ohm-relink-perf-1024'
os.sched_setaffinity(0,{28,29});os.nice(12)
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def checkspace():assert shutil.disk_usage(r.parent).free>8<<30
def dump(f,v):f.write_text(json.dumps(v,sort_keys=True,indent=2)+'\\n')
checkspace()
''';args=[TOP,PACKAGE_SHA,PACKAGE_SIZE]
if mode=='transfer':
    identity=gh('api','user','--jq','.login').decode().strip();assert identity=='charliermarsh'
    release=json.loads(gh('release','view','ohm-1.99.0-15','--repo','astral-sh/ohm','--json','url,assets,tagName,publishedAt'))
    asset,=[a for a in release['assets'] if a['name']==NAME]
    assert asset['digest']=='sha256:'+PACKAGE_SHA and asset['size']==PACKAGE_SIZE
    save('provenance',json.dumps({'url':release['url'],'publishedAt':release['publishedAt'],'tag':release['tagName'],'asset':{k:asset[k] for k in ('name','url','size','digest')}},indent=2).encode())
    pipe=subprocess.Popen([GH,'release','download','ohm-1.99.0-15','--repo','astral-sh/ohm','--pattern',NAME,'--output','-'],cwd=PKG_REPO,stdout=subprocess.PIPE)
    try:
        data=ssh(base+'''r.mkdir(mode=0o700);f=r/'distribution.tar.gz';a=f.with_suffix('.partial')
with a.open('xb') as out:shutil.copyfileobj(sys.stdin.buffer,out,2**20)
assert a.stat().st_size==ss and h(a)==sha
a.replace(f);print(json.dumps({'sha256':sha,'bytes':f.stat().st_size}))
''',*args,stdin=pipe.stdout)
        pipe.stdout.close();assert pipe.wait()==0;save('transferred',data)
    finally:
        if pipe.poll() is None:pipe.terminate();pipe.wait()
elif mode=='run':
    f=FIXTURE.read_bytes();fx=hashlib.sha256(f).hexdigest()
    out=ssh(base+'''import tarfile,time
archive=r/'distribution.tar.gz';assert h(archive)==sha and archive.stat().st_size==ss
src=sys.stdin.buffer.read();fx=sys.argv[4];assert hashlib.sha256(src).hexdigest()==fx
test=r/'fixture.py'
if not test.exists():test.write_bytes(src)
assert h(test)==fx
sdkdir=r/'distribution'
if not sdkdir.exists():
    sdkdir.mkdir(mode=0o700)
    with tarfile.open(archive,'r:gz') as t:
        members=t.getmembers()
        assert sum(m.size for m in members)<5<<30 and all(not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
        t.extractall(sdkdir,members=members,filter='data')
dist,=[d for d in sdkdir.iterdir() if (d/'install.sh').is_file()];sdk=r/'installed-sdk'
assert not sdk.exists() and (dist/'git-commit-hash').read_text().strip()=='2169ab9678eb7c748acc1a9b89e7df21548dbd73'
with (r/'install.log').open('xb') as log:
    subprocess.run(['sh',str(dist/'install.sh'),'--prefix='+str(sdk),'--sysconfdir='+str(sdk/'etc'),'--disable-ldconfig','--components=rustc,cargo,rust-std-x86_64-unknown-linux-gnu'],stdout=log,stderr=subprocess.STDOUT,check=True)
rustc=sdk/'bin/rustc';cargo=sdk/'bin/cargo';driver,=(sdk/'lib').glob('librustc_driver-*.so')
assert h(cargo)==h(dist/'cargo/bin/cargo') and h(rustc)==h(dist/'rustc/bin/rustc') and h(driver)==h(dist/'rustc/lib'/driver.name)
descriptor=r/'rustup';(descriptor/'toolchains').mkdir(parents=True);(descriptor/'toolchains/ohm').symlink_to(sdk)
(descriptor/'settings.toml').write_text('version = "12"\\n\\n[overrides]\\n')
env={'HOME':str(Path.home()),'PATH':str(Path.home()/'.cargo/bin')+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','RUSTUP_HOME':str(descriptor),'RUSTUP_AUTO_INSTALL':'0'}
versions={k:subprocess.check_output([k,'+ohm','-vV'],env=env,text=True) for k in ('rustc','cargo')}
tools={'package_sha256':sha,'package_bytes':ss,'cargo':h(cargo),'frontend':h(rustc),'driver':h(driver),'versions':versions,'fixture_sha256':fx,'execution_host':socket.gethostname(),'caller_affinity':sorted(os.sched_getaffinity(0)),'sdk':str(sdk)}
dump(r/'installed.json',tools)
args=[sys.executable,'-B',str(test),'--report-old-semantics','--out',str(r/'fixture-output'),'--rustup',str(descriptor),'--sysroot',str(sdk),'--cargo',str(cargo),'--driver',str(driver),'--driver-soname',driver.name]
with (r/'stdout').open('xb') as so,(r/'stderr').open('xb') as se:
    cmd="import subprocess,sys; from pathlib import Path; q=subprocess.run(sys.argv[1:-1]); Path(sys.argv[-1]).write_text(str(q.returncode))"
    proc=subprocess.Popen([sys.executable,'-B','-c',cmd,*args,str(r/'exit')],env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,close_fds=True,start_new_session=True)
print(json.dumps(dict(tools,pid=proc.pid)))
''',*args,fx,input=f);save('installed',out)
elif mode=='poll':
    data=ssh(base+'''exitfile=r/'exit';done=exitfile.read_text().strip() if exitfile.is_file() else None
report={'exit':done,'tail':(r/'stderr').read_text()[-1000:] if (r/'stderr').exists() else None,'archive_bytes':(r/'distribution.tar.partial').stat().st_size if (r/'distribution.tar.partial').exists() else None,'installed':(r/'installed.json').is_file()}
if done=='0':
    p=r/'fixture-output/evidence';data=json.loads((p/'results.json').read_bytes())
    report['cases']={name:{'artifacts':{k:v['header'] for k,v in z['builds'].items()},'ordinary_readers':z['readers']} for name,z in data.items()}
    report['complete']=json.loads((p/'complete.json').read_bytes());report['result_sha256']=h(p/'results.json')
print(json.dumps(report))
''',*args);save('poll',data)
else:raise ValueError(mode)
