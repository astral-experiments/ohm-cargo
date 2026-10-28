"""Qualify ordinary builds of two real Ruff members across a real typeshed edit and restoration."""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import mmap
import os
import shutil
import socket
import subprocess
import sys
import traceback
import zipfile

here=Path(__file__).resolve().parent
p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
o=p/'member-build-matched-native-v1'
canonical=p/'member-build-matched-canonical-v1'
images=p/'member-matched-images-v1'
sys.path.insert(0,str(here))
import capture
from member_reader import search_args,validate
from stub_bytes import read_stub
spec=importlib.util.spec_from_file_location('stock_validation',p/'early-completion-wall-protocol-v2/test-ruff.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
plan=json.loads((here/'plan.json').read_bytes())
stub=Path('crates/ty_vendored/vendor/typeshed/stdlib/functools.pyi')
target=canonical/'ruff target'
sdk=canonical/'Ohm-SDK'
def digest(b):return hashlib.sha256(b).hexdigest()
def emit(f,data):q.put(f,data)

def toolview(image,arm):
    result=o/('view-'+arm);result.mkdir()
    # The same donor SDK and rustlib are mounted in both subjects. Only cargo and the driver differ.
    paths=json.loads((here/'locations.json').read_bytes())
    donor=images/paths['common']; cargo=images/paths[image]['cargo'];driver=images/paths[image]['driver']
    assert all(x.is_file() for x in (cargo,driver,donor/'bin/rustc'))
    assert q.sha(cargo)==plan['arms'][image]['cargo_sha'] and q.sha(driver)==plan['arms'][image]['driver']
    assert q.sha(donor/'bin/rustc')==plan['common']['frontend']
    wild=donor/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    assert q.sha(wild)==plan['common']['wild']
    import re
    name,=re.findall(r'Shared library: \[(librustc_driver-[0-9a-f]+\.so)\]',subprocess.check_output(['readelf','-d',donor/'bin/rustc'],text=True))
    # Private bind targets must exist inside the read-only donor. The remote transport creates them.
    assert (donor/'lib'/name).is_file() and (donor/'bin/cargo').is_file()
    ru=result/'rustup/toolchains';ru.mkdir(parents=True);(ru/'ohm').symlink_to(sdk,target_is_directory=True)
    br=['--ro-bind',str(donor),str(sdk),'--ro-bind',str(cargo),str(sdk/'bin/cargo'),'--ro-bind',str(driver),str(sdk/'lib'/name)]
    checks={str(sdk/'bin/cargo'):q.sha(cargo),str(sdk/'bin/rustc'):q.sha(donor/'bin/rustc'),str(sdk/'lib'/name):q.sha(driver),
            str(sdk/wild.relative_to(donor)):q.sha(wild)}
    return ru.parent,br,checks

def worker(arm,pkg,initial,steps):
    image=arm[0];sample=o/(arm+'-'+pkg);sample.mkdir(mode=0o700)
    if (o/('view-'+arm)).exists():raise AssertionError('arm name must have unique state')
    ru,mount,checks=toolview(image,arm)
    state=sample/'state';q.state(state)
    env=q.opts(state,q.sdk/'bin/cargo')[1]
    env.update(HOME=str(canonical/'home'),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(canonical/'shared'),
               CARGO_HOME=str(canonical/'cargo'),RUSTUP_HOME=str(ru),CARGO_BUILD_JOBS='4')
    base=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',*mount]
    for n in ('target','shared','cargo','home'):base+=['--bind',str(state/n),str(target if n=='target' else canonical/n)]
    member=q.src/'crates'/pkg;overlay=sample/'visible-functools.pyi'
    def run(argv,dot):
        return subprocess.run([*base,'--ro-bind',str(overlay),str(q.src/stub),'--bind',str(dot),str(dot),'--chdir',member,'--',*argv],env=env,capture_output=True,stdin=subprocess.DEVNULL)
    blobs={s:(here/('stub-'+s+'.pyi')).read_bytes() for s in ('original','reversed')}
    for s,b in blobs.items():assert digest(b)==plan['stub'][s]
    val=initial;overlay.write_bytes(blobs[initial])
    probe=run(['rustc','+ohm','--print=sysroot'],sample);assert probe.returncode==0 and probe.stdout.decode().strip()==str(sdk)
    hashes=run(['sha256sum',*checks.keys()],sample);assert hashes.returncode==0
    assert {line.split('  ',1)[1]:line.split('  ',1)[0] for line in hashes.stdout.decode().splitlines()}==checks
    emit(sample/'binding.json',dict(hashes=checks,sysroot=probe.stdout.decode().strip(),image=image))
    roster0=None;search=None;series=[]
    for tag,kind in steps:
        assert shutil.disk_usage(p).free>40*2**30
        dot=sample/tag;dot.mkdir();(dot/'trace').mkdir()
        if val!=kind:
            old=overlay.stat().st_mtime_ns;overlay.write_bytes(blobs[kind]);assert overlay.stat().st_mtime_ns>old
            val=kind
        assert overlay.read_bytes()==blobs[kind]
        cmd=['cargo','+ohm','build','--locked','--offline','-j4','--message-format=json']
        trace=['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat','-o',str(dot/'trace/exec')]
        result=run([*trace,*cmd],dot)
        for ext,b in (('stdout',result.stdout),('stderr',result.stderr)):(dot/ext).write_bytes(b)
        emit(dot/'command.json',dict(code=result.returncode,argv=cmd,source=kind,expected=digest(blobs[kind]),mtime=overlay.stat().st_mtime_ns,
                                    stdout=digest(result.stdout),stderr=digest(result.stderr)))
        assert result.returncode==0,(pkg,tag,result.stderr[-1000:])
        rows=[json.loads(x) for x in result.stdout.splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
        arts=[x for x in rows if x['reason']=='compiler-artifact'];assert all(not x['profile']['test'] for x in arts)
        assert len(arts)==plan['units'][pkg]
        roster=sorted(json.dumps({k:x[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for x in arts)
        if roster0 is None:roster0=roster
        assert roster==roster0
        physical=capture.cmds(dot/'trace');emit(dot/'physical.json',physical)
        if search is None:search=search_args(dot,pkg)
        native={};vendored=[]
        for art in arts:
            n=art['target']['name']
            if n not in (pkg,'ty_vendored') or art['target']['kind']==['custom-build']:continue
            for f in map(Path,art['filenames']):
                rel=f.relative_to(target);actual=state/'target'/rel
                native[str(rel)]=q.sha(actual)
                if n=='ty_vendored' and f.suffix in ('.rlib','.rmeta'):vendored.append(actual)
        assert len(vendored)==2 and native and (pkg!='ty_wasm' or 'debug/libty_wasm.so' in native)
        archives=[f for n in ('target','shared') for f in (state/n).rglob('zipped_typeshed.zip')]
        assert len(archives)==1,len(archives)
        z,=archives
        with zipfile.ZipFile(z) as archive:assert read_stub(archive,'stdlib/functools.pyi')==blobs[kind]
        zipped=z.read_bytes()
        for item in vendored:
            with item.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as buf:assert buf.find(zipped)>=0
        caller=validate(pkg,dot,run,target,native,search,(here/'reader.rs').read_bytes(),blobs[kind])
        # The caller is out of the measured command and its result and hashes are retained in the ledger.
        jobs=[(x['crate'],x['kind']) for x in physical['jobs']]
        info=dict(step=tag,stage=kind,source=digest(blobs[kind]),units=len(arts),dirty=[x['target']['name'] for x in arts if not x['fresh']],
                  jobs=jobs,wild=len(physical['wild']),outputs=native,caller=caller,zip=digest(zipped),zip_path=str(z.relative_to(state)),
                  diagnostics=sorted(json.dumps(x,sort_keys=True) for x in rows if x['reason']=='compiler-message'),roster=digest('\n'.join(roster).encode()))
        emit(dot/'product.json',info);series.append(info);emit(sample/'progress.json',series)
        print(arm,pkg,tag,info['units'],len(info['dirty']),len(jobs),info['wild'],flush=True)
    return series

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024'
    assert (p/'member-build-spaces-protocol-v2/exit').read_text()=='0'
    assert not o.exists() and not canonical.exists() and shutil.disk_usage(p).free>110*2**30
    os.sched_setaffinity(0,set(range(8)));q.source_gate()
    with (p/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        o.mkdir(mode=0o700);canonical.mkdir(mode=0o700)
        for n in ('Ohm-SDK','ruff target','cargo','shared','home'):(canonical/n).mkdir()
        all_={}
        for name,pkg,initial,steps in plan['histories']:
            all_[name]=worker(name,pkg,initial,steps)
        q.source_gate();emit(o/'complete.json',all_)
if __name__=='__main__':
    try:main()
    except BaseException:
        if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
        raise
