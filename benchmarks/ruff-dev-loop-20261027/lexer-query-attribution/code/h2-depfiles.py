from pathlib import Path
import hashlib,json,re,sys,subprocess
if len(sys.argv)==1:
 d=Path(__file__).resolve().parent
 rows=json.loads((d/'nine-terminals.json').read_bytes())['rows'];sel=[{k:j[k] for k in ('manifest_relpath','exe','stable_crate_id','source')}for j in rows]
 code=Path(__file__).read_text()
 result=subprocess.check_output(['dbox','ssh','charlie-ohm-relink-b-1024','--no-tmux','--','nice','-n','19','taskset','-c','30','/usr/bin/python3','-B','-c',code,'read'],input=json.dumps(sel).encode(),timeout=90)
 o=json.loads(result);(d/'retained-test-dep-info.json').write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
 for v in o:print(v['exe'],v['make_dep_info_present'],v['cargo_bin_env'],v['tracked_possible_bin_paths'],v['position_marker'])
 sys.exit()
q=Path.home()/'.cache/ohm-233-position-qualified-20261027/first-occurrence-mixed-parser-20261027/state/test/B';logical=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target')
o=[]
for r in json.load(sys.stdin):
 p=q/r['manifest_relpath'];f=p.with_suffix('').with_suffix('.d')
 alternatives=[p.with_name(r['exe']+'.d'),f]
 files={x for x in alternatives if x.is_file()};assert len(files)<=1
 if not files: o.append(dict(**r,make_dep_info_present=False,cargo_bin_env=None,tracked_possible_bin_paths=None,position_marker=None));continue
 f,=files;b=f.read_bytes();lines=b.decode().splitlines();env={}
 for line in lines:
  if (m:=re.match(r'^# env-dep:(CARGO_BIN_EXE_[^=]+)(?:=(.*))?$',line)):env[m[1]]=m[2]
 rules=[l for l in lines if l and not l.startswith('#')and ': ' in l];assert rules and not any(v.endswith('\\') for v in rules);tokens=sorted({token for rule in rules for token in rule.split(': ',1)[1].split()})
 match=sorted(t for t in tokens if t in env.values()or t.startswith(str(logical))and Path(t).name in ('ty','ruff','ruff_python_formatter'))
 o.append(dict(**r,make_dep_info_present=True,raw_sha256=hashlib.sha256(b).hexdigest(),cargo_bin_env=list(env),tracked_possible_bin_paths=match,tracked_path_count=len(tokens),position_marker=any('ohm-foreign-span-bytes'in t for t in tokens),env_path_values_sha256={k:hashlib.sha256((v or '').encode()).hexdigest()for k,v in env.items()}))
print(json.dumps(o))
