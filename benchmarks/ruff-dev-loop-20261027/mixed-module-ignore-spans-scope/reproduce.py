"""Compare the proposed effective ordinary writer to the normal Ohm writer with a fresh reader cache."""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('mode',choices=('ordinary-writer','normal','upstream-ordinary'))
ap.add_argument('directory',nargs='?',type=Path)
args=ap.parse_args()
d=args.directory.resolve() if args.directory else Path(tempfile.mkdtemp(prefix='heterogeneous-spans-'))
d.mkdir(exist_ok=True,parents=True)
assert not any(d.iterdir())
before='pub fn answer()->u8 {17}\n'
(d/'reader.rs').write_text('extern crate input; fn main(){let _=input::answer();}\n')
(d/'error.rs').write_text('extern crate input; fn main(){input::answer(5);}\n')
env=dict(os.environ,RUSTC_BOOTSTRAP='1')
def rustc(argv, label):
    ps=subprocess.run(['rustc','+ohm',*argv],cwd=d,env=env,capture_output=True)
    (d/(label+'.stderr')).write_bytes(ps.stderr)
    print(label,ps.returncode)
    return ps
for stage,txt,cache in [('initial',before,'warm'),('moved',' '*11+before,'warm'),('empty',' '*11+before,'empty')]:
    (d/'input.rs').write_text(txt)
    producer=(['-Zpublic-api-hash'] if args.mode=='normal' else ['-Zincremental-ignore-spans'])
    if args.mode=='ordinary-writer':
        producer.append('-Zpublic-api-hash=no')
    consumer=[] if args.mode=='upstream-ordinary' else ['-Zpublic-api-hash']
    p=rustc(['--crate-type=rlib','--emit=metadata','-Cmetadata=f1','-Cincremental=p-'+cache,*producer,'input.rs'],stage+'-producer')
    assert not p.returncode
    ps=rustc(['--emit=metadata','-Cincremental=r-'+cache,*consumer,'--extern','input=libinput.rmeta','reader.rs'],stage+'-reader')
    if args.mode=='ordinary-writer' and stage=='moved':
        assert ps.returncode==101 and b'incremental compilation error with module_children' in ps.stderr
    else:
        assert ps.returncode==0
    assert rustc(['--emit=metadata','--error-format=json','--extern','input=libinput.rmeta','error.rs'],stage+'-fresh-diagnostic').returncode==1
print(d)
