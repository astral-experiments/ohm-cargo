from pathlib import Path
import io,json,hashlib,gzip,sys,tarfile,base64
H=Path(__file__).resolve().parent;V=H.parent/'cfg-library-svh-v3-replay-v1';contents={};j=lambda p:json.loads(p.read_bytes())
for fn in ('complete.json','progress.json','failure.txt'):
 if (V/fn).is_file():contents[fn]=(V/fn).read_bytes()
for p in sorted((V/'common').glob('*')):
 if p.is_file():contents['common/'+p.name]=p.read_bytes()
for dp in sorted(V.glob('block-*/*')):
 if not dp.is_dir():continue
 prefix=dp.relative_to(V)
 for p in dp.glob('*/result.json'):contents[str(prefix/p.parent.name/p.name)]=p.read_bytes()
 if (dp/'summary.json').is_file():contents[str(prefix/'summary.json')]=(dp/'summary.json').read_bytes()
 for q in dp.glob('*/compiler.exec'):contents[str(prefix/q.parent.name/q.name)]=q.read_bytes()
 for s in dp.glob('*/stderr'):
  if s.stat().st_size>0:contents[str(prefix/s.parent.name/s.name)]=s.read_bytes()
 if str(prefix).startswith('block-1/'):
  for n in ('chain-edited','empty-edited'):
   f=dp/n/'result.json'
   if f.is_file():
    r=j(f)
    if 'metadata' in r:
     p=dp/n/'artifacts'/r['metadata'];b=p.read_bytes();h=hashlib.sha256(b).hexdigest();assert h==r['metadata_sha256'];contents['raw-rmeta/'+h+'.rmeta']=b
b=io.BytesIO()
with gzip.GzipFile(filename='',fileobj=b,mode='wb',compresslevel=6,mtime=0) as g,tarfile.open(mode='w',fileobj=g) as t:
 for n,z in sorted(contents.items()):
  i=tarfile.TarInfo(n);i.size=len(z);i.mode=0o644;i.mtime=0;t.addfile(i,io.BytesIO(z))
print(base64.b64encode(b.getvalue()).decode())
