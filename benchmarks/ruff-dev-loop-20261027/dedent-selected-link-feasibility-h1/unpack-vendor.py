"""Extract previously matched crates into a fresh directory source for an offline experiment."""
from pathlib import Path
import hashlib,json,tarfile,tomllib
w=Path(__file__).resolve().parent
p=w/'vendor';p.mkdir()
lock=tomllib.loads((w/'source/Cargo.lock').read_text())
rows={r['name']+'-'+r['version']:r['checksum'] for r in lock['package'] if r.get('source','').startswith('registry+')}
for name,expected in sorted(rows.items()):
 archive=w/'archives'/(name+'.crate');assert hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()==expected,name
 with tarfile.open(archive,'r:gz') as t:
  for e in t.getmembers():
   assert e.name.startswith(name+'/') and not e.name.startswith('/') and '..' not in Path(e.name).parts and (e.isfile() or e.isdir()),e.name
  t.extractall(p,filter='data')
 crate=p/name
 content={str(f.relative_to(crate)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in crate.rglob('*') if f.is_file() and f.name!='.cargo-checksum.json'}
 (crate/'.cargo-checksum.json').write_text(json.dumps(dict(files=content,package=expected),separators=(',',':')))
print('verified',len(rows),'packages')
