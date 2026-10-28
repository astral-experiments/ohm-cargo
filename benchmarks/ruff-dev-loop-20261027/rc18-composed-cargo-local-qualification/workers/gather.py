"""Read selected source-bound H2 correctness records; retain every native phase and trace digest."""
import hashlib, io, json, os, re, sys, tarfile
from pathlib import Path
mode=sys.argv[1]
assert mode in ('dev','pgo')
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028'); S=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
ROOT=Path('/home/dev-user/.cache'); BASE=ROOT/'ohm-ron-consumed-cargo-20261028'; G=BASE/'rc18-composed'; P=BASE/'rc18-pgo'
rc=mode=='pgo';d=P if rc else G
image=(Path('/mnt/devbox-scratch/dev-user/ohm-rc18-pgo-qualification-20261028/cargo') if rc else X/'target-rc18-composed/debug/cargo')
F=Path('/dev/shm/ohm-ron-derive-checked-suite-20261028')
H=ROOT/'ohm-rc18-testsuite-20261028'
trace=P/'traces' if rc else H
current=ROOT/'ohm-rc18-current-epoch-20261028'
mig=ROOT/('ohm-rc18-pgo-retained-includes-20261028' if rc else 'ohm-rc18-retained-includes-current-epoch-20261028')
typed=(P/'typed' if rc else G/'typed-check')/'status'
dep=ROOT/('ohm-rc18-pgo-output-dep-20261028' if rc else 'ohm-rc18-cargo-output-dep-exact-20261028')
tag='rc18-pgo' if rc else 'rc18'
sha=lambda b:hashlib.sha256(b).hexdigest()
def filehash(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record_bytes(data):return json.dumps(data,sort_keys=True,indent=2).encode()+b'\n'
read=lambda p:json.loads(p.read_bytes())
items={}
def put(name,data):
    assert name not in items
    items[name]=data.read_bytes() if isinstance(data,Path) else data
def copy(src,dst,names):
    if isinstance(names,str):names=names.split()
    for n in names:
        p=src/n
        if p.is_file():put(dst+'/'+n,p)
def active_trace(folder,name):
    rustc=X/'joins/rustup/toolchains/ohm/bin/rustc'
    assert rustc.samefile(S/'bin/rustc')
    cases={};cargos=[];files={}
    for f in sorted(folder.glob(name+'.exec.*')):
        b=f.read_bytes();files[f.name]=sha(b)
        for l in b.decode().splitlines():
            if not l.endswith('= 0'):continue
            m=re.match(r'execve\("([^"]+)"',l)
            if not m:continue
            exe=m[1]
            if exe==str(F/'target/debug/cargo'):cargos.append({'pid':int(f.suffix[1:]),'line':l})
            if exe!=str(rustc) or '"--crate-name", "integration"' not in l:continue
            target=re.search(r'"--out-dir", "([^"]+)"',l)[1]
            case=target.split('/'+name+'/')[-1].split('/target/')[0]
            assert '/' not in case and '"tests/integration.rs"' in l
            cases.setdefault(case,[]).append({'pid':int(f.suffix[1:]),'line':l})
    assert len(cargos)==(14 if 'default_and' in name else 41),len(cargos)
    return {'rust_cases':cases,'cargo_processes':cargos,'trace_file_sha256':files,'exact_rustc_sha256':filehash(rustc),'exact_cargo_sha256':filehash(image)}
for f in ('early_native_integration_tests_default_and_fallback','early_native_integration_tests_warm_evidence_and_fallback','generate_good_d_files','ohm_defaults_reexpand_derive_after_native_input_changes'):
    copy(d,'suite',[f+'.out',f+'.exit'])
    if f.startswith('early_native'):put('suite/'+f+'.trace.json',record_bytes(active_trace(trace,f)))
if rc:
    copy(P,'build','pgo-source.json')
else:
    keep='build.err build.out rc18-dev.sha build.sh changed-inputs.sha lib-depinfo.out lib-depinfo-exact.out lock-fork.raw lock-fork.out pty-composed.out pty-composed.exit pty-composed.sha pty-released.out pty-released.exit pty-released.sha terminal_cancellation_restores_the_shell_and_stops_descendants.exit terminal_cancellation_restores_the_shell_and_stops_descendants.out suite.log'
    copy(G,'build',keep)
    files=['suite-build.jsonl','suite-build.err','lib-build.jsonl','lib-build.err','source.tgz']
    put('build/original-files.json',record_bytes({n:{'size':(G/n).stat().st_size,'sha256':filehash(G/n)} for n in files}))
    # Preserve both old-context fixture rejections and first incorrect Make-path assertion.
    copy(G,'earlier','include.out include-v2.out public-dep.out')
    old=ROOT/'ohm-rc18-cargo-output-dep-20261028/qc/built'
    copy(old,'earlier/expected-rendered-path','consumer.d cargo.jsonl stderr')
    for i,s in enumerate(['ohm-rc18-retained-includes-20261028','ohm-rc18-retained-includes-original-path-20261028']):
        dir=next((ROOT/s).glob('trained-*/before'))
        copy(dir,'earlier/historic-slot-'+str(i),'cargo.jsonl stderr worker.stderr program')
direct=X/('natural-managed-'+tag);a17=X/('migrate-natural-'+tag+'-from17');a261=X/('migrate-natural-'+tag+'-from261')
for name,path in [('direct',direct),('from17',a17),('from261',a261)]:
    r=read(path/'complete.json');copy(path,'derive/'+name,'complete.json packages.json')
    for phase in r['rows']:
        dest='derive/'+name+'/'+phase
        copy(path/phase,dest,'row.json out err encoded.bin rustc.d expected-cargo cargo.sha')
        traces=list((path/phase).glob('exec.*'));assert traces
        raw={f.name:filehash(f) for f in traces}
        true=[{'pid':int(f.suffix[1:]),'line':l} for f in traces for l in f.read_text().splitlines() if l.endswith(' = 0') and ('"--crate-name",' in l or '"/bin/cargo"' in l or '/bin/cargo"' in l)]
        put(dest+'/physical.json',record_bytes({'trace_file_sha256':raw,'selected_execs':true}))
inc=read(mig/'complete.json');assert len(inc)==6
for kind in inc:
    p=mig/kind;old=current/kind
    copy(old,'includes/'+kind,'report.json')
    copy(old/'again','includes/'+kind+'/official-again','cargo.jsonl stderr program')
    copy(old/'clean','includes/'+kind+'/official-empty','cargo.jsonl stderr program')
    for phase in ('before','first','second','empty'):
        copy(p/phase,'includes/'+kind+'/'+phase,'cargo.jsonl stderr exec program row.json encoded.bin rustc.d worker.stderr')
    copy(p/'state/warm/target/debug','includes/'+kind+'/actual-warm','hold_direct.d')
    copy(p/'independent/target/debug','includes/'+kind+'/actual-empty','hold_direct.d')
for stamp in ('current','preserved'):
    p=typed/('rmeta-'+stamp);base='typed/'+stamp
    copy(p,base,'complete.json origins.json old-rmeta-root.txt new-rmeta-root.txt source-17.rs source-29.rs original-product replacement')
    r=read(p/'complete.json')
    for phase in r['rows']:
        copy(p/phase,base+'/'+phase,'stderr stdout result.json rustc.d cargo.fingerprint')
for arm in ('qc','rc'):
    for phase in ('built','regenerated','unchanged'):
        copy(dep/arm/phase,'depfiles/'+arm+'/'+phase,'row.json cargo.jsonl stderr consumer.d exec')
facts={'mode':mode,'cargo':filehash(image),'frontend':filehash(S/'bin/rustc'),'driver':filehash(next((S/'lib').glob('librustc_driver*.so'))),'suite_executable':filehash(H/Path((G/'suite.exe').read_text().strip()).relative_to(F)),'lib_executable':filehash(H/Path((G/'lib.exe').read_text().strip()).relative_to(F))}
put('subjects.json',record_bytes(facts))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',compresslevel=9) as t:
    for k,v in sorted(items.items()):
        m=tarfile.TarInfo(k);m.mode=0o644;m.size=len(v);t.addfile(m,io.BytesIO(v))
