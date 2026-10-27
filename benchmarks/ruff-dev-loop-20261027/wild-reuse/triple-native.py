"""Run paired, uninstrumented full Ruff commands after a fixed historical edit on the dedicated devbox."""
import argparse
from collections import Counter
from contextlib import contextmanager
import csv
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import time

P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
RUFF=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027')
PIN='93526150df078af7dd8fc4226cdcc469539d2001'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('name');parser.add_argument('mode',choices=['build','test']);parser.add_argument('patch',type=Path)
parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--seed',type=int,required=True)
parser.add_argument('--parent-driver',type=Path);parser.add_argument('--candidate-driver',type=Path)
parser.add_argument('--parent-wild',type=Path);parser.add_argument('--candidate-wild',type=Path)
parser.add_argument('--shipped-wild',type=Path,required=True)
parser.add_argument('--parser-oracle',action='store_true')
parser.add_argument('--wild-proof',action='store_true',help='Pilot opt-in. Measure proof cost in the candidate, use its event log only in traced qualification.')
parser.add_argument('--wild-observe',action='store_true',help='Only collect a previously enabled Wild verifier’s trace events.')
parser.add_argument('--discovery-only',action='store_true');parser.add_argument('--queue',action='store_true')
parser.add_argument('--only-arm',choices=['parent','candidate'],default='parent')
parser.add_argument('--pilot',action='store_true');parser.add_argument('--no-new-registries',action='store_true')
a=parser.parse_args();assert re.fullmatch(r'[a-z0-9-]+',a.name) and a.patch.is_file() and a.candidate.is_file()
assert a.wild_observe and not (a.wild_proof or a.discovery_only or a.pilot or a.parser_oracle or a.parent_driver)
assert a.shipped_wild.is_file() and a.parent_wild.is_file() and a.candidate_wild.is_file()
guard=(P/'native-measure.lock').open('a');fcntl.flock(guard,fcntl.LOCK_EX|(0 if a.queue else fcntl.LOCK_NB))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*args,data=None):
    return subprocess.check_output(['git','--no-optional-locks','-C',RUFF,*args],input=data)
def dump(path,obj):path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def roster(rows):
    units=[r for r in rows if r.get('reason')=='compiler-artifact'];assert len(units)==(501 if a.mode=='build' else 619)
    result=[];products={}
    for r in units:
        uid=(r['package_id'],r['target']['name'],','.join(r['target']['kind']),r['profile']['test']);result.append(uid)
        if not r['package_id'].startswith('path+'):continue
        for path in map(Path,r['filenames']):
            if path.suffix not in ('','.so'):continue
            with path.open('rb') as s:magic=s.read(4)
            if magic==b'\x7fELF':products['/'.join(path.parts[-4:])]=sha(path)
    return sorted(result),products
assert (P/'warm.rc').read_text().strip()=='0' and git('rev-parse','HEAD').decode().strip()==PIN and not git('status','--porcelain')
canonical=P/'native-target'; cargo=P/'frozen-toolchain/bin/cargo';parent=P/'subjects/parent';assert sha(parent) in ('211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc','13396fe1c6886f41155ac24f507210c7a5f655e5b3279a28f45bf3a5e6bcaf08')
components={'cargo':(cargo,parent,a.candidate)}
assert bool(a.parent_driver)==bool(a.candidate_driver) and bool(a.parent_wild)==bool(a.candidate_wild)
if a.parent_driver:
    (driver,)=list((P/'frozen-toolchain/lib').glob('librustc_driver-*.so'));components['driver']=(driver.resolve(),a.parent_driver,a.candidate_driver)
if a.parent_wild:
    wild=(P/'frozen-toolchain/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd').resolve();components['wild']=(wild,a.parent_wild,a.candidate_wild)
assert all((P/'frozen-toolchain') in dest.parents and left.is_file() and right.is_file() for dest,left,right in components.values())
env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(P/'registry-home'),CARGO_TARGET_DIR=str(canonical),CARGO_BUILD_BUILD_DIR=str(P/'shared'),CARGO_BUILD_JOBS='8',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0',SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs')
assert not [k for k in env if k.startswith('WILD_')]
command=['taskset','-c','0-23','cargo','+ohm',a.mode,*(['--no-run'] if a.mode=='test' else []),'--locked','--offline']
patch=a.patch.read_bytes();names=[x.split(b'\t',2)[2].decode() for x in git('apply','--numstat','-',data=patch).splitlines()];assert all(n.startswith('crates/') for n in names);git('apply','--check','--reverse','-',data=patch)
if a.parser_oracle:assert sha(a.patch)=='08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff'
originals={n:((RUFF/n).read_bytes(),(RUFF/n).stat()) for n in names};index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip());index_sha=sha(index)
out=P/('results-'+a.name);out.mkdir()
arms_to_run=('shipped','parent','candidate')
order=list(itertools.permutations(arms_to_run))*3;random.Random(a.seed).shuffle(order)
subjects={k:{'parent':sha(l),'candidate':sha(r),'shipped':sha(a.shipped_wild if k=='wild' else l)} for k,(_,l,r) in components.items()}
assert len(set(subjects['cargo'].values()))==1 and len(set(subjects['wild'].values()))==3
assert subjects['wild']['shipped']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert subjects['wild']['parent']=='1079dffdaee2bc9f81a8aebd800339fdbc3922c08c31cb319c7cc70cec2bb76b'
dump(out/'plan.json',dict(seed=a.seed,orders=order,mode=a.mode,command=command,edit_sha=sha(a.patch),subjects=subjects,pin=PIN,planned_blocks=len(order)))
@contextmanager
def edited():
    assert not git('status','--porcelain');git('apply','--reverse','--whitespace=nowarn','-',data=patch)
    try:yield
    finally:
        for name,(data,st) in originals.items():
            f=RUFF/name;f.write_bytes(data);f.chmod(st.st_mode & 0o777);os.utime(f,ns=(st.st_atime_ns,st.st_mtime_ns))
        assert not git('status','--porcelain') and sha(index)==index_sha
@contextmanager
def active(arm):
    snap=out/('target-'+arm);holder=out/'original-target';assert not holder.exists() and canonical.is_dir()
    saved=[];mounted=False;parked=False
    try:
        for key,(dest,left,right) in components.items():
            restore=out/('original-'+key);assert not restore.exists()
            subject=right if arm=='candidate' else a.shipped_wild if arm=='shipped' and key=='wild' else left
            if key=='cargo':
                os.link(dest,restore);saved.append((dest,restore));incoming=dest.with_name('incoming-'+key);assert not incoming.exists();os.link(subject,incoming);incoming.replace(dest)
                if incoming.exists():incoming.unlink()
            else:
                # Keep the observed driver/linker file's ctime stable across arm changes.
                store=P/'frozen-toolchain'/'.bench-components';store.mkdir(exist_ok=True)
                digest=sha(subject);fixed=store/(key+'-'+digest)
                if not fixed.exists():shutil.copy2(subject,fixed);fixed.chmod(0o555)
                assert sha(fixed)==digest
                dest.rename(restore);saved.append((dest,restore));dest.symlink_to(fixed)
        canonical.rename(holder);parked=True
        snap.rename(canonical);mounted=True
        yield
    finally:
        if mounted:canonical.rename(snap)
        if parked:holder.rename(canonical)
        for dest,restore in reversed(saved):
            restore.replace(dest)
            if restore.exists():restore.unlink()
def invoke(arm,label,verify=False,trace=False,fresh_only=False):
    d=out/(arm+'-'+label);d.mkdir();argv=command.copy()
    if verify or fresh_only:argv+=['--message-format=json']
    if trace:argv=['strace','-ff','-qq','-s','2000','-e','trace=execve','-o',str(d/'exec'),*argv]
    assert shutil.disk_usage(P).free>24*1024**3 and sha(index)==index_sha
    run_env=env.copy()
    if a.wild_proof and arm=='candidate':run_env['WILD_REUSE_OUTPUT']='1'
    if trace and (a.wild_observe or a.wild_proof) and arm=='candidate':run_env['WILD_REUSE_LOG']=str(d/'wild-events.tsv')
    with (d/'stdout').open('wb') as stdout,(d/'stderr').open('wb') as stderr:
        start=time.monotonic_ns();res=subprocess.run(argv,env=run_env,cwd=RUFF,stdout=stdout,stderr=stderr);elapsed=time.monotonic_ns()-start
    log=(d/'stderr').read_text();assert res.returncode==0 and 'Blocking waiting' not in log,(d,log[-1200:]);result={'ns':elapsed}
    if a.no_new_registries and label!='settle':assert not [l for l in log.splitlines() if l.lstrip().startswith('Compiling ') and '/ruff-ohm-whole-native-' not in l],d
    if fresh_only:
        rows=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines() if l.startswith(b'{')]
        units=[r for r in rows if r.get('reason')=='compiler-artifact'];assert len(units)==(501 if a.mode=='build' else 619)
        result['fresh']=sum(r['fresh'] for r in units);result['dirty']=[r['target']['name'] for r in units if not r['fresh']]
        dump(d/'receipt.json',result);assert not result['dirty'],(d,result['dirty'])
    if verify:
        rows=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines() if l.startswith(b'{')]
        units,elf=roster(rows);dirty=[(r['package_id'],r['target']['name'],r['target']['kind']) for r in rows if r.get('reason')=='compiler-artifact' and not r['fresh']]
        result.update(roster_sha=hashlib.sha256(json.dumps(units).encode()).hexdigest(),elf=elf,dirty=dirty)
        if a.parser_oracle:
            (ruff,)=set(r['executable'] for r in rows if r.get('reason')=='compiler-artifact' and r['target']['name']=='ruff' and r['target']['kind']==['bin'] and not r['profile']['test'] and r['executable'])
            sample=b"t'first' b'second'\n";cmd=[ruff,'check','--isolated','--no-cache','--target-version','py314','--output-format','json','-']
            actual=subprocess.run(cmd,input=sample,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=RUFF,env=env);assert actual.returncode==1 and not actual.stderr
            diagnostics=json.loads(actual.stdout);messages=[d['message'] for d in diagnostics]
            if 'edit' in label:assert 'Bytes literal cannot be mixed with non-bytes literals' in messages,messages
            else:assert messages==['Cannot mix t-string literals with string or bytes literals'],messages
            result['parser_diagnostics']=diagnostics
    if trace:
        calls=Counter();compile=[]
        for t in d.glob('exec.*'):
            for line in t.read_text(errors='replace').splitlines():
                m=re.search(r'execve\("([^"]+)"',line)
                if not m or not line.rstrip().endswith('= 0'):continue
                exe=Path(m[1]);name=exe.name
                if name=='rustc' and (c:=re.search(r'"--crate-name", "([^" ]+)"',line)) and c[1]!='___':kind='rustc_link_only' if re.search(r'"(?:-Z)?link-only"',line) else 'rustc_full';calls[kind]+=1;compile.append([kind,c[1]])
                if name=='ld.bfd' and exe.parent.name=='wild-ld':calls['wild']+=1
        result.update(processes=dict(calls),crates=sorted(compile))
        if a.wild_proof or a.wild_observe:
            log=d/'wild-events.tsv';lines=log.read_text().splitlines() if log.exists() else []
            records=[l.split('\t') for l in lines]
            assert all(len(r)==3 and r[0] in ('hit','miss') and re.fullmatch('[0-9a-f]{64}',r[1]) and r[2] for r in records)
            assert len({r[2] for r in records})==len(records)
            events=Counter(r[0] for r in records);assert events['hit']<=calls['wild']
            result.update(wild_events=dict(events),full_links=calls['wild']-events['hit'])
    dump(d/'receipt.json',result);return result
with guard:
    assert sha(cargo)==sha(parent)
    for arm in arms_to_run:
        subprocess.run(['cp','-a','--reflink=auto',canonical,out/('target-'+arm)],check=True)
        with active(arm):
            invoke(arm,'settle')
            if a.wild_proof or a.wild_observe:
                with edited():invoke(arm,'train-edit')
                invoke(arm,'train-restore')
            first=invoke(arm,'before',True);assert not first['dirty']
            with edited():
                changed=invoke(arm,'verify-edit',True,True);assert changed['roster_sha']==first['roster_sha']
                invoke(arm,'after-edit-fresh',fresh_only=True)
            invoke(arm,'restore-discovery')
    with (out/'observations.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['pair','order','arm','elapsed_ns'])
        for i,arms in enumerate(order,1):
            for arm in arms:
                with active(arm):
                    with edited():
                        res=invoke(arm,f'pair-{i:02}');writer.writerow([i,'/'.join(arms),arm,res['ns']]);f.flush()
                        invoke(arm,f'pair-{i:02}-edit-fresh',fresh_only=True)
                    invoke(arm,f'restore-{i:02}')
            print(i,arms,flush=True)
    for arm in arms_to_run:
        with active(arm):
            with edited():
                invoke(arm,'verify-final-edit',True,True)
                invoke(arm,'final-edit-fresh',fresh_only=True)
            invoke(arm,'final-restore');final=invoke(arm,'final-fresh',True);assert not final['dirty']
    dump(out/'complete.json',dict(index_sha256=sha(index),pin=PIN,source_clean=not bool(git('status','--porcelain'))))
