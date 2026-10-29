#!/usr/bin/python3
import os,sys
from pathlib import Path
a=sys.argv[1:]
if '--crate-name' in a and a[a.index('--crate-name')+1]=='manifest_case':
    f=Path(os.environ['CARGO_MANIFEST_DIR'])/'Cargo.toml'
    a.extend(['--cfg','observed_test_off' if b'\ntest = false\n' in f.read_bytes() else 'observed_test_on'])
os.execvp(a[0],a)
