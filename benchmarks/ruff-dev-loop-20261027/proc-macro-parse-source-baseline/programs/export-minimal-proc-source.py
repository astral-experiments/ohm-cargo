"""Archive baseline inputs and actually run commands; retain large native files by SHA-256."""
from pathlib import Path
import hashlib,gzip,json,shutil,sys
base=Path(sys.argv[1]);out=Path(sys.argv[2]);src=Path(sys.argv[3]);pairs=[p.split('=',1) for p in sys.argv[4:]]
out.mkdir(mode=0o700)
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def put(f,d):
    d=out/d;d.parent.mkdir(exist_ok=True,parents=True);assert not d.exists();d.write_bytes(f.read_bytes())
for name in ('minimal-proc-source-hash.py','minimal-proc-source-hash-v2.py','minimal-transient-positions.py','minimal-transient-positions-v2.py','export-minimal-proc-source.py'):
    f=src/name
    if f.is_file():put(f,Path('programs')/name)
for label,name in pairs:
    study=base/name;d=Path(label);files={}
    for f in [*sorted((study/'evidence').rglob('*')),*sorted((study/'workspace').rglob('*'))]:
        if not f.is_file():continue
        rel=f.relative_to(study)
        if f.suffix=='.rlib' or f.name=='app':
            files[str(rel)]={'sha256':sha(f),'bytes':f.stat().st_size}
            continue
        assert f.stat().st_size<500000,f
        put(f,d/rel)
    (out/d/'product-digests.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n')
