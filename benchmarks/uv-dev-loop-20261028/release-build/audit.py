from pathlib import Path
from hashlib import sha256
import csv, re, sys
p=Path(__file__).resolve().parent; stages=[('base',None),('unit','unit-deps'),('warnings','manifest-warnings'),('feature','feature-deps-small'),('depfile','depfile-render'),('semver','lock-version-req')]
expected_files=set((p/'affected-files.txt').read_text().splitlines());seen_hashes=set();previous=None;version=None;libs=None;rows=[]
for name,patch in stages:
    f=p/'bin'/name
    if not f.exists() and '--partial' in sys.argv: break
    fingerprint={filename:h for h,filename in (line.split('  ',1) for line in (p/f'logs/{name}.source.sha256').read_text().splitlines())}
    assert set(fingerprint)==expected_files,(name,set(fingerprint)^expected_files)
    if previous is not None:
        actual={filename for filename in fingerprint if fingerprint[filename]!=previous[filename]}; changed=set(re.findall(r'^\+\+\+ b/(.+)$',(p/f'patches/{patch}.patch').read_text(),re.M));assert actual==changed,(name,actual,changed)
    previous=fingerprint
    data=f.read_bytes();digest=sha256(data).hexdigest();assert digest not in seen_hashes;seen_hashes.add(digest)
    log=(p/f'logs/{name}.binary.txt').read_text(); assert digest in log
    actual_version=log.splitlines()[0]; actual_libs=[]
    for line in log.splitlines():
        if not line.startswith('\t'): continue
        dep=line.strip().split()[0]; actual_libs.append(dep.rsplit('/',1)[-1])
    if version is None:version=actual_version;libs=actual_libs
    assert actual_version==version and actual_libs==libs,(name,actual_version,actual_libs)
    elapsed=int(re.search(r'^elapsed_seconds=(\d+)$',log,re.M)[1]); rows.append((name,patch or '',len(data),elapsed,digest))
out=p/('binaries-partial.tsv' if '--partial' in sys.argv else 'binaries.tsv')
with out.open('w') as f:
    w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(['variant','patch_added','binary_bytes','build_seconds','sha256']);w.writerows(rows)
print(out,len(rows),version,libs)
