"""Export integrity-checked QA logs and each real compiler/linker's successful exec line."""
from pathlib import Path
import hashlib,io,json,re,sys,tarfile
fourth=sys.argv[1:]==['--fourth']
assert fourth or not sys.argv[1:]
R=Path('/home/dev-user/.cache/ohm-rc18-final-tools-ruff-20261028' if fourth else '/home/dev-user/.cache/ohm-rc18-r2-whole-ruff-20261028')
root=R/('records-v2' if fourth else 'records');private_id='85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381'
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda f:json.loads(f.read_bytes())
asbytes=lambda x:json.dumps(x,indent=2,sort_keys=True).encode()+b'\n'
if fourth:
    assert (R/'fourth-worker.exit').read_text().strip()=='1' and (R/'fourth-worker-v2.exit').read_text().strip()=='0'
    assert set(read(R/'fourth-complete.json')['stages'])=={'cold','unchanged'} and (R/'failure-v2.txt').exists()
else:
    assert not (R/'failure-v2.txt').exists()
    assert (R/'worker-v2.exit').read_text().strip()=='0' and len(read(R/'complete.json')['records'])==15 and len(read(R/'progress.json'))==15
idx,=[p for p in (R/'states'/('test' if fourth else 'check')/'cargo/registry/index').iterdir() if sha(p.name.encode())==private_id]
key=idx.name.encode(); data={};origins={}
def add(name,raw):
    assert name not in data
    payload=raw.replace(key,b'registry-offline-protected')
    data[name]=payload
    origins[name]={'original_bytes':len(raw),'original_sha256':sha(raw),'portable_sha256':sha(payload),'replaced':raw.count(key)}
for n in ('complete.json','failure.txt','failure-v2.txt','progress.json','launch.json','observation-amendment-v2.json','preservation-protocol-v2.json','final-sdk.json','prepare.done','preservation-protocol.json','actual-loaded.json','actual-loaded-all-segments.json','initial-tools.sha','preflight.stderr','preflight-v2.stderr','worker.stdout','worker.stderr','worker.exit','worker-v2.stdout','worker-v2.stderr','worker-v2.exit','fourth-state.json','fourth-final-sdk.json','fourth-complete.json','fourth-worker.exit','fourth-worker.stdout','fourth-worker.stderr','fourth-worker-v2.exit','fourth-worker-v2.stdout','fourth-worker-v2.stderr','fourth-before-cargo-amendment.json','fourth-v2-observed.out','fourth-v2-observed.err'):
    f=R/n
    if f.is_file():add(n,f.read_bytes())
for p in sorted((R/'protocol').iterdir()):
    if p.is_file():add('protocol/'+p.name,p.read_bytes())
for outer in sorted(root.iterdir()):
    if outer.is_file():continue
    if outer.name.endswith('-version'):
        for p in sorted(outer.iterdir()):
            if p.is_file():add(str(p.relative_to(root)),p.read_bytes())
        continue
    for d in sorted(outer.iterdir()):
        rel=str(d.relative_to(root))
        for n in ('command.json','exit.json','stdout','stderr','result.json','actual-processes.json','retained-links.json'):
            f=d/n
            if f.is_file():add(rel+'/'+n,f.read_bytes())
        for sub in d.iterdir():
            if not sub.is_dir() or sub.name=='trace':continue
            for f in sorted(sub.rglob('*')):
                if not f.is_file() or f.name not in ('argv.json','exit.json','stdout','stderr'):continue
                add(str(f.relative_to(root)),f.read_bytes())
        f=d/'actual-processes.json'
        if f.is_file():
            j=read(f); selected=[]
            for job in j['processes']:
                trace=d/'trace'/('exec.'+str(job['pid']));raw=trace.read_bytes()
                assert sha(raw)==j['raw_trace_sha256'][trace.name]
                line,=[s for s in raw.splitlines() if sha(s)==job['argv_sha256']]
                selected.append({'pid':job['pid'],'kind':job['kind'],'sha256':sha(line),'line':line.decode()})
            add(rel+'/native-exec-lines.json',asbytes(selected))
retained={}
available=R/'native-outputs'
if available.is_dir():
    for f in sorted(available.iterdir()):
        if not f.is_file():continue
        with f.open('rb') as b:actual=hashlib.file_digest(b,'sha256').hexdigest()
        assert actual==f.name and not f.is_symlink()
        retained[f.name]=f.stat().st_size
add('retained-storage.json',asbytes({'physical_verified':True,'objects':retained}))
data['originals.json']=asbytes({'protected_basename_sha256':private_id,'files':origins})
with tarfile.open(mode='w|gz',fileobj=sys.stdout.buffer,compresslevel=6) as t:
    for n,b in sorted(data.items()):
        ent=tarfile.TarInfo(n);ent.size=len(b);ent.mtime=0;t.addfile(ent,io.BytesIO(b))
