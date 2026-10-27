"""Export every enrolled Cargo output and physical control without retaining timing-environment credentials."""
from pathlib import Path
import hashlib, io, json, os, socket, subprocess, sys, tarfile
H=Path.home()/'.cache/ohm-233-position-qualified-20261027'
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
A=P/'pr233-time-run-v1';Q=H/'pr233-three-parser-protocol-h5-v2';C=H/'pr233-time-control-v1'
assert socket.gethostname()=='charlie-ohm-loader-perf-1024' and (C/'score.exit').read_text().strip()=='0'
os.sched_setaffinity(0,{28,29});os.nice(5);sys.path.insert(0,str(Q))
from processes import records
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def get(p):return json.loads(p.read_bytes())
complete=get(A/'complete.json')
assert complete['pairs']==96 and complete['ordinary_timed_commands']==192
output=H/'pr233-heldout-timing-results-v1';output.mkdir(mode=0o700)
z=output/'cargo-evidence.tar.zst';docs=('complete','observations','results','references','copied','prepared','post-controls','started','prepare-admission')
receipts=sorted((A/'receipts').rglob('witness.json'))
assert sum(f.relative_to(A/'receipts').parts[0]=='timed' for f in receipts)==192
assert sum(f.relative_to(A/'receipts').parts[0] in ('pre','post') for f in receipts)==48
def info(name, size):
    m=tarfile.TarInfo(name);m.size=size;m.mode=0o644;m.mtime=0
    return m
def bytes_item(t,name,data): t.addfile(info(name,len(data)),io.BytesIO(data))
def file_item(t,name,f):
    with f.open('rb') as stream:t.addfile(info(name,f.stat().st_size),stream)
members=0; no_native_cases=0; native_cases=0
with z.open('xb') as fo:
    compressor=subprocess.Popen(['zstd','-q','-10','-T2','--long=26','--stdout'],stdin=subprocess.PIPE,stdout=fo)
    try:
        with tarfile.open(fileobj=compressor.stdin,mode='w|',format=tarfile.GNU_FORMAT) as stream:
            for n in docs:file_item(stream,'summary/'+n+'.json',A/(n+'.json'));members+=1
            for f in receipts:
                folder=f.parent;rid=folder.relative_to(A/'receipts').as_posix()
                file_item(stream,rid+'/witness.json',f);members+=1
                r=get(f)
                for kind in ('first','immediate'):
                    if kind not in r:continue
                    rec=r[kind];d=folder/kind
                    for name in ('stdout','stderr'):
                        raw=d/name;assert sha(raw)==rec[name+'_sha256'],(rid,name)
                        file_item(stream,rid+'/'+kind+'/'+name,raw);members+=1
                    fullargs=[]
                    if rec['traced']:
                        origin={}
                        for pid,path,args in records(d):
                            if pid not in origin:origin[pid]=sha(d/pid)
                            # Preserve PID, complete image, actual crate/mode tokens and argv hash.
                            # Separately preserve complete original arguments of the crate/Wild job.
                            img=Path(path);relevant=(img.name=='rustc' and '--crate-name' in args) or (img.name=='ld.bfd' and img.parent.name=='wild-ld')
                            fullargs.append([pid,origin[pid],path,args if relevant else None,hashlib.sha256(json.dumps(args,separators=(',',':')).encode()).hexdigest()])
                        assert fullargs
                        native_cases+=1
                    else:assert not list(d.glob('exec.*')) and rid.startswith('timed/') and kind=='first';no_native_cases+=1
                    if fullargs:bytes_item(stream,rid+'/'+kind+'/programs.json',json.dumps(fullargs,separators=(',',':')).encode());members+=1
        compressor.stdin.close();assert compressor.wait()==0
    except BaseException:
        compressor.kill();compressor.wait();raise
assert no_native_cases==192
print(json.dumps({'path':str(z),'sha256':sha(z),'bytes':z.stat().st_size,'selected_files':members,'traced':native_cases,'untraced':no_native_cases,'source_complete':sha(A/'complete.json')}))
