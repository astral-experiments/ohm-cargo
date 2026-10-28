"""Run one prepared namespace's ordinary Ruff command and inspect it only outside the scored endpoint."""
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path(os.environ['CARGO_TARGET_DIR']).parent
study=root/'native-ready-order19'
previous=root/'paired-frontend/functional-ops-v3'
expected_tools={'rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60','stock-wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','gcc':'1b99826121ae6682a634e5efe09bd3e3df58ce58e0b28f849114ab5b89139c26','collect2':'4d1f341ae5b763b513258ee2812422a45e063c30a2f1924a0cf63d3699f3a158'}
cargo_sha={'A':'6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac','B':'419200f1010d167502103a3f1964c937eec8c22ade26a021309718b854363f94'}
command=['cargo','+ohm','test','--workspace','--no-run','--locked','--offline','-j8']
mode,arm,state,cohort,label=sys.argv[1:];assert mode in ('census','warm','clock','plain','oracle') and arm in cargo_sha
assert state in ('original','notebook') and cohort in ('repeat','transition','cold','settle')
assert label and all(c.isalnum() or c in '.-' for c in label)
directory=study/'reports'/label
if mode!='oracle':directory.mkdir()
assert Path.cwd()==root/'source' and Path(os.environ['CARGO_BUILD_BUILD_DIR'])==root/'shared'
assert os.geteuid()==os.getuid()==1000 and Path('/').stat().st_uid==Path('/home').stat().st_uid==0
assert list(map(int,Path('/proc/self/uid_map').read_text().split()))==[0,0,4294967295]
for path in [root/'source',root/'target',root/'shared',root/'cargo']:
    assert all(part.stat().st_uid in (0,1000) for part in [path,*path.parents])
assert not any(n in os.environ for n in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','WILD_LOG'))
assert set(os.sched_getaffinity(0))==set(range(32))

def sha(p):
    with p.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def dump(name,value):
    with (directory/name).open('x') as fd:json.dump(value,fd,sort_keys=True);fd.write('\n')

def read_artifacts():
    with (directory/'cargo.stdout').open('rb') as fd: rows=[json.loads(v) for v in fd]
    assert rows[-1]=={'reason':'build-finished','success':True}
    arts=[r for r in rows if r['reason']=='compiler-artifact'];fresh=sum(r['fresh'] for r in arts)
    assert len(arts)==619
    if cohort!='settle':assert fresh=={'repeat':563,'transition':559,'cold':0}[cohort],(len(arts),fresh,cohort)
    return arts,fresh

def e2e_oracle(arts):
    e2e,=[Path(a['executable']) for a in arts if '/crates/ty_server#' in a['package_id'] and a['target']['name']=='e2e' and a['target']['kind']==['test']]
    assert e2e.is_relative_to(root/'target')
    listed=subprocess.check_output([e2e,'--list','--format','terse'],timeout=60)
    digest=hashlib.sha256(listed).hexdigest();assert len(listed.splitlines())==200 and digest=='e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316'
    cases={};env=dict(os.environ,INSTA_UPDATE='no',NO_COLOR='1',RUST_BACKTRACE='0')
    for case,loc in [('notebook::hover_past_end_of_cell','628'),('notebook::inlay_hints_range_past_end_of_cell','657')]:
        proc=subprocess.run([e2e,'--exact',case,'--test-threads=1','--nocapture'],capture_output=True,timeout=90,env=env)
        assert proc.returncode==(101 if state=='notebook' else 0) and b'199 filtered out' in proc.stdout
        if state=='notebook':assert ('notebook.rs:'+loc+':').encode() in proc.stdout+proc.stderr
        cases[case]={'exit':proc.returncode,'stdout_sha256':hashlib.sha256(proc.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(proc.stderr).hexdigest()}
    return e2e,{'file':e2e.name,'sha256':sha(e2e),'state':state,'listed':200,'listing_sha256':digest,'tests':cases}

if mode=='oracle':
    arts,_=read_artifacts();_,oracle=e2e_oracle(arts);dump('behavior.json',oracle);sys.exit(0)
argv=command+([] if mode=='plain' else ['--message-format=json'])
if mode=='census':
    prep=json.loads((root/'prepared.json').read_bytes());assert sha(root/'source'/prep['file'])==prep['edited_sha256' if state=='notebook' else 'old_sha256']
    status=subprocess.check_output(['git','--no-optional-locks','status','--porcelain','-z']);assert status==(b' M '+os.fsencode(prep['file'])+b'\0' if state=='notebook' else b'')
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='93526150df078af7dd8fc4226cdcc469539d2001'
    sdk=(Path(os.environ['RUSTUP_HOME'])/'toolchains/ohm').resolve();gcc=Path(shutil.which('cc')).resolve();paths={'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','stock-wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd','gcc':gcc,'collect2':Path(subprocess.check_output([gcc,'-print-prog-name=collect2'],text=True).strip()).resolve()}
    images={k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()};assert {k:v['sha256'] for k,v in images.items()}=={'cargo':cargo_sha[arm],**expected_tools}
    if cohort=='cold':assert not list((root/'target').iterdir()) and not list((root/'shared').iterdir())
    dump('image-contract.json',{'images':images})
    tracer=previous/'actual-execs.py'
    if cohort=='repeat':
        tracer=root/'ops/native-order-live-v4.py'
        assert sha(tracer)=='9a54e14116a1ad7a66274d4a772fd59f149e647920d3ee85f870b43c31d0e8e5' and sha(root/'ops/native-order-rss-v4.py')=='d60e4802fb93ff9e89cf126076eaa166741538cb0246e93d4619a2cc0242e3c0'
    argv=[sys.executable,'-IB',tracer,directory/'execs.json',directory/'image-contract.json',*argv]
with (directory/'cargo.stdout').open('xb') as stdout,(directory/'cargo.stderr').open('xb') as stderr:
    start=time.perf_counter_ns();p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=2200);elapsed=time.perf_counter_ns()-start
record={'exit':p.returncode,'stdout_sha256':sha(directory/'cargo.stdout'),'stderr_sha256':sha(directory/'cargo.stderr')}
assert p.returncode==0,(p.returncode,(directory/'cargo.stderr').read_bytes()[-2400:])
if mode!='plain':
    arts,fresh=read_artifacts();record.update(units=len(arts),fresh=fresh)
if mode!='census':
    if mode!='warm':record['wall_ns']=elapsed
    dump('result.json',record);sys.exit(0)
ex=json.loads((directory/'execs.json').read_bytes());events=ex['events'];counts=Counter(v['role'] for v in events);assert ex['root_exit']==0 and counts['cargo']==1
for v in events:
    code=ex['process_exit'][str(v['pid'])]
    if code==0:continue
    assert cohort=='cold' and code==1 and v['role'] in ('gcc','collect2') and (v['out'] in (None,'conftest'))
full=[v['target'] for v in events if v['role']=='rustc-full']
if cohort=='repeat':assert full==['ron'] and all(counts[k]==50 for k in ('rustc-link-only','gcc','collect2','stock-wild'))
if cohort=='transition':assert len(full)==12 and counts['rustc-link-only']==43 and all(counts[k]==52 for k in ('gcc','collect2','stock-wild'))
if cohort=='cold':assert counts['rustc-full']>=619 and counts['stock-wild']>=100
spec=importlib.util.spec_from_file_location('fields',previous/'elf.py');fields=importlib.util.module_from_spec(spec);spec.loader.exec_module(fields)
for v in events:
    if v['role'] in ('rustc-link-only','rustc-full'):
        flags=[a for a in v['argv'] if a.startswith('-Zthreads=')];assert flags==['-Zthreads=8'],(v['target'],flags)
        assert (v['role']=='rustc-link-only')==('-Zlink-only' in v['argv'] or v['argv'][-2:]==['-Z','link-only'])
wilds=[v for v in events if v['role']=='stock-wild']
roster=json.loads((root/'ops/native-order-product-roster.json').read_bytes())['native_output']
assert len(roster['repeat'])==50 and len(roster['transition'])==52
required=set(roster['repeat' if cohort=='repeat' else 'transition'])
outputs={};wild_names=[]
for event in wilds:
    file=Path(event['out']);wild_names.append(file.name)
    if not file.is_absolute() or not file.is_relative_to(root):continue
    relative=str(file.relative_to(root))
    if relative not in required:continue
    assert file.is_file() and relative not in outputs
    outputs[relative]={'size':file.stat().st_size,'sha256':sha(file),'fields':fields.normalize(file)}
assert set(outputs)==required,(cohort,sorted(required-set(outputs)),sorted(set(outputs)-required))
executable,behavior=e2e_oracle(arts);linked,=[root/name for name in outputs if Path(name).name==executable.name];assert os.path.samefile(linked,executable) and outputs[str(linked.relative_to(root))]['sha256']==behavior['sha256']
record.update(cohort=cohort,counts=dict(counts),full=full,source_sha256=sha(root/'source'/prep['file']),execs_sha256=sha(directory/'execs.json'),wild_outputs=sorted(wild_names),products=outputs,behavior=behavior,
              compiler_args=sorted((v['role'],v['target'],v['argv_sha256']) for v in events if v['role'] in ('rustc-full','rustc-link-only')))
if cohort=='repeat':
    import runpy
    compare=root/'ops/native-order-args-v4.py';assert sha(compare)=='8f114ec372cd419e94a5f7e38f40b4667d69d8d04bd826d9b46bdde1c676d9c0'
    assert Path(os.environ['TMPDIR'])==root/'tmp'
    record['native_args']=runpy.run_path(str(compare))['fingerprints'](events,root/'target',root/'tmp')
    memory=ex['memory'];assert memory['samples']
    record['memory']={'max_rss_bytes':max(x[2] for x in memory['samples']),'max_pss_bytes':max(x[3] for x in memory['samples'] if x[3] is not None),'largest_child_kib':max(ex['maxrss_kib'].values())}
dump('result.json',record)
print(cohort,arm,state,len(outputs),counts['stock-wild'],flush=True)
