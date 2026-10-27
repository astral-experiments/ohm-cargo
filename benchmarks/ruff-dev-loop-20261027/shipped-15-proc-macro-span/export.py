"""Export the actual command and artifact receipts from the private distribution test on H1."""
from pathlib import Path
import base64,hashlib,json,os,socket,zlib,sys
os.sched_setaffinity(0,{28,29})
r=Path('/dev/shm/ohm-packaged-15-macro-20261027')
assert socket.gethostname()=='charlie-ohm-relink-perf-1024' and (r/'exit').read_text().strip()=='0'
e=r/'fixture-output/evidence'
names={'status.json','stderr','stdout','argv.json','result.json','raw.rmeta','libbridge.rlib','unit-after.rs','unit-before.rs','maker.rs','complete.json','results.json','tools.json'}
files={};apps={}
def sha(f):
    with f.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
for f in sorted(e.rglob('*')):
    if not f.is_file():continue
    rel=f.relative_to(e).as_posix()
    if f.name=='app':apps[rel]={'bytes':f.stat().st_size,'sha256':sha(f)};continue
    assert f.name in names and f.stat().st_size<1_000_000,rel
    files[rel]=base64.b64encode(f.read_bytes()).decode()
assert len(apps)==10 and len([n for n in files if n.endswith('argv.json')])==46
files['native-executables.json']=base64.b64encode((json.dumps(apps,sort_keys=True,indent=2)+'\n').encode()).decode()
sys.stdout.buffer.write(zlib.compress(json.dumps(files,separators=(',',':')).encode(),8))
