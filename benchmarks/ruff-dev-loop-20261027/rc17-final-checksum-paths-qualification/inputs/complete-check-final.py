from pathlib import Path
s=Path(__file__).with_name('complete-matrix-final.py').read_text().split('cases={}')[0]
exec(compile(s,'raw matrix helpers','exec'),globals())
st=root/'case';st.mkdir();shutil.copytree(tmpl,st/'code');src=st/'code/hold_direct/src/main.rs';src.write_text(src.read_text()+'\nconst _: [(); 17] = [(); escape_fixture::VALUE];\n')
actual=st/'input space/libescape_fixture.rlib';decoy=st/'input\\ space/libescape_fixture.rlib';actual.parent.mkdir();decoy.parent.mkdir()
env=dict(base,CARGO_HOME=str(st/'home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_BUILD_JOBS='4',CARGO_ENCODED_RUSTFLAGS='--extern\x1fescape_fixture='+str(actual))
start='old' if o.cargo=='upgrade' else o.cargo
def compile_r(val,out):
 (st/'external.rs').write_text('pub const VALUE:usize='+str(val)+';\n');cmd=['rustc','+ohm','--crate-name','escape_fixture','--crate-type','rlib','-Copt-level=1','-Cmetadata=identical-disambiguator','-Cdebuginfo=0',st/'external.rs','-o',out];r=run(cmd,st,env,start);assert r.returncode==0,r.stderr
compile_r(17,actual);shutil.copy2(actual,st/'real-original.rlib');compile_r(29,st/'future.rlib');shutil.copy2(st/'future.rlib',decoy)
res={}
def check(phase,ck,e=env):
 rec=st/'records'/phase;rec.mkdir(parents=True);cmd=['cargo','+ohm','check','--offline','-p','hold_direct','--message-format=json'];r=run(cmd,st/'code',e,ck);(rec/'stdout.jsonl').write_bytes(r.stdout);(rec/'stderr').write_bytes(r.stderr)
 ev=[json.loads(x) for x in r.stdout.splitlines()];art=[a for a in ev if a.get('reason')=='compiler-artifact'];diags=[a['message'] for a in ev if a.get('reason')=='compiler-message' and a['message'].get('level')=='error'];refs=[a for a in art if a['target']['name']=='hold_direct'];fds=[f for b in [Path(e['CARGO_TARGET_DIR']),Path(e['CARGO_BUILD_BUILD_DIR'])] for f in b.rglob('dep-bin-hold_direct') if f.is_file() and b'OBS' in f.read_bytes()];fp=None
 if fds:assert len(fds)==1;fp=fds[0];shutil.copyfile(fp,rec/'encoded')
 out={'exit':r.returncode,'units':len(art),'fresh':refs[0]['fresh'] if refs else None,'all_fresh':bool(refs) and all(a['fresh'] for a in art),'diagnostics':diags,'encoded':str(fp) if fp else None,'protocol':fp.read_bytes()[-41:-37].decode() if fp else None,'complete':fp.read_bytes()[-33] if fp else None};(rec/'row.json').write_text(json.dumps(out,indent=2)+'\n');res[phase]=out;print(phase,ck,r.returncode,out['fresh'],out['complete'],[(x.get('code') or {}).get('code') for x in diags],flush=True)
for label in ['first','train','unchanged']:check(label,start)
stamp=actual.stat();actual.write_bytes((st/'future.rlib').read_bytes());os.utime(actual,ns=(stamp.st_atime_ns,stamp.st_mtime_ns));check('changed',start)
if o.cargo=='upgrade':
 decoy.unlink();check('corrected','fixed')
end='fixed' if o.cargo=='upgrade' else start;check('independent',end,dict(env,CARGO_TARGET_DIR=str(st/'empty-target'),CARGO_BUILD_BUILD_DIR=str(st/'empty-shared')))
(root/'result.json').write_text(json.dumps(res,indent=2)+'\n')
assert res['first']['exit']==res['train']['exit']==res['unchanged']['exit']==0
assert res['independent']['exit']!=0 and any((x.get('code') or {}).get('code')=='E0308' for x in res['independent']['diagnostics'])
if o.cargo=='upgrade' and o.rust=='old':
 assert res['changed']['all_fresh'] and res['changed']['exit']==0 and res['corrected']['diagnostics']==res['independent']['diagnostics']
elif o.cargo=='old' and o.rust=='old':assert res['changed']['all_fresh'] and res['changed']['exit']==0
else:assert res['changed']['diagnostics']==res['independent']['diagnostics']
