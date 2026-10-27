"""Audit realized full Cargo process-facing artifacts."""
import hashlib,json
from pathlib import Path
from shared import need
MODE_COUNTS={"test":(619,110)}

def as_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def audit_json(path,mode):
    rows=[json.loads(line) for line in path.read_bytes().splitlines() if line]
    need(rows[-1]=={'reason':'build-finished','success':True},path)
    arts=[r for r in rows if r['reason']=='compiler-artifact']
    need(len(arts)==MODE_COUNTS[mode][0],(mode,len(arts)))
    executable=sorted({r['executable'] for r in arts if r['executable']})
    paths={p for r in arts if r['package_id'].startswith('path+') for p in r['filenames'] if Path(p).suffix in {'','.so'}}
    elfs=[]
    for n in sorted(paths):
        with open(n,'rb') as f:
            if f.read(4)==b'\x7fELF':elfs.append(n)
    need(set(executable)<=set(elfs) and (len(elfs),len(executable))==((15,6) if mode=='build' else (110,102)),(mode,len(elfs),len(executable)))
    roster=sorted([json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in arts]);messages=sorted([json.dumps([r['package_id'],r['target']['name'],r['message']],sort_keys=True) for r in rows if r['reason']=='compiler-message'])
    return {'units':len(arts),'dirty':sorted(r['target']['name'] for r in arts if not r['fresh']),'elf':elfs,'executables':executable,'roster_sha256':as_digest(roster),'message_sha256':as_digest(messages),'roster':roster,'messages':messages}

