"""Rebuild the sealed corpus from an existing Ruff Git checkout, with no network access."""
import argparse,gzip,hashlib,json,subprocess
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--ruff',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);a=parser.parse_args()
P=Path(__file__).resolve().parent;d=json.loads(gzip.decompress((P/'corpus.json.gz').read_bytes()))
a.out.mkdir(parents=True,exist_ok=False)
f=subprocess.Popen(['git','-C',str(a.ruff),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
for row in d['actual_inputs']:
    query=d['ruff']+':'+row['path'];f.stdin.write((query+'\n').encode());f.stdin.flush()
    obj,kind,size=f.stdout.readline().split();assert obj.decode()==row['git'] and kind==b'blob'
    data=f.stdout.read(int(size));assert f.stdout.read(1)==b'\n'
    if row['path']=='crates/ruff_linter/src/rules/ruff/helpers.rs':
        rem=b'/// return `true` if `func` represents a call to `dataclasses.field()`.\n'
        assert data.count(rem)==1;data=data.replace(rem,rem.replace(b'dataclasses.field',b'dataclass.field'))
    assert len(data)==row['size'] and hashlib.sha256(data).hexdigest()==row['sha256']
    (a.out/str(row['file'])).write_bytes(data)
f.stdin.close();assert f.wait()==0;print(len(d['actual_inputs']),'Ruff inputs match')
