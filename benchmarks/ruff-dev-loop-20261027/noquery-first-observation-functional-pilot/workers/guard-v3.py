"""Native negative/positive checks with an unchanged frontend and in-place driver replacement."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys
D=Path(__file__).resolve().parent.parent; N=Path(__file__).resolve().parent
kind=sys.argv.pop(1)
assert kind in ('switch','wrapper','off','q-old-receipt')
if kind=='q-old-receipt':
 out=N/'Q-old-raw'; data={}
 for loc in sorted((out/'case/records').iterdir()):
  row=json.loads((loc/'row.json').read_bytes());tr=(loc/'exec').read_text();row['extra_queries']=[l for l in tr.splitlines() if 'execve(' in l and l.endswith('= 0') and '"-Zohm-observer-dep-info", "--print=sysroot"' in l];data[loc.name]=row
 assert data['first']['value']==17 and not data['first']['complete'] and data['first']['extra_queries'] and data['empty']['value']==data['changed']['value']==data['noop']['value']==29 and len(data['changed']['compiler_exec'])==1 and len(data['noop']['compiler_exec'])==0
 (out/'rechecked-observer.json').write_text(json.dumps({'original_classifier_exit':1,'expected_unsupported_query':True,'rows':data},indent=2)+'\n');print('confirmed',kind,flush=True);sys.exit()
s=(D/'input/equal-length-matrix.py').read_text().split('cases={}')[0]
s=s.replace("shutil.copytree(physical/'bin',logical/'bin',symlinks=False);", "(logical/'bin').mkdir();[(logical/'bin'/entry.name).symlink_to(entry) for entry in (physical/'bin').iterdir()];")
if kind in ('wrapper','off'):
 a=s.index("logical=root/'active-sdk'");b=s.index("def sha(path):",a)
 s=s[:a]+"logical=Path(os.environ['PRIVATE_NATIVE_SDK']);rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(logical);receipt=json.loads((release/'receipt.json').read_bytes());installed='fixed'\n"+s[b:]
# A wrapper also names rustc as argv[1]. Count only the executable in execve's first argument.
s=s.replace("compiler_rows=[s for s in physical if str(logical/'bin/rustc') in s or str((rustup/'toolchains/ohm')/'bin/rustc') in s]", """compiler_rows=[line for line in physical if (m:=re.search(r'execve\("([^"]+)"',line)) and Path(m.group(1)).name=='rustc' and Path(m.group(1)).samefile(logical/'bin/rustc')]""")
original_file=__file__;__file__=str(D/'input/native-guard-helpers.py')
exec(compile(s,'private native reader setup','exec'),globals());__file__=original_file
st=root/'case';st.mkdir();shutil.copytree(tmpl,st/'code')
src=st/'code/hold_direct/src/main.rs';src.write_text(src.read_text().replace(');}',');println!("escape-value={}",escape_fixture::value());}')+'\nconst _: &[u8] = include_bytes!("incidental.rlib");\n')
(src.parent/'incidental.rlib').write_bytes(b'only source, not an external crate\n')
actual=st/'extern space/libescape_fixture.rlib';actual.parent.mkdir();shadow=st/'no-decoy'
env=dict(base,CARGO_HOME=str(st/'cargo-home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_ENCODED_RUSTFLAGS='--extern\x1fescape_fixture='+str(actual),CARGO_BUILD_JOBS='3')
if kind=='wrapper':
 sh=st/'rustc-wrapper';sh.write_text('#!/bin/sh\nexec "$@"\n');sh.chmod(0o755);env['RUSTC_WRAPPER']=str(sh)
if kind=='off':env['CARGO_ENCODED_RUSTFLAGS']+='\x1f-Zcache-proc-macros=no'
compiler(st,env,17,actual,'fixed');compiler(st,env,29,st/'future.rlib','fixed')
orig=actual.stat();assert orig.st_size==(st/'future.rlib').stat().st_size
front=logical/'bin/rustc';front_stat=front.stat();front_sha=sha(front);dll=logical/'lib'/receipt['driver_name'];source=src.read_text();results={}
def rung(label):
 row=cargo(st,env,label,'fixed',actual,shadow)
 unit=st/'records'/label;trace=(unit/'exec').read_text();reported=(unit/'rustc.d').read_bytes()
 row.update(has_optional=b'# ohm-observer-inputs-v1 ' in reported,probe=sum('execve(' in l and l.endswith('= 0') and '"-Zohm-observer-dep-info", "--print=sysroot"' in l for l in trace.splitlines()),driver=sha(dll))
 assert (front.stat().st_ino,sha(front))==(front_stat.st_ino,front_sha)
 assert row['probe']==0 and not any('-Zohm-observer-dep-info' in l for l in row['compiler_exec'])
 results[label]=row
 (root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
def swap(other):
 dst=dll.parent/'private-next-driver';shutil.copyfile(other,dst);dst.replace(dll)
rung('prime');rung('repeat');ok=results['prime']
assert ok['value']==17
if kind=='wrapper':assert ok['complete']==0 and results['repeat']['complete']==0 and len(results['repeat']['compiler_exec'])==1
elif kind=='off':assert not ok['has_optional'] and ok['complete']==0 and results['repeat']['complete']==1
else:assert ok['complete']==1 and ok['has_optional'] and not results['repeat']['compiler_exec']
actual.write_bytes((st/'future.rlib').read_bytes());os.utime(actual,ns=(orig.st_atime_ns,orig.st_mtime_ns))
if kind=='switch':
 swap(D/'release-unicode/rc17-fixed/candidate-driver.so')
rung('changed');assert results['changed']['value']==29 and len(results['changed']['compiler_exec'])==1
if kind=='switch':
 assert not results['changed']['has_optional'] and results['changed']['driver']!=ok['driver']
 src.write_text(source+'\n// First ordinary source edit after driver rollback.\n');rung('old-source-edit');assert results['old-source-edit']['value']==29 and len(results['old-source-edit']['compiler_exec'])==1
 swap(N/'common-release/candidate-driver.so');src.write_text(source+'\n// Genuine source edit after returning to the supporting driver.\n');rung('return-edit');rung('return-fresh');assert results['return-edit']['value']==29 and results['return-fresh']['fresh']
env=dict(env,CARGO_TARGET_DIR=str(st/'clean-target'),CARGO_BUILD_BUILD_DIR=str(st/'clean-shared'));rung('empty');assert results['empty']['value']==29
print(kind,[(lab,v['value'],v['complete'],v['probe'],v['has_optional']) for lab,v in results.items()],flush=True)
