"""Resolve one compiler-storage component in typed Cargo artifact output fields."""
import hashlib
import json
import re
from pathlib import Path

def encode(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'))
def digest(x):
    return hashlib.sha256(encode(x).encode()).hexdigest()
def candidate_dirs(target, value):
    base=Path(target)/'debug/build/workspaces'
    f=Path(value)
    if not f.is_relative_to(base):return None
    parts=f.relative_to(base).parts
    if len(parts)<3 or not re.fullmatch('[a-f0-9]{16}',parts[0]) or not re.fullmatch('v2-[a-f0-9]{16}',parts[1]):return None
    return base,parts
def anchor(target,rows):
    explicit=[]
    for raw in rows:
        row=json.loads(raw)
        if row['target']['name']!='unicode_ident' or 'lib' not in row['target']['kind']:continue
        for field in row['filenames']:
            pair=candidate_dirs(target,field)
            if pair is None:continue
            _,ar=pair
            if len(ar)==6 and ar[2]=='unicode-ident' and re.fullmatch('[a-f0-9]{16}',ar[3]) and ar[4]=='out' and ar[5]==f'libunicode_ident-{ar[3]}.rlib':
                explicit.append([ar[0],ar[1],ar[3],ar[5]])
    assert explicit and len({(v[0],v[1])for v in explicit})==1,explicit
    ns=sorted(explicit)[0][:2];return ns,sorted(explicit)
def canonical(target,rows,permitted):
    counts=0;result=[]
    def strip(value):
        nonlocal counts
        if value is None:return value
        pair=candidate_dirs(target,value)
        if pair is None:return value
        base,parts=pair
        assert list(parts[:2])==permitted,(permitted,parts[:2])
        assert '<compiler-matched-namespace>' not in value
        expected='/'.join([str(base),permitted[0],permitted[1],''])
        assert value.startswith(expected) and value.count(expected)==1
        counts+=1
        return value.replace(expected,'/'.join([str(base),permitted[0],'<compiler-matched-namespace>','']),1)
    for raw in rows:
        row=json.loads(raw)
        assert set(row)=={'package_id','manifest_path','target','profile','features','filenames','executable'}
        row['filenames']=[strip(f)for f in row['filenames']]
        row['executable']=strip(row['executable'])
        result.append(encode(row))
    assert counts>0;return sorted(result),counts
