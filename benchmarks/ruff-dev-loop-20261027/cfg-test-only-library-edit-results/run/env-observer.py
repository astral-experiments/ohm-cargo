"""Capture only public Cargo package fields for a positive identical-input compiler replay."""
from pathlib import Path
import hashlib,json,os,time
Q=Path.home()/'.cache/ohm-233-position-qualified-20261027/cfg-library-first-v1-campaign';O=Q/'compiler-env-roster';O.mkdir(exist_ok=True);done=set()
while not (Q/'complete.json').is_file() and not any(Q.glob('failure-*.txt')):
 for p in Path('/proc').glob('[0-9]*'):
  if p.name in done:continue
  try:
   b=(p/'cmdline').read_bytes().split(b'\0');i=b.index(b'--crate-name')
   if b[i+1]!=b'ty_ide' or not b[0].endswith(b'/rustc') or b'crates/ty_ide/src/lib.rs' not in b:continue
   e={};env=(p/'environ').read_bytes().split(b'\0')
   for row in env:
    k,s,v=row.partition(b'=')
    if s and (k.startswith(b'CARGO_PKG_') or k in (b'CARGO_MANIFEST_DIR',b'CARGO_MANIFEST_PATH',b'CARGO_CRATE_NAME',b'CARGO_PRIMARY_PACKAGE',b'CARGO_BIN_NAME',b'CARGO_ENCODED_RUSTFLAGS',b'LD_LIBRARY_PATH',b'OUT_DIR',b'OPT_LEVEL',b'PROFILE',b'TARGET',b'HOST',b'CARGO')):e[k.decode()]=v.decode()
   if e.get('CARGO_MANIFEST_DIR')!='/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/crates/ty_ide':continue
   (O/(p.name+'.json')).write_text(json.dumps({'pid':int(p.name),'env':e,'actual_argument_hash':hashlib.sha256(b'\0'.join(b)).hexdigest()},sort_keys=True,indent=1)+'\n');done.add(p.name)
  except (OSError,ValueError,IndexError):pass
 time.sleep(0.4)
