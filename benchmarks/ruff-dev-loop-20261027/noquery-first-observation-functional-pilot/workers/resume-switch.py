"""Resume the original swap from its successful post-downgrade Cargo command and two physical output namespaces."""
from pathlib import Path
from types import SimpleNamespace
import os,re,subprocess,shutil,json,hashlib,time
N=Path(__file__).resolve().parent;D=N.parent;root=N/'guard-switch-v2';st=root/'case';logical=root/'active-sdk';rustup=root/'rustup';new_c=N/'cargo-func/cargo-N';o=SimpleNamespace(rust='fixed');installed='fixed';old_c=new_c
source=(D/'input/equal-length-matrix.py').read_text();s=source[source.index('def sha(path):'):source.index("for ck in (['old','fixed']")]
a=s.index(' active=[x for base');b=s.index(' b=fp.read_bytes()',a)
s=s[:a]+''' traced=(rec/'exec').read_text()
 dirs_for_unit=set(re.findall(r'"--out-dir", "([^\"]+)"',line)[0] for line in traced.splitlines() if '"--crate-name", "hold_direct"' in line and line.endswith('= 0') and '"--out-dir", ' in line)
 if dirs_for_unit:
  assert len(dirs_for_unit)==1,dirs_for_unit
  selected=Path(dirs_for_unit.pop());assert selected.is_relative_to(dirs[0]) or selected.is_relative_to(dirs[1])
  selected_by_target[str(dirs[0])]=selected
 else:
  assert unit['fresh'];selected=selected_by_target[str(dirs[0])]
 fp=selected.parent/'fingerprint/dep-bin-hold_direct';dep,=selected.glob('hold_direct*.d')
 assert b'ohm-foreign-span-bytes' in dep.read_bytes() and b'OBS1' in fp.read_bytes()
'''+s[b:];s=s.replace('rec.mkdir(parents=True);cmd=','rec.mkdir(parents=True,exist_ok=True);cmd=')
selected_by_target={};exec(compile(s,'exact committed Cargo command result mapped to physical rustc output','exec'),globals())
rawrun=run
def run(args,case,e,ck,trace=None):
 if trace and trace.parent.name=='changed':
  assert trace.exists() and not (trace.parent/'row.json').exists()
  return subprocess.CompletedProcess(args,0,(trace.parent/'stdout.jsonl').read_bytes(),(trace.parent/'stderr').read_bytes())
 return rawrun(args,case,e,ck,trace)
src=st/'code/hold_direct/src/main.rs';source=src.read_text();actual=st/'extern space/libescape_fixture.rlib';shadow=st/'no-decoy'
env=dict(base,CARGO_HOME=str(st/'cargo-home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_ENCODED_RUSTFLAGS='--extern\x1fescape_fixture='+str(actual),CARGO_BUILD_JOBS='3')
front=logical/'bin/rustc';front_meta=(front.stat().st_ino,sha(front));dll=logical/'lib/librustc_driver-774a793a844d5500.so'
results=json.loads((root/'results.json').read_bytes());assert set(results)=={'prime','repeat'};assert results['prime']['complete']==1 and not results['repeat']['compiler_exec']
def rung(label):
 row=cargo(st,env,label,'fixed',actual,shadow);unit=st/'records'/label;tr=(unit/'exec').read_text();body=(unit/'rustc.d').read_bytes()
 row.update(probe=sum('execve(' in l and l.endswith('= 0') and '"-Zohm-observer-dep-info", "--print=sysroot"' in l for l in tr.splitlines()),has_optional=b'# ohm-observer-inputs-v1 ' in body,driver=sha(dll))
 assert row['probe']==0 and not any('-Zohm-observer-dep-info' in l for l in row['compiler_exec']) and (front.stat().st_ino,sha(front))==front_meta
 results[label]=row
 (root/'rechecked-namespace-results.json').write_text(json.dumps(results,indent=2)+'\n')
rung('changed');assert results['changed']['value']==29 and len(results['changed']['compiler_exec'])==1 and not results['changed']['has_optional']
src.write_text(source+'\n// Genuine first source edit after rollback.\n');rung('old-source-edit');assert results['old-source-edit']['value']==29 and len(results['old-source-edit']['compiler_exec'])==1
dst=dll.with_name('private-return-driver');shutil.copyfile(N/'common-release/candidate-driver.so',dst);dst.replace(dll)
assert sha(dll)==results['prime']['driver']
src.write_text(source+'\n// Genuine source edit after returning compiler.\n');rung('return-edit');rung('return-fresh');assert results['return-edit']['value']==29 and results['return-fresh']['fresh']
env=dict(env,CARGO_TARGET_DIR=str(st/'clean-target'),CARGO_BUILD_BUILD_DIR=str(st/'clean-shared'));rung('empty');assert results['empty']['value']==29
print([(k,r['value'],r['complete'],r['probe'],len(r['compiler_exec'])) for k,r in results.items()],flush=True)
