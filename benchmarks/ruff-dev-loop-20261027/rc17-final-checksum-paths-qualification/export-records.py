"""Emit only command receipts, explicit small fixture inputs and trace files from named study roots."""
from pathlib import Path
import gzip,hashlib,io,json,os,sys,tarfile
root=Path(sys.argv[1]);dirs=sys.argv[2:];found={};unchecked=[]
for name in dirs:
 p=root/name
 if not p.exists():raise FileNotFoundError(p)
 for dp,ds,fs in os.walk(p):
  for sub in list(ds):
   if sub in {'active-sdk','rustup','target','shared','empty-shared','empty-target','clean-target','clean-shared','cargo-home','home','.git','warm','cold'}:ds.remove(sub)
  for n in fs:
   f=Path(dp)/n
   if f.is_symlink():continue
   if n in {'exec','native','fingerprint','rustc.d','encoded','stdout.jsonl','stderr','stdout','complete','suite.failures','source-map','binary_file','Cargo.toml','Cargo.lock','expected.d'} or f.suffix in {'.json','.log','.rc','.rs','.d','.version','.argv','.syscalls','.stderr','.stdout'}:
    rel=str(f.relative_to(root))
    if f.stat().st_size > 20*2**20:raise ValueError((rel,f.stat().st_size))
    found[rel]=f
assert found
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0,compresslevel=5) as gz:
 with tarfile.open(fileobj=gz,mode='w|') as arc:
  for name,fn in sorted(found.items()):
   info=tarfile.TarInfo(name);info.size=fn.stat().st_size;info.mode=0o644
   with fn.open('rb') as fp:arc.addfile(info,fp)
print(len(found),sum(f.stat().st_size for f in found.values()),file=sys.stderr)
