"""Shipped-release holdouts for cache integrity, wrong executable, data isolation and env diagnostics."""
from pathlib import Path
exec(Path(__file__).with_name('cheap.py').read_text().partition('results={}\n')[0].replace('ohm-release17-panic-audit-20261028','ohm-release17-tracker-guards-20261028'))
out={}
def record(id,d,rows,**kw):
    out[str(id)]=dict(rows=rows,**kw);store(R/'partial.json',out);print(id,kw,flush=True)
def invoke(d,n,args=(),env=None,expected=0):
    j=call(d,n,list(args),env)
    assert (j['rc']==expected and not j['panic'] and not j['timeout']),(d,n,j)
    return j
def expect(d,n,value):assert (d/(n+'.out')).read_text().strip()==str(value),(d,n,value)
for id in [194,195]:
    d=R/str(id);source(d,'app','[dependencies]\ndep={path="dep"}\n[workspace]\n','fn main(){println!("PROBE_ALPHA {}",dep::value());}')
    source(d/'dep','dep','','pub fn value()->u32{11}',True);args=['run','--offline','--quiet'];rows=[invoke(d,'prime',args)];expect(d,'prime','PROBE_ALPHA 11')
    m,=(d/'target').rglob('*.rlink-cache.json');j=json.loads(m.read_text());op=next(Path(x['path']) for x in j['objects'] if b'PROBE_ALPHA' in Path(x['path']).read_bytes());assert op.is_relative_to(d)
    if id==194:
        old=op.read_bytes();s=op.stat();tmp=op.with_name('replacement');tmp.write_bytes(old.replace(b'PROBE_ALPHA',b'PROBE_WRONG'));os.utime(tmp,ns=(s.st_atime_ns,s.st_mtime_ns));tmp.replace(op);assert op.stat().st_size==len(old) and op.stat().st_mtime_ns==s.st_mtime_ns and op.read_bytes()!=old
    else:
        j['objects']=[x for x in j['objects'] if Path(x['path'])!=op];assert j['objects'];m.write_text(json.dumps(j));op.unlink()
    (d/'dep/src/lib.rs').write_text('pub fn value()->u32{22}');rows.append(invoke(d,'edit',args));expect(d,'edit','PROBE_ALPHA 22');record(id,d,rows,stdout='PROBE_ALPHA 22')
d=R/'206';source(d,'demo','[workspace]\n','fn main(){}');rows=[invoke(d,'prime',['build','--offline','--quiet'])]
obj,=(d/'target').rglob('*.rlink-objects');sib=d/'isolated-sibling';sib.mkdir()
for n in ['keep.o','keep.bc','keep.txt']:(sib/n).write_text(n)
before={q.name:sha(q) for q in sib.iterdir()};obj.rename(obj.with_name(obj.name+'.original'));obj.symlink_to(sib,target_is_directory=True);(d/'src/main.rs').write_text('fn main(){println!("edited");}');rows.append(invoke(d,'edit',['run','--offline','--quiet']));expect(d,'edit','edited');after={q.name:sha(q) for q in sib.iterdir()};assert before==after;record(206,d,rows,surviving=after)
d=R/'210';a=d/'a';b=d/'b';e={'CARGO_BUILD_BUILD_DIR':str(d/'shared')};rows=[];values=[]
for w,v in [(a,11),(b,22)]:source(w,'demo','[workspace]\n',f'fn main(){{println!("{v}");}}')
for i,(w,v) in enumerate([(a,11),(b,22),(a,11),(b,22)]):
    n='run'+str(i);rows.append(invoke(w,n,['-Zohm-defaults=no','run','--offline','--quiet'],e));expect(w,n,v);values.append(int((w/(n+'.out')).read_text()))
record(210,d,rows,values=values)
d=R/'212';shared=d/'shared';e={'CARGO_BUILD_BUILD_DIR':str(shared)};rows=[]
for w in ['alpha','beta']:
    p=d/w;source(p,w,'[workspace]\n','fn main(){}');rows.append(invoke(p,'build',['-Zohm-defaults=no','build','--offline','--quiet'],e))
assert shared.is_relative_to(R) and d.is_relative_to(R);(shared/'keep').write_text('only fixture');beta,=shared.rglob('bin-beta');before=sha(beta);rows.append(invoke(d/'alpha','clean',['-Zohm-defaults=no','clean','--offline'],e));assert sha(beta)==before and (shared/'keep').read_text()=='only fixture';record(212,d,rows,beta_fingerprint=before,foreign_file_retained=True)
d=R/'214';source(d,'probe','[workspace]\n','fn main(){println!("{}",env!("SEEN"));}');(d/'build.rs').write_text('fn main(){println!("cargo::rerun-if-env-changed=PROBE"); println!("cargo::rustc-env=SEEN={:?}",std::env::var_os("PROBE").as_ref().map(|v|v.as_encoded_bytes()));}');rows=[];vals=[]
for i,(env,val) in enumerate([({'PROBE':os.fsdecode(b'\xff')},'Some([255])'),({'PROBE':os.fsdecode(b'\xfe')},'Some([254])'),({},'None')]):
 n='run'+str(i);rows.append(invoke(d,n,['run','--offline','--quiet'],env));expect(d,n,val);vals.append(val)
record(214,d,rows,values=vals)
d=R/'215';source(d,'probe','[workspace]\n',r'fn main(){println!("{}",include_str!("data\nnotes"));}');(d/'src/data').write_text('11');real=d/'src/data\nnotes';real.write_text('11');rows=[invoke(d,'prime',['run','--offline','--quiet'])];expect(d,'prime',11);real.write_text('22');rows.append(invoke(d,'edit',['run','--offline','--quiet']));expect(d,'edit',22);record(215,d,rows,newline_filename=[11,22])
d=R/'218';source(d,'probe','[workspace]\n','fn main(){println!("{:?}",option_env!("PROBE"));}');rows=[invoke(d,'prime',['check','--offline','--quiet'])];env={'PROBE':os.fsdecode(b'\xff')};rows.append(invoke(d,'warm',['check','--offline','--quiet'],env,101));coldenv=dict(env,CARGO_TARGET_DIR=str(d/'cold'),CARGO_BUILD_BUILD_DIR=str(d/'cold-shared'));rows.append(invoke(d,'cold',['check','--offline','--quiet'],coldenv,101));assert (d/'warm.err').read_text()==(d/'cold.err').read_text() and 'not a valid Unicode string' in (d/'warm.err').read_text();record(218,d,rows,matching_error=sha(d/'warm.err'))
d=R/'219';source(d,'probe','description="alpha"\n[workspace]\n','fn main(){println!("{}",env!("CARGO_PKG_DESCRIPTION"));}');env={'CARGO_PKG_DESCRIPTION':'alpha'};rows=[invoke(d,'prime',['run','--offline','--quiet'],env)];expect(d,'prime','alpha');p=d/'Cargo.toml';p.write_text(p.read_text().replace('alpha','bravo'));rows.append(invoke(d,'edit',['run','--offline','--quiet'],env));expect(d,'edit','bravo');record(219,d,rows,values=['alpha','bravo'])
d=R/'225';d.mkdir();cache=d/'cache';ctx='0123456789abcdef';cache.mkdir();(cache/'.ohm-shared-registry-cache-v1').touch();dep=cache/'.ohm-gc-v1/dependencies'/ctx;dep.mkdir(parents=True);(dep/'usage').touch()
for i in range(8):
    profile=cache/('profile'+str(i));payload=profile/'build/registries'/ctx;payload.mkdir(parents=True);(profile/'.cargo-build-lock').touch();(payload/'lib').touch()
rows=[]
for n in ['first','second']:rows.append(invoke(d,n,['gc','--build-dir',str(cache)]))
record(225,d,rows,remaining=sorted(str(x.relative_to(cache)) for x in cache.rglob('usage')),context_still_exists=dep.exists());store(R/'complete.json',out)
