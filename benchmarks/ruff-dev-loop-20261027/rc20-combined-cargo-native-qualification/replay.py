"""Replay the combined-stack correctness cases on caller-owned, authenticated SDKs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def sha(f):
    with f.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('fresh_directory',type=Path)
    ap.add_argument('combined_sdk',type=Path,help='combined Cargo installed beside official -19 rustc and lib')
    ap.add_argument('official18_sdk',type=Path)
    ap.add_argument('--only',choices=['all','values','diagnostics','assembler','writers'],default='all')
    opts=ap.parse_args();root=opts.fresh_directory.resolve();base=Path(__file__).resolve().parent
    if os.geteuid()==0 or sys.platform!='linux':ap.error('requires ordinary-uid Linux and a rustup Cargo proxy')
    if root.exists()or shutil.disk_usage(root.parent).free<=24*2**30+600*2**20:ap.error('choose a new directory on a volume with 24 GiB plus 600 MiB free')
    src=json.loads((base/'subjects.json').read_bytes());combined=opts.combined_sdk.resolve(strict=True);older=opts.official18_sdk.resolve(strict=True)
    for k,sdk,expected_c in [('19',combined,src['image']['binary_sha256']),('18',older,src['sdk18']['cargo'])]:
        enrolled=src['sdk'+k];drivers=list((sdk/'lib').glob('librustc_driver*.so'))
        if len(drivers)!=1 or any(sha(f)!=v for f,v in [(sdk/'bin/cargo',expected_c),(sdk/'bin/rustc',enrolled['rustc']),(drivers[0],enrolled['driver']),(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd',enrolled['wild'])]):ap.error('SDK '+k+' differs from the bound native images')
    root.mkdir(mode=0o700)
    def run(*args):
        subprocess.run([sys.executable,'-IB',*args],check=True)
    if opts.only in ('all','values'):run(base/'replay-values.py',combined,root/'values','--expect','correct')
    if opts.only in ('all','diagnostics'):
        run(base/'diagnostic.py',root/'combined-diagnostic',combined,src['image']['binary_sha256'],src['sdk19']['rustc'])
        run(base/'diagnostic.py',root/'shipped18-diagnostic',older,src['sdk18']['cargo'],src['sdk18']['rustc'])
    if opts.only in ('all','assembler'):
        run(base/'assembler.py',combined,root/'assembler-default','--incremental','0','--relationship','used-private')
        raw=(base/'assembler.py').read_bytes();needle=b"args=['cargo','+ohm']"
        assert sha(base/'assembler.py')==src['harnesses']['assembler_h8'] and raw.count(needle)==1
        helper=root/'assembler-yes.py';helper.write_bytes(raw.replace(needle,b"args=['cargo','+ohm','-Zrelink-only=yes']"))
        assert sha(helper)==src['harnesses']['assembler_yes']
        run(helper,combined,root/'assembler-explicit','--incremental','0','--relationship','used-private')
    if opts.only in ('all','writers'):
        w=base/'writer-probes'
        for n in ('public-api','resolve','provenance','check-hint'):
            tool='probe-generated-cargo-cache-writers.py' if n in ('public-api','resolve')else'probe-postcompile-cache-writers.py'
            run(w/tool,root/n,combined,'--case',n,'--expect','protected')
        run(w/'reproduce.py',root/'manifest','--sdk',combined,'--expect','protected')

if __name__=='__main__':main()
