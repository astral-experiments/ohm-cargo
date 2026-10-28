import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

ops=Path('/home/dev-user/.cache/ohm-rc18-final-tools-ops-20261028')
out=ops/'package-smoke-v1'
assert (ops/'package-smoke-v1.exit').read_text().strip()=='0'
checks=json.loads((out/'complete.json').read_bytes())
data={}
for name in ('package-smoke-v1.stdout','package-smoke-v1.stderr','package-smoke-v1.exit','smoke-test-release.sh','package_bytes_smoke.py'):
    data[name]=(ops/name).read_bytes()
for name in ('complete.json','original-stanza.sh','original-fixture.sh','run-package-stanza.sh'):
    data[name]=(out/name).read_bytes()
for case,native in {'package-raw-tmpdir':out/'smoke/byte-path-target/debug/ohm-smoke','library-raw':out/'lib-target-raw/debug/ohm-byte-library','library-unicode-decoy':out/'lib-target-unicode-decoy/debug/ohm-byte-library'}.items():
    for name in ('stdout','stderr','exit','elf-comment','wild-execs','exec.trace'):
        data[case+'/'+name]=(out/case/name).read_bytes()
    data[case+'/native.elf']=native.read_bytes()
    assert hashlib.sha256(data[case+'/native.elf']).hexdigest()==checks['cases'][case]['elf']
for n in ('smoke/crate/Cargo.toml','smoke/crate/Cargo.lock','smoke/crate/src/main.rs','smoke/crate/macros/Cargo.toml','smoke/crate/macros/src/lib.rs','library/Cargo.toml','library/Cargo.lock','library/src/main.rs'):
    data[n]=(out/n).read_bytes()
for raw,tag in [(b'lib-\xff','raw'),(b'lib-\xef\xbf\xbd','unicode-decoy')]:
    with open(os.fsencode(out)+b'/'+raw+b'/libohm_byte_choice.a','rb') as f:data['native-fixture/'+tag+'.a']=f.read()
with tarfile.open(mode='w|gz', fileobj=sys.stdout.buffer) as t:
    for n,raw in sorted(data.items()):
        m=tarfile.TarInfo(n);m.size=len(raw);m.mtime=0;t.addfile(m,io.BytesIO(raw))
