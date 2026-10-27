"""Export successful clean-check receipts and complete parent/candidate producer counters."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import time

p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
n='revision-native-66815c41574c'
check=p/(n+'-clean-check-control')
producer=p/(n+'-producer-instructions')
rc=p/(n+'-logs')/'clean-check-cost.rc'
while not rc.exists():
    time.sleep(8)
assert rc.read_text().strip()=='0'
s=json.loads((producer/'summary.json').read_bytes())
assert set(s)=={'check','build'} and all(len(v['pairs'])==4 for v in s.values())
rows=json.loads((producer/'observations.json').read_bytes())
assert len(rows)==16 and {r['driver_sha256'] for r in rows}=={'051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518','3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2'}
files = sorted(producer.glob('*-argv.json'))+[producer/'summary.json',producer/'observations.json']
files += sorted(producer.glob('*-??-*/receipt.json'))+sorted(producer.glob('*-??-*/rustc.ir'))
files += [check/'summary.json']+sorted(check.glob('*/*/receipt.json'))
sdk=p/'parser-assets/stage2/revision-series/dynamorio'
if (sdk/'client/pidcounter.c').is_file():files.append(sdk/'client/pidcounter.c')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
    for f in files:
        assert f.is_file() and not f.is_symlink() and f.stat().st_size<2_000_000
        if f.is_relative_to(producer):k='producer/'+str(f.relative_to(producer))
        elif f.is_relative_to(check):k='clean-check/'+str(f.relative_to(check))
        else:k=str(f.relative_to(sdk))
        tar.add(f,arcname=k,recursive=False)
