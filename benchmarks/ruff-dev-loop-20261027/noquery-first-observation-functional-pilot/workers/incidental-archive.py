"""Discriminate an incidental .rlib source checksum from genuine compiler binary enumeration."""
from pathlib import Path
s=Path(__file__).with_name('equal-length-matrix.py').read_text().split('cases={}')[0]
exec(compile(s,'native one-extern acquisition helpers','exec'),globals())
assert o.rust=='fixed' and o.cargo=='fixed'
expected=os.environ['EXPECT_CAPTURE']
assert expected in {'legacy','ignored','optional','probe'}
st=root/'case';st.mkdir();shutil.copytree(tmpl,st/'code')
src=st/'code/hold_direct/src/main.rs'
src.write_text(src.read_text().replace(');}',');println!("escape-value={}",escape_fixture::value());}')+'\nconst _: &[u8] = include_bytes!("incidental.rlib");\n')
(src.parent/'incidental.rlib').write_bytes(b'only a source, not a compiler extern\n')
actual=st/'extern space/libescape_fixture.rlib';actual.parent.mkdir();shadow=st/'no-decoy'
env=dict(base,CARGO_HOME=str(st/'cargo-home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_BUILD_JOBS='4',CARGO_ENCODED_RUSTFLAGS='--extern\x1fescape_fixture='+str(actual))
compiler(st,env,17,actual,'fixed');compiler(st,env,29,st/'future.rlib','fixed');before=actual.stat();assert before.st_size==(st/'future.rlib').stat().st_size
rows={}
rows['first']=cargo(st,env,'first','fixed',actual,shadow);dep=Path(rows['first']['depfile']).read_bytes()
assert dep.startswith(b'# ohm-raw-checksum-paths-v2\n') and b'# checksum:' in dep and b'incidental.rlib' in dep
line=next((x for x in dep.splitlines() if x.startswith(b'# ohm-observer-inputs-v1 ')),None)
ordinary=dep if line is None else dep.replace(line+b'\n',b'',1)
assert any(x.startswith(b'# checksum:') and x.endswith(b'incidental.rlib') for x in ordinary.splitlines())
assert (b'libescape_fixture.rlib' in ordinary)==(expected=='probe')
assert (line is not None)==(expected in ('ignored','optional'))
assert rows['first']['complete']==int(expected in ('probe','optional'))
if line:
 phash,hexdata=line.split(b' ')[2:];nested=bytes.fromhex(hexdata.decode());(st/'nested.d').write_bytes(nested)
 assert phash.startswith(b'blake3=') and b'# checksum:' in nested and b'libescape_fixture.rlib' in nested
actual.write_bytes((st/'future.rlib').read_bytes());os.utime(actual,ns=(before.st_atime_ns,before.st_mtime_ns))
rows['changed']=cargo(st,env,'changed','fixed',actual,shadow)
rows['noop']=cargo(st,env,'noop','fixed',actual,shadow)
rows['empty']=cargo(st,dict(env,CARGO_TARGET_DIR=str(st/'clean-target'),CARGO_BUILD_BUILD_DIR=str(st/'clean-shared')),'empty','fixed',actual,shadow)
for label,row in rows.items():
 tr=(st/'records'/label/'exec').read_text();row['capability_queries']=[l for l in tr.splitlines() if 'execve(' in l and l.endswith('= 0') and '"-Zohm-observer-dep-info", "--print=sysroot"' in l]
assert rows['first']['stamps']==rows['changed']['stamps'] and rows['first']['real']!=rows['changed']['real']
assert rows['first']['value']==17 and rows['changed']['value']==rows['empty']['value']==rows['noop']['value']==29
assert not rows['changed']['fresh'] and len(rows['changed']['compiler_exec'])==1
assert rows['noop']['fresh'] and len(rows['noop']['compiler_exec'])==0
assert bool(rows['first']['capability_queries'])==(expected=='probe')
result={'rows':rows,'expected':expected,'inline_receipt':line is not None,'compiler':sha(logical/'bin/rustc'),'driver':receipt['candidate_postbolt'],'cargo':sha(new_c),'incidental_checksum':True,'ordinary_real_extern':b'libescape_fixture.rlib' in ordinary,'nested_sha':hashlib.sha256(nested).hexdigest() if line else None}
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('first',rows['first']['complete'],'receipt',line is not None,'compiled-after-edit',len(rows['changed']['compiler_exec']),'noop',len(rows['noop']['compiler_exec']))

