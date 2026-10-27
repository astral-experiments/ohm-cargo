"""Unpack only checksum-bound public crate indexes, scripts and this campaign's tool inputs."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,shutil,subprocess,sys,tarfile
label=sys.argv[1];assert label.isidentifier();p=Path('/dev/shm/ohm-ron-nonobserver-mono-20261027-'+label)
assert not p.exists() and shutil.disk_usage(p.parent).free>8*2**30,(p,shutil.disk_usage(p.parent))
p.mkdir();sz=0;seen={}
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as f:
    for member in f:
        name=member.name;rel=PurePosixPath(name)
        assert member.isreg() and not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] in ('inputs','sdk') and name not in seen
        sz+=member.size;assert sz<340*2**20
        dst=p/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        h=hashlib.sha256()
        with f.extractfile(member) as inp, dst.open('xb') as out:
            while b:=inp.read(2**20):out.write(b);h.update(b)
        dst.chmod(member.mode&0o777);seen[name]=h.hexdigest()
m=json.loads((p/'inputs/asset-manifest.json').read_bytes())
assert set(seen)==set(m)|{'inputs/asset-manifest.json'} and all(seen[k]==v for k,v in m.items())
script='run-times.py' if sys.argv[2:]==['timed'] else 'fixture.py';assert not sys.argv[2:] or sys.argv[2:]==['timed']
subprocess.run(['/usr/bin/python3','-B',p/'inputs'/script],check=True,env=dict(os.environ,OHM_SCOPED_FIXTURE_ROOT=str(p)))
