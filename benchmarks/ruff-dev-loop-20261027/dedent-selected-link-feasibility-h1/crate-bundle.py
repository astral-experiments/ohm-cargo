"""Verify package-mode locked inputs and collect their original immutable archives."""
from pathlib import Path
import hashlib,json,subprocess,tomllib,tarfile,urllib.request,io
p=Path(__file__).resolve().parent
repo=Path('/home/dev-user/code/oss/wild-ohm-output-20261023')
lock=tomllib.loads(subprocess.check_output(['git','-C',repo,'show','e856d81f:Cargo.lock']).decode())
pk={e['name']+'-'+e['version']:e for e in lock['package'] if e.get('source','').startswith('registry+')}
roots=[Path('/home/dev-user/.cargo/registry/cache'),Path('/home/dev-user/.cache/ohm-ruff-loop-20261026/registry-home/registry/cache')]
cached={}
for root in roots:
 for f in root.glob('*/*.crate'):
  if f.stem in pk:cached.setdefault(f.stem,f)
dest=p/'vendor-crates.tar'
with tarfile.open(dest,'x') as tar:
 for name,e in sorted(pk.items()):
  if name in cached:data=cached[name].read_bytes()
  else:
   url='https://static.crates.io/crates/'+e['name']+'/'+name+'.crate'
   with urllib.request.urlopen(url,timeout=15) as src:data=src.read()
  assert hashlib.sha256(data).hexdigest()==e['checksum'],name
  info=tarfile.TarInfo(name+'.crate');info.size=len(data);tar.addfile(info,io.BytesIO(data))
print(len(pk),dest.stat().st_size,hashlib.file_digest(dest.open('rb'),'sha256').hexdigest())
