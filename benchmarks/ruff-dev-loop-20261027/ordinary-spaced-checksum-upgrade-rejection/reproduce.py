"""Run the ordinary include checksum control on a linked Ohm installation using only Python and rustup."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--toolchain',default='ohm',help='rustup name for the installed Ohm release under test')
parser.add_argument('--keep',type=Path,help='new path at which to keep the two temporary projects and command outputs')
args=parser.parse_args()
if os.name!='posix':
    parser.error('The neighboring filename in this control uses a literal Unix backslash.')

def run(root,mode):
    w=root/mode
    (w/'src').mkdir(parents=True)
    (w/'Cargo.toml').write_text('[package]\nname="byte_reader"\nversion="0.1.0"\nedition="2024"\n[workspace]\n')
    actual=w/'input space/value.bin'
    other=w/('input'+chr(92)+' space')/'value.bin'
    actual.parent.mkdir();other.parent.mkdir()
    before=bytes([17,255,0,254]);after=bytes([29,255,0,254])
    actual.write_bytes(before);other.write_bytes(after)
    source='const INPUT: &[u8] = include_bytes!("../input space/value.bin");\n'
    if mode=='check':source+='const _: [(); 17] = [(); INPUT[0] as usize];\n'
    (w/'src/main.rs').write_text(source+'fn main() { println!("{}", INPUT[0]); }\n')
    outputs={}
    def command(label,clean=False):
        e=os.environ.copy()
        for key in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_LOG',
                    'CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST'):
            e.pop(key,None)
        prefix='cold-' if clean else ''
        e.update(CARGO_TARGET_DIR=str(w/(prefix+'target')),CARGO_BUILD_BUILD_DIR=str(w/(prefix+'shared')),
                 CARGO_HOME=str(w/'cargo-home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',CARGO_TERM_COLOR='never')
        c=subprocess.run(['cargo','+'+args.toolchain,mode,'--offline','-j2','--message-format=json'],
                         cwd=w,env=e,capture_output=True)
        (w/(label+'.stdout')).write_bytes(c.stdout);(w/(label+'.stderr')).write_bytes(c.stderr)
        rows=[json.loads(b) for b in c.stdout.splitlines()]
        if not rows or rows[-1].get('reason')!='build-finished':
            raise RuntimeError(c.stderr.decode(errors='replace')[-1800:])
        arts=[v for v in rows if v['reason']=='compiler-artifact']
        program=None
        if mode=='build' and c.returncode==0:
            art,=arts
            program=int(subprocess.check_output([art['executable']]))
        errors=[v['message']['code']['code'] for v in rows if v['reason']=='compiler-message' and v['message'].get('code') and v['message']['level']=='error']
        outputs[label]={'code':c.returncode,'fresh':[v['fresh'] for v in arts],'program':program,'errors':errors}
    command('initial');command('unchanged')
    saved=actual.stat()
    actual.write_bytes(after);os.utime(actual,ns=(saved.st_atime_ns,saved.st_mtime_ns))
    assert actual.stat().st_size==saved.st_size and actual.stat().st_mtime_ns==saved.st_mtime_ns
    command('changed')
    other.unlink()
    command('clean',True)
    assert outputs['initial']['code']==0
    if mode=='build':assert outputs['initial']['program']==17 and outputs['clean']['program']==29
    else:assert outputs['clean']['code']!=0 and 'E0308' in outputs['clean']['errors']
    return outputs

def main(base):
    print(json.dumps({m:run(base,m) for m in ('build','check')},indent=2))
if args.keep:
    base=args.keep.resolve();base.mkdir(mode=0o700)
    main(base)
else:
    with tempfile.TemporaryDirectory(prefix='ohm-ordinary-checksum-') as td:main(Path(td))
