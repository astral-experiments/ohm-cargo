from pathlib import Path
import json,os,sys
root=Path(sys.argv[1]);marker,staged,manifest,lock=(root/x for x in ['target/.cargo-resolve-cache-v1','late/Cargo.toml.incoming','late/Cargo.toml','ws/Cargo.lock'])
def identity(x):
 import hashlib
 s=x.stat()
 return [s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,len(x.read_bytes()),hashlib.sha256(x.read_bytes()).hexdigest()]
assert marker.is_fifo() and staged.is_file() and not manifest.exists() and lock.is_file()
identity_before=identity(lock)
# A successful blocking writer open is an actual read-side rendezvous. Cargo
# opens this marker only after converting the first locked Cargo.lock snapshot.
with open(marker,'wb',buffering=0) as writer:
 assert not manifest.exists()
 os.rename(staged,manifest)
 assert manifest.is_file() and identity(lock)==identity_before
 writer.write(b'intentional-cache-miss\n')
(root/'actor.json').write_text(json.dumps({'lock':identity_before,'manifest_at_release':identity(manifest),'marker':'FIFO','published':True})+'\n')
