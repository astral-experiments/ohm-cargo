"""Compare the actual PGO Cargo library and CLI rustc arguments and primary extern files."""
import hashlib,json,re,subprocess as sp
from pathlib import Path
X=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-rc17-20261028');I=X/'inputs';D=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027');S=D/'states/raw-rc17'
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
rows={}; data=json.loads((X/'complete.json').read_bytes())
def resolve(a,k):
 path=Path(k)
 for part in ('target','cargo-home','shared'):
  if path.is_relative_to(S/part):return X/a/'state'/part/path.relative_to(S/part)
 return path
for a in ('A','Q','N'):
 records={}
 for full in (X/a/'compiler.exec').read_text().splitlines():
  if '"--crate-name", "cargo"' not in full or 'execve(' not in full or '"--print=' in full or '"link-only"' in full:continue
  source=next((src for src in ('src/lib.rs','src/bin/cargo/main.rs') if '"'+src+'"' in full),None)
  if not source or 'profile-use=' not in full:continue
  args=re.findall(r'"((?:\\.|[^"\\])*)"',full.split('execve(',1)[1]); argv=args[1:]
  externs={}
  for i,w in enumerate(argv[:-1]):
   if w=='--extern':
    name,loc=argv[i+1].split('=',1);p=resolve(a,loc);assert p.is_file(),loc
    externs[name]={'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)}
  assert len(externs)>4
  row={'argv':hashlib.sha256(b'\0'.join(v.encode() for v in argv)).hexdigest(),'count':len(externs),'externs':externs}
  assert source not in records or records[source]==row,(a,source)
  records[source]=row
 assert len(records)==2
 rows[a]=records
report={}
for source in rows['A']:
 base=rows['A'][source]['externs']; summary={}
 for a in ('N','Q'):
  ext=rows[a][source]['externs'];assert set(ext)==set(base);summary[a]={'argv_equal':rows[a][source]['argv']==rows['A'][source]['argv'],'same':sum(base[k]==ext[k] for k in ext),'differ':sorted(k for k in ext if ext[k]!=base[k]),'total':len(ext)}
 report[source]=summary
out={'classification':'source/profile matched production builds, comparison of the actual direct --extern files in both cargo-library and cargo CLI compilations','summary':report,'arms':rows}
(X/'release-input-audit.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n');print(json.dumps(report),sha(X/'release-input-audit.json'))
