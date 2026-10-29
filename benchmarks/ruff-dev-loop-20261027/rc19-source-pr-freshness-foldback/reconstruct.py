"""Reopen the preserved controls, product versions, physical builds and standard suites."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path


PRIOR={'101':'62afc4ab5acf699478f72b8fdbd5927db1da26bb','103':'1a84f8f36f0ff9f283337bfcce856b4b54c47281'}
FIX={'101':'f12e6b41ad880c69c38c7f36bdd3ac219d538b1a','103':'1cbb910d0011480d7e4fcaf5cec8e2513cf6550c'}
RUSTC='c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'
MOD='src/compiler/fingerprint/mod.rs'

def digest(b):return hashlib.sha256(b).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_bytes())
def capture(args):return subprocess.check_output(args)
def brief(p):
    return {'sha256':sha(p),'bytes':p.stat().st_size}
def normalized_syscalls(path):
    """Keep just the precise flags for the two challenge paths, with raw hashes separately retained."""
    values={'fifo':[],'parent':[]}
    for line in path.read_text().splitlines():
        for suffix,kind in [('/lib-api"','fifo'),('/bin-client"','parent')]:
            if 'openat(' not in line or suffix not in line:continue
            tail=line.split(suffix,1)[1]
            m=re.match(r', ([A-Z0-9_|]+)',tail)
            assert m,line[:130]
            flags=m[1].split('|')
            values[kind].append({'flags':flags,'returned':bool(re.search(r'\)\s+= [0-9]+',tail)),'unfinished':'<unfinished' in tail})
    return values
def gas(root,n,*args):
    return capture(['git','--no-optional-locks','-C',root/f'ohm-cargo-fold-marker-pr{n}-20261028',*args])
def build(arm,number,stage):
    raw=load(arm/'build.json')
    expected=PRIOR[number] if stage=='prior' else FIX[number]
    stamp=FIX[number] if stage=='stamped' else PRIOR[number]
    assert raw['source']==expected and raw['stage']==stage and raw['pr']==number
    exe=arm/'sdk/bin/cargo'
    assert sha(exe)==raw['cargo'] and sha(arm/'sdk/bin/rustc')==raw['rustc']==RUSTC
    version=capture([exe,'-Vv']); assert ('commit-hash: '+stamp+'\n').encode() in version
    assert ('('+stamp[:9]+' ').encode() in version.splitlines()[0]
    messages=(arm/'build.jsonl').read_bytes()
    assert digest(messages)==raw['cargo_messages']
    rows=list(map(json.loads,messages.splitlines()))
    assert rows[-1]=={'reason':'build-finished','success':True}
    cargo,=[a for a in rows if a.get('executable') and a['target']['name']=='cargo']
    emits=[dict(a['env']) for a in rows if a['reason']=='build-script-executed' and 'CARGO_COMMIT_HASH' in dict(a['env'])]
    assert len(emits)==1 and emits[0]['CARGO_COMMIT_HASH']==stamp and emits[0]['CARGO_COMMIT_SHORT_HASH']==stamp[:9]
    assert cargo['target']['kind']==['bin'] and not cargo['fresh'] and 'ohm-defaults' in cargo['features']
    detail={'declaration':raw,'reported_cargo':version.splitlines()[0].decode(),'commit_reported':stamp,'cargo_vv':digest(version),'version_lines':version.decode().splitlines(),
            'build_script_stamp':{k:v for k,v in emits[0].items() if k.startswith('CARGO_COMMIT')},
            'artifacts':sum(a['reason']=='compiler-artifact' for a in rows),'physical_size':exe.stat().st_size,
            'build_stderr':brief(arm/'build.stderr'),'original_build_receipt':sha(arm/'build.json')}
    if stage=='stamped':
        assert (arm/'build.exit').read_bytes()==b'0\n' and sha(arm/'cargo-version')==raw['stdout_vv']==digest(version)
        assert sha(arm/'build-exec.log')==raw['build_trace'] and sha(arm/'launch.json')==raw['launch_sha256']
        with (arm/'build-exec.log').open(errors='replace') as f:
            compilers=[];git=[]
            for line in f:
                if 'execve(' not in line or not line.rstrip().endswith('= 0'):continue
                if '"--crate-name", "cargo"' in line and '"--crate-type"' in line:
                    compilers.append({'line_sha256':digest(line.encode()),'kind':'bin' if 'src/bin/cargo/main.rs' in line else 'lib'})
                if re.search(r'execve\("[^"]*/git",',line) and ('"log"' in line or '"rev-parse"' in line):
                    git.append(digest(line.encode()))
        assert {row['kind'] for row in compilers}=={'bin','lib'} and git
        detail.update(launch=load(arm/'launch.json'),compile_execves=compilers,git_queries=git,trace=brief(arm/'build-exec.log'))
    return detail
def recovery(arm,image):
    p=arm/'reverted';rep=load(p/'result.json')
    assert rep['mode']=='default' and rep['cargo_sha256']==image and rep['rustc_sha256']==RUSTC
    assert (p/'prime-program/stdout').read_bytes()==(p/'final-program/stdout').read_bytes()==b'1\n'
    for phase,row in rep['phases'].items():
        for file,h in row['files'].items():assert sha(p/phase/file)==h
        stderr=(p/phase/'stderr').read_text()
        assert re.findall(r'error\[(E[0-9]+)\]',stderr)==row['errors']
        lines=(p/phase/'exec.log').read_text().splitlines()
        # The unmodified registered fixture counts only direct frontend execs, excluding wrapper argv.
        rust=[]
        for line in lines:
            head=re.search(r'execve\("([^"]+)"',line)
            if head is None or not line.rstrip().endswith('= 0') or Path(head[1]).name!='rustc':continue
            name=re.search(r'"--crate-name", "(dep|app)"',line)
            kind=re.search(r'"--crate-type", "([^"]+)"',line)
            if name:rust.append([name[1],kind[1] if kind else None])
        assert rust==row['rustcs'],(arm.name,phase,rust,row['rustcs'])
    # Exercise program semantics and check the synchronized marker evidence preserved on disk.
    assert (p/'app/dependency-failed').is_file() and (p/'app/parent-started-early').is_file() and not (p/'app/parent-timed-out').exists()
    assert (p/'app/dep/src/lib.rs').read_bytes()==b'pub const VALUE: i32 = 1;'
    return {'result':rep,'original_receipt':sha(p/'result.json'),'program_stdout':{'prime':'1\n','final':'1\n'},
            'reverted_source_sha256':sha(p/'app/dep/src/lib.rs'),'forced_parent_started':True,'forced_producer_failed':True}
def fifo(base,arm,mode,variant):
    p=base/'fifo-audit'/arm.name/mode/variant;row=load(p/'result.json')
    assert (row['subject'],row['variant'],row['mode'])==(arm.name,variant,mode)
    assert row['cargo']==sha(arm/'sdk/bin/cargo') and row['rustc']==RUSTC
    for name,h in [('stdout',row['stdout']),('stderr',row['stderr']),('syscalls',row['trace'])]:assert sha(p/'probe'/name)==h
    prime=[json.loads(l) for l in (p/'prime/stdout').read_bytes().splitlines()]
    assert prime[-1]=={'reason':'build-finished','success':True} and sum(a['reason']=='compiler-artifact' and not a['fresh'] for a in prime)==4
    flags=normalized_syscalls(p/'probe/syscalls')
    assert len(flags['fifo'])==row['fifo_open_calls'] and len(flags['parent'])==row['root_open_calls']
    if variant=='parent-error':assert row['parent_eisdir'] and b'Is a directory' in (p/'probe/stderr').read_bytes()
    return {'result':row,'opens':flags,'prime_stdout':brief(p/'prime/stdout'),'prime_stderr':brief(p/'prime/stderr'),'original_receipt':sha(p/'result.json')}
def suites(arm,stage,anchor):
    if stage=='prior':return None
    p=arm/('suites-v5' if stage=='stamped' else 'suites-v2')
    q=load(p/'complete.json')
    assert q['source']==anchor['declaration']
    build_rows=[json.loads(l) for l in (p/'build.jsonl').read_bytes().splitlines()]
    assert build_rows[-1]=={'reason':'build-finished','success':True}
    bins={r['target']['name']+'-'+r['target']['kind'][0]:Path(r['executable']) for r in build_rows if r.get('executable')}
    sets={}
    for name,one in q['sets'].items():
        d=p/name;tr=d/'exec.log'
        for field,n in [('stdout','stdout'),('stderr','stderr'),('trace','exec.log')]:
            assert one[field]==sha(d/n)
        lines=(d/'stdout').read_text().splitlines()
        assert one['tests']==[line for line in lines if line.startswith('test ') and line.endswith(' ... ok')]
        assert len(one['tests'])==one['passed']
        kind='cargo-lib' if name=='fingerprints' else 'testsuite-test'
        # All tests are executed from the retained fresh-profile runnable when available.
        harness=bins[kind]; assert sha(harness)==one['harness']
        ok=[]
        for l in tr.read_text().splitlines():
            m=re.search(r'execve\("([^"]+)"',l)
            if m and l.rstrip().endswith('= 0') and Path(m[1]).name=='cargo' and (f'/target-{anchor["declaration"]["pr"]}/' in m[1]):
                ok.append(digest(l.encode()))
        assert len(ok)==one['physical_cargo_calls'],(stage,name,len(ok),one['physical_cargo_calls'])
        sets[name]={**one,'native_cargo_events':ok}
        if stage=='stamped':
            bind=load(d/'mounted.json')
            assert sha(d/'mounted.json')==one['mounted'] and bind['mounted_product_sha256']==anchor['declaration']['cargo']
            assert bind['same_inode'] and bind['version_sha256']==anchor['cargo_vv'] and bind['commit']==anchor['commit_reported']
            assert (d/'exit').read_bytes()==b'0\n'
            sets[name]['mount_witness']=bind
    result={'sets':sets,'build_jsonl':brief(p/'build.jsonl'),'build_stderr':brief(p/'build.stderr'),'original_receipt':sha(p/'complete.json')}
    if stage=='stamped':
        initial=arm/'suites-v3'
        assert not any(f.is_dir() for f in initial.iterdir())
        for file in ('build.jsonl','build.stderr'): assert sha(initial/file)==sha(p/file)
        selection=load(p/'profile-selection.json')
        assert selection['product_binary']==anchor['declaration']['cargo'] and selection['test_build_binary']!=selection['product_binary']
        assert selection['test_build_binary']==sha(bins['cargo-bin']) and selection['test_build_version_sha256']==anchor['cargo_vv']
        result['build_selection']=selection
        rejected=load(p/'userns-preflight.json')
        prior=arm/'suites-v4/fingerprints'
        assert rejected['prior_exit']==int((prior/'exit').read_bytes())==1
        assert not (prior/'exec.log').exists() and rejected['test_processes']==0
        assert sha(prior/'stdout')==rejected['stdout_sha256'] and sha(prior/'stderr')==rejected['stderr_sha256']
        result['userns_preflight']=rejected
    return result
def collect(base,sources,fixture):
    assert sha(fixture/'SHA256SUMS')=='7bd69adfb38cdf31f300b61679fef88bc60b2530757683d979de384ce144d264'
    for row in (fixture/'SHA256SUMS').read_text().splitlines():
        h,n=row.split(maxsplit=1);assert sha(fixture/n.strip())==h
    parents={}; arms={}; patches={}
    old_fifo=load(base/'branch-special-files.json')
    for n in ('101','103'):
        assert not gas(sources,n,'status','--porcelain')
        assert gas(sources,n,'rev-parse','HEAD').decode().strip()==FIX[n]
        path=gas(sources,n,'diff','--name-only',PRIOR[n],FIX[n]).decode().splitlines(); assert path==[MOD]
        patches['pr'+n+'.patch']=gas(sources,n,'diff','--no-ext-diff',PRIOR[n],FIX[n])
        refs={}
        for role,commit in [('prior',PRIOR[n]),('fixed',FIX[n])]:
            file=gas(sources,n,'show',commit+':'+MOD)
            refs[role]={'commit':commit,'tree':gas(sources,n,'rev-parse',commit+'^{tree}').decode().strip(),
                'parents':gas(sources,n,'show','-s','--format=%P',commit).decode().split(),
                'file_sha256':digest(file),'file_git_blob':gas(sources,n,'rev-parse',commit+':'+MOD).decode().strip(),'file_bytes':len(file)}
        assert refs['fixed']['parents'][0]==refs['prior']['commit']
        parents[n]={**refs,'path':MOD,'patch_sha256':digest(patches['pr'+n+'.patch'])}
        for stage in ('prior','fixed','stamped'):
            arm=base/f'{stage}-{n}'
            a=build(arm,n,stage)
            assert a['declaration']['tree']==refs['prior' if stage=='prior' else 'fixed']['tree']
            fi={}
            for mode in ('default','no-ohm'):
                for variant in (('parent-error','single-fifo') if stage=='stamped' else ('parent-error',)):
                    fr=fifo(base,arm,mode,variant)
                    if stage!='stamped':assert fr['result']==old_fifo[arm.name+'/'+mode]
                    fi[mode+'/'+variant]=fr
            arms[arm.name]={'image':a,'recovery':recovery(arm,a['declaration']['cargo']),'fifo':fi,'suites':suites(arm,stage,a)}
    omitted_mount=base/'fixed-101/suites'
    stop=(omitted_mount/'conditional/stdout').read_text()
    assert 'test result: FAILED. 0 passed; 7 failed;' in stop and 'Read-only file system' in stop
    preflight={'completed_fingerprints':73,'failed_conditional':7,'reason':'read-only harness temporary directory',
               'streams':{s+'/'+n:brief(omitted_mount/s/n) for s in ('fingerprints','conditional') for n in ('stdout','stderr','exec.log')}}
    evid={'source':parents,'arms':arms,'earlier_harness_preflight':preflight,'rustc_sha256':RUSTC,'fixture_manifest':sha(fixture/'SHA256SUMS'),
          'fixture_reproduce':sha(fixture/'reproduce.py'),
          'operators':{n:sha(base/n) for n in ('build.py','build-stamped.py','suites.py','suites-v2.py','suites-stamped.py','suites-stamped-v4.py','suites-stamped-v5.py','branch-fifo-audit.py','run-stamped-controls.py')}}
    return evid,patches

if __name__=='__main__':
    arg=argparse.ArgumentParser();arg.add_argument('raw',type=Path);arg.add_argument('worktrees',type=Path);arg.add_argument('fixture',type=Path);arg.add_argument('destination',type=Path);arg.add_argument('--compare',action='store_true')
    a=arg.parse_args();ev,patches=collect(a.raw,a.worktrees,a.fixture)
    files={'results.json':(json.dumps(ev,indent=2,sort_keys=True)+'\n').encode(),**patches}
    reusable=['reproduce.py',*(str(f.relative_to(a.fixture)) for top in ('fixture','wrapper') for f in sorted((a.fixture/top).rglob('*')) if f.is_file())]
    files['regression/fixture-source.SHA256SUMS']=(a.fixture/'SHA256SUMS').read_bytes()
    for name in reusable:files['regression/'+name]=(a.fixture/name).read_bytes()
    streams={}
    for key,arm in ev['arms'].items():
        if arm['suites'] is None:continue
        sub='suites-v5' if key.startswith('stamped-') else 'suites-v2'
        for cat,case in arm['suites']['sets'].items():
            path=a.raw/key/sub/cat/'stdout'
            assert sha(path)==case['stdout']
            streams[key+'/'+cat]=path.read_text()
    files['suite-stdout.json.gz']=gzip.compress((json.dumps(streams,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0)
    for name,data in files.items():
        p=a.destination/name
        if a.compare:assert p.read_bytes()==data,name
        else:assert not p.exists(),name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(data)
    print('Verified six physical builds, recovered binaries, kernel file controls, source patches and standard suites.')

