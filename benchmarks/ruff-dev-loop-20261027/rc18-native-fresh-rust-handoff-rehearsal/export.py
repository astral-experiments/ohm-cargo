"""Select exact logs, literal child argv and program bodies for the isolated local five-crate witness."""
import gzip,hashlib,io,json,os,stat,sys,tarfile
from pathlib import Path
r=Path(__file__).resolve().parent; label=sys.argv[1];w=r/label;rows=json.loads((w/'reports/all.json').read_bytes()); data={}
def add(n,b):
 if n in data:raise ValueError(n)
 data[n]=b
def h(b):return hashlib.sha256(b).hexdigest()
for f in ['witness.py','launch.py','export.py',label+'.binding.json',label+'.terminal.json',label+'.stdout',label+'.stderr','input.sha']:
 add('host/'+f,(r/f).read_bytes())
for f in (w/'source').rglob('*'):
 if f.is_file():add('project/'+str(f.relative_to(w/'source')),f.read_bytes())
for n,j in rows.items():
 dest=w/'reports'/n
 for f in ['trace.private','stderr','stdout','structured.json']:
  add('commands/'+n+'/'+f,(dest/f).read_bytes())
 for f in (w/'launches'/n).glob('*.json'):add('handshake/'+n+'/'+f.name,f.read_bytes())
for n in ['higher','restored']:
 root=w/('target-'+n+'gold');exsha=rows[n+'gold']['final_file'];matches=[]
 for folder in [root,w/('shared-'+n+'gold')]:
  for f in folder.rglob('reader_case-*'):
   if f.is_file() and not f.is_symlink() and os.access(f,os.X_OK):
    b=f.read_bytes()
    if b.startswith(b'\x7fELF') and h(b)==exsha:matches.append(b)
 assert matches,n
 add('abi/'+n+'.elf',matches[0])
add('checked.json',(w/'reports/qualified.json').read_bytes());add('artifacts.json',json.dumps({n:h(b) for n,b in data.items()},sort_keys=True,indent=2).encode()+b'\n')
with (r/(label+'-selected.tar.gz')).open('xb') as stream:
 with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as gz:
  with tarfile.open(fileobj=gz,mode='w') as t:
   for n,b in sorted(data.items()):
    ent=tarfile.TarInfo(n);ent.mode=0o644;ent.mtime=0;ent.size=len(b);t.addfile(ent,io.BytesIO(b))
print(len(data),h((r/(label+'-selected.tar.gz')).read_bytes()),(r/(label+'-selected.tar.gz')).stat().st_size)
