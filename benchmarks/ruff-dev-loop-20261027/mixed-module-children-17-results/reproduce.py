"""Reproduce the ordinary mixed-library workspace failure using the active Ohm toolchain."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('directory', nargs='?', type=Path)
parser.add_argument('--expect', choices=['parent', 'fixed'], required=True)
args = parser.parse_args()
root = args.directory.resolve() if args.directory else Path(tempfile.mkdtemp(prefix='module-children-'))
root.mkdir(parents=True, exist_ok=True)
assert not any(root.iterdir()), root
src = root / 'source'
for crate in ('input', 'reader'):
    (src / crate / 'src').mkdir(parents=True)
(src/'Cargo.toml').write_text('[workspace]\nmembers=["input","reader"]\nresolver="2"\n')
(src/'input/Cargo.toml').write_text('[package]\nname="input"\nversion="0.1.0"\nedition="2024"\n[lib]\ncrate-type=["rlib","cdylib"]\n')
(src/'reader/Cargo.toml').write_text('[package]\nname="reader"\nversion="0.1.0"\nedition="2024"\n[dependencies]\ninput={path="../input"}\n')
(src/'reader/src/main.rs').write_text('fn main(){println!("{}",input::answer());}\n')
(src/'input/src/other.rs').write_text('pub fn number()->u8{29}\n')
lib = src/'input/src/lib.rs'
env = {k: v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTC_BOOTSTRAP'))}
for d in ('cargo','target','build'):
    (root/d).mkdir()
env.update(CARGO_HOME=str(root/'cargo'), CARGO_TARGET_DIR=str(root/'target'), CARGO_BUILD_BUILD_DIR=str(root/'build'))
# Resolve the rustup proxy before changing CARGO_HOME.
cargo = ['cargo','+ohm','build','--workspace','--offline','--quiet']
def run(label):
    x = subprocess.run(cargo, cwd=src, env=env, capture_output=True)
    (root/(label+'.stderr')).write_bytes(x.stderr)
    v = subprocess.check_output([root/'target/debug/reader'], text=True).strip() if not x.returncode else None
    row = (x.returncode, v, b'incremental compilation error with module_children(input[' in x.stderr)
    print(json.dumps([label,*row]), flush=True)
    return row
lib.write_text('pub fn answer()->u8{17}\n')
assert run('original') == (0, '17', False)
lib.write_text('mod other; pub fn answer()->u8{other::number()}\n')
assert run('edited') == ((101,None,True) if args.expect == 'parent' else (0,'29',False))
(root/'target').rename(root/'warm-target')
(root/'build').rename(root/'warm-build')
assert run('empty-edited') == (0,'29',False)
(src/'input/src/other.rs').write_text('pub fn number()->u8{31}\n')
assert run('private-body-edit') == (0,'31',False)
print(root)
