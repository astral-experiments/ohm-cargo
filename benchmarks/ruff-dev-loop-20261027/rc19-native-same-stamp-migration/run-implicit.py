"""Run the same-stamp implicit libgcc_s transition in a private Linux mount namespace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('old_sdk',type=Path)
parser.add_argument('replacement_sdk',type=Path)
parser.add_argument('new_directory',type=Path)
parser.add_argument('poison',choices=('valid','malformed'))
parser.add_argument('--cpus')
options = parser.parse_args()
if options.cpus:
    os.sched_setaffinity(0,{int(x) for x in options.cpus.split(',')})
assert os.geteuid()!=0 and platform.machine()=='x86_64' and sys.platform=='linux'
here=Path(__file__).resolve().parent
source=Path('/usr/lib/gcc/x86_64-linux-gnu/13/libgcc_s.so')
assert source.is_file() and not source.is_symlink() and source.stat().st_uid==0
def identity(path):
    stat=path.stat()
    return (stat.st_dev,stat.st_ino,stat.st_uid,hashlib.sha256(path.read_bytes()).hexdigest())
host=identity(source)
original=source.read_bytes()
assert original.endswith(b'GROUP ( libgcc_s.so.1 -lgcc )\n')
work=options.new_directory.absolute()
work.mkdir(mode=0o700)
materials=work/'materials';materials.mkdir()
unpublished=work/'private-libgcc-script';unpublished.write_bytes(original)
assert not unpublished.samefile(source)
subprocess.run(['as','--64',here/'observer.S','-o',materials/'observer.o'],check=True)
(materials/'valid.a').write_bytes(f'INPUT ( {materials}/observer.o )\n'.encode()+original)
(materials/'malformed.a').write_bytes(b'not a valid native linker script')
(materials/'absent.a').write_bytes(original)
(work/'mount-identity.json').write_text(json.dumps({'initial':os.readlink('/proc/self/ns/mnt'),'original':host[-1]})+'\n')
# The helper binds one task-owned file inside a private namespace and drops every capability
# before running the interpreter or any Cargo, compiler, test or native program.
mount="""/usr/bin/mount --bind "$1" "$2"
shift 2
exec /usr/bin/setpriv --reuid="$1" --regid="$2" --init-groups --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all /usr/bin/env -i "HOME=$3" "PATH=/usr/bin:/bin" "RUSTUP_PROXY_CARGO=$4" "OHM_REPLAY_PRIVATE_INPUTS=$5" /usr/bin/python3 -IB "$6" "$7" "$8" --external-provider --replacement "$9" --poison "${10}"
"""
proxy=Path(os.environ.get('RUSTUP_PROXY_CARGO',Path.home()/'.cargo/bin/cargo')).absolute()
args=['sudo','-n','/usr/bin/unshare','--mount','--propagation','private','/bin/sh','-eu','-c',mount,'held-implicit',unpublished,source,str(os.getuid()),str(os.getgid()),Path.home(),proxy,work,here/'replay-implicit.py',options.old_sdk.resolve(strict=True),work/'run',options.replacement_sdk.resolve(strict=True),options.poison]
try:
    subprocess.run(args,check=True)
finally:
    assert identity(source)==host
