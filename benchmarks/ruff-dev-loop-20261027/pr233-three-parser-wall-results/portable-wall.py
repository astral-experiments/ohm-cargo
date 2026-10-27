"""Normalize the sole machine-specific Cargo registry directory in an already verified timing archive."""
from collections import defaultdict
from pathlib import Path
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

original, public = (Path(a).resolve() for a in sys.argv[1:])
public.mkdir()
basename_digest = '85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381'
alias = ('portable-registry-cache-' + basename_digest[:16]).encode()
old = None
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_bytes())
def dump(path, value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def canonical(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def once(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)
def product_rosters(raw, arm):
    rows=[json.loads(line) for line in raw.splitlines() if line]
    items=[r for r in rows if r.get('reason')=='compiler-artifact']
    cols=('package_id','manifest_path','target','profile','features','filenames','executable')
    values=[{k:r[k] for k in cols} for r in items]
    fingerprint=lambda x:canonical(sorted(json.dumps(r,sort_keys=True) for r in x))
    plain=fingerprint(values)
    prefix='/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target/debug/build/workspaces/2a0346c599559020/'
    scopes={'B':'v2-c95b8d54c8a62c02-all-native-all','C':'v2-8b4edd970c9a0df5-all-native-all'}
    for unit in values:
        paths=[]
        for x in [*unit['filenames'],unit['executable']]:
            if isinstance(x,str) and x.startswith(prefix):
                scope,_,rest=x[len(prefix):].partition('/')
                assert scope==scopes[arm] and rest
                x=prefix+'<registered-compiler-release>/'+rest
            paths.append(x)
        unit['filenames']=paths[:-1];unit['executable']=paths[-1]
    return plain,fingerprint(values)

original_export=read(original/'export-receipt.json')
shutil.copy2(original/'export-receipt.json',public/'original-export-receipt.json')
for f in sorted(original.iterdir()):
    if f.is_file() and 'cargo-evidence.zst.part-' not in f.name and f.name not in ('SHA256SUMS','export-receipt.json','verify-wall.py'):
        shutil.copy2(f,public/f.name)
shutil.copy2(original/'verify-wall.py',public/'verify-original-wall.py')
shutil.copy2(__file__,public/'portable-wall.py')
proof={}
by_kind=defaultdict(dict)
def remember(kind,before,after):
    if before!=after:
        assert by_kind[kind].setdefault(before,after)==after
seen_rosters=set();entries=0
original_parts=sorted(original.glob('cargo-evidence.zst.part-*'))
assert original_parts
with tempfile.TemporaryDirectory() as td:
    packed=Path(td)/'portable.zst'
    cat=subprocess.Popen(['cat',*original_parts],stdout=subprocess.PIPE)
    decomp=subprocess.Popen(['zstd','-q','-d','--stdout'],stdin=cat.stdout,stdout=subprocess.PIPE);cat.stdout.close()
    with packed.open('wb') as dest:
        comp=subprocess.Popen(['zstd','-q','-10','-T2','--long=26','--stdout'],stdin=subprocess.PIPE,stdout=dest)
        with tarfile.open(fileobj=decomp.stdout,mode='r|') as src,tarfile.open(fileobj=comp.stdin,mode='w|',format=tarfile.GNU_FORMAT) as dst:
            for member in src:
                n=member.name;assert member.isfile();entries+=1
                raw=src.extractfile(member).read()
                if old is None and n.endswith('/stdout'):
                    roots=set(re.findall(rb'/registry/src/([^/]+)/',raw))
                    candidates=[r for r in roots if sha(r)==basename_digest]
                    if candidates:old,=candidates
                assert alias not in raw
                norm=raw.replace(old,alias) if old is not None else raw
                if norm!=raw:
                    assert norm.replace(alias,old)==raw
                    kind=Path(n).name
                    assert kind in ('stdout','stderr','programs.json'),n
                    proof[n]=[sha(raw),sha(norm),raw.count(old)]
                    if kind in ('stdout','stderr'):remember('raw',sha(raw),sha(norm))
                    if kind=='programs.json':
                        for a,b in zip(json.loads(raw),json.loads(norm),strict=True):
                            if a!=b:
                                assert a[:3]==b[:3] and a[4]==b[4] and a[3] is not None
                                assert a[4]==sha(json.dumps(a[3],separators=(',',':')).encode())
                                remember('argv',a[4],sha(json.dumps(b[3],separators=(',',':')).encode()))
                    if kind=='stdout':
                        assert n.endswith(('/first/stdout','/immediate/stdout'))
                        pieces=n.split('/')
                        arm=next(s for s in pieces if s in ('B','C'))
                        lk=(arm,raw.count(b'"reason":"compiler-artifact"'))
                        if lk not in seen_rosters:
                            seen_rosters.add(lk)
                            o=product_rosters(raw,arm);v=product_rosters(norm,arm)
                            for a,b in zip(o,v):remember('roster',a,b)
                        # The selected local basename occurs only in the manifest or target on a registry artifact.
                        # If another Cargo record contains it, a new verifier binding is required.
                        if raw.count(old) != 2*sum(1 for row in raw.splitlines() if old in row):raise ValueError(n)
                member.size=len(norm);dst.addfile(member,io.BytesIO(norm))
        comp.stdin.close();assert comp.wait()==0
    decomp.stdout.close();assert decomp.wait()==cat.wait()==0
    assert entries==original_export['selected_files'] and len(proof)>=192 and len(seen_rosters)==4 and old is not None
    hh=hashlib.sha256()
    with packed.open('rb') as f:
        index=0
        while buf:=f.read(6<<20):
            hh.update(buf);(public/f'cargo-evidence.zst.part-{index:04d}').write_bytes(buf);index+=1
    report={**original_export,'sha256':hh.hexdigest(),'bytes':packed.stat().st_size,'path':'cargo-evidence.zst.part-*'}
dump(public/'export-receipt.json',report)
dump(public/'portable-receipt.json',dict(original_export_sha256=original_export['sha256'],portable_export_sha256=report['sha256'],registry_component_sha256=basename_digest,replacement=alias.decode(),changed_members=proof,digest_map=by_kind))
s=(original/'verify-wall.py').read_text()
s=once(s,"refs=None","""refs=None
portable=read(here/'portable-receipt.json')
assert portable['portable_export_sha256']==packed['sha256']
assert portable['original_export_sha256']==read(here/'original-export-receipt.json')['sha256']
def portable_digest(kind,d):return portable['digest_map'].get(kind,{}).get(d,d)
checked_portable=set()
def verify_portable_member(name,raw):
    entry=portable['changed_members'].get(name)
    count=raw.count(portable['replacement'].encode())
    if not entry:assert count==0;return
    actual=sha(raw);assert entry[1]==actual and int(entry[2])==count and count>0
    if name.endswith(('/stdout','/stderr')):assert portable_digest('raw',entry[0])==actual
    checked_portable.add(name)
""")
s=once(s,"r['stdout_sha256']==sha(f['stdout']) and r['stderr_sha256']==sha(f['stderr'])","portable_digest('raw',r['stdout_sha256'])==sha(f['stdout']) and portable_digest('raw',r['stderr_sha256'])==sha(f['stderr'])")
s=once(s,"==ref['roster'] and", "==portable_digest('roster',ref['roster']) and") if "==ref['roster'] and" in s else once(s,"==ref['roster']\n","==portable_digest('roster',ref['roster'])\n")
s=once(s,"}==normalized\n","}==dict(normalized,sha256=portable_digest('roster',normalized['sha256']))\n")
s=once(s,"separators=(',',':')).encode())==ah","separators=(',',':')).encode())==portable_digest('argv',ah)")
s=once(s,"files.setdefault(bits[-2],{})[bits[-1]]=stream.extractfile(member).read()","raw=stream.extractfile(member).read();verify_portable_member(name,raw);files.setdefault(bits[-2],{})[bits[-1]]=raw")
s=once(s,"observations=summary['observations']","assert checked_portable==set(portable['changed_members'])\nobservations=summary['observations']")
(public/'verify-wall.py').write_text(s)
with (public/'README.md').open('a') as f:
    f.write('\nThe public archive replaces one machine-specific Cargo registry checkout basename with a stable alias. The translation preserves all other Cargo output, all times, every native job and all original witness records. The raw archive passed the original verifier before this export. Each translated member has its original and public digest and substitution count in `portable-receipt.json`. The offline verifier recomputes the normalized unit rosters and checks each original timing witness. `verify-original-wall.py` verifies the unmodified archive on its originating system.\n')
def finalize():
    files=sorted(f for f in public.iterdir() if f.is_file() and f.name!='SHA256SUMS')
    assert all(f.stat().st_size<8_000_000 for f in files)
    m=public/'SHA256SUMS';m.write_text(''.join(sha(f.read_bytes())+'  '+f.name+'\n' for f in files))
    print(len(files),sha(m.read_bytes()),'members',entries,'portable',len(proof),flush=True)
finalize()
