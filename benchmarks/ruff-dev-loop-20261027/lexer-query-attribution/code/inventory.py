"""Read only the traced compiler directories for the held-out historical edit."""
from pathlib import Path
from collections import Counter
import ast, datetime, hashlib, json, os, re, subprocess, sys
exec(IDS)
q=Path.home()/'.cache/ohm-233-position-qualified-20261027/first-occurrence-mixed-parser-20261027'
logical=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target')
version='1.99.0-dev (f1a7cf9d2 2026-10-25) (ohm-1.99.0-14)'
def birth(f):
 text=subprocess.check_output(['stat','-c','%w',f],text=True).strip()
 assert text!='-'
 return int(datetime.datetime.fromisoformat(text).timestamp()*1e6)
def facts(p):
 st=p.stat();return dict(path=str(p.relative_to(q)),bytes=st.st_size,mtime_us=st.st_mtime_ns//1000)
out={}
for mode in ('build','test'):
 for arm in ('B','C'):
  case=mode+'/'+arm; dest=q/'receipts'/case/'lexer-pending-indentation-edit';restore=q/'receipts'/case/'lexer-pending-indentation-restore'
  result=json.loads((dest/'receipt.json').read_bytes());st=q/'state'/case/'target';jobs=[];mdrefs=[]
  bounds=[birth(dest/'stdout'),(dest/'invocation.json').stat().st_mtime_ns//1000]
  restore_bounds=[birth(restore/'stdout'),(restore/'invocation.json').stat().st_mtime_ns//1000]
  for line in (dest/'stdout').read_bytes().splitlines():
   row=json.loads(line)
   if row.get('reason')=='compiler-artifact' and row['target']['name']=='ruff_python_parser' and not row['profile']['test'] and row['target']['kind']==['lib']:
    mdrefs.extend(facts(st/Path(x).relative_to(logical)) for x in row['filenames'] if x.endswith('.rmeta'))
  assert len(mdrefs)==1,mdrefs
  for rec in result['processes']['jobs']:
   assert rec['kind']=='full'; trace=dest/rec['pid'];lines=[]
   for raw in trace.read_text(errors='replace').splitlines():
    if raw.startswith('execve(') and raw.endswith('= 0'):
     m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',raw)
     if m and Path(ast.literal_eval(m[1])).name=='rustc':
      argv=[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])]
      if '--crate-name' in argv and argv[argv.index('--crate-name')+1]==rec['crate']:lines.append((raw,argv))
   (raw,argv),=lines
   get=lambda s:[argv[i+1] for i,v in enumerate(argv) if v==s]
   ct=get('--crate-type');exe=not ct or '--test'in argv or 'bin'in ct
   cs=get('-C');metadata=[v[9:] for v in cs if v.startswith('metadata=')]
   inc,=[v[12:] for v in cs if v.startswith('incremental=')]
   stable=stable_id(rec['crate'],metadata,exe,version)
   base=st/Path(inc).relative_to(logical)/(rec['crate']+'-'+b36(stable))
   generations=[]
   for parent in sorted(base.glob('s-*')):
    if not parent.is_dir():continue
    ts=int(parent.name.split('-')[1],36)
    graphs=[facts(x) for x in sorted(parent.glob('*dep-graph.bin'))]
    generations.append(dict(start_us=ts,in_edit=bounds[0]<=ts<=bounds[1],in_restore=restore_bounds[0]<=ts<=restore_bounds[1],files=graphs))
   ext=[s.split('=',1)[0].split(':')[-1] for s in get('--extern')]
   jobs.append(dict(crate=rec['crate'],stable_crate_id=f'{stable:016x}',metadata=metadata,crate_types=ct,test='--test'in argv,inc_base=base.name,base_exists=base.exists(),trace=rec['pid'],exec_line_sha256=hashlib.sha256(raw.encode()).hexdigest(),explicit_external_parser='ruff_python_parser'in ext,workspace_externs=sorted(k for k in ext if k.startswith(('ruff','ty_')) or k=='ty'),generations=generations))
  out[case]=dict(edit_command_bounds_us=bounds,restore_command_bounds_us=restore_bounds,regular_parser_rmeta=mdrefs[0],jobs=jobs)
print(json.dumps(out))
