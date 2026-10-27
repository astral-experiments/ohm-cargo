"""Compare two real Ruff builds on a fresh candidate, keeping all compiler inputs and plugin bytes equal."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,shutil,socket,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--driver',type=Path,required=True);p.add_argument('--sha',required=True);p.add_argument('--label',required=True);a=p.parse_args()
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';W=X/'pr233-three-parser-protocol-h5-v2';sys.path.insert(0,str(W))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,sha,load,dump,env
from state import gate_free,source_clean,seed,source_binds,set_source,FILES,RSL,DELETED
from namespace import skeleton,spawn_args
from processes import records
program=Path(__file__).resolve().parent
J=P/'allocation-ruff-diagnostic-v1';J.mkdir(mode=0o700,exist_ok=True)
O=J/a.label
assert a.label in ('parent','candidate') and socket.gethostname()=='charlie-ohm-loader-perf-1024'
assert sha(W/'SHA256SUMS')=='2f303a5f75b09b18eb4e0fb38d3579f846d80d47a49b512fea2af9dbd5a93190'
subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=W,check=True)
cargo=P/'alloc-cargo-control/cargo';cfg=env();cfg['PATH']=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin'
assert a.sha==sha(a.driver)==(a.driver.parent/'verified.sha').read_text().split()[0]
assert sha(cargo)=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'
assert sha(FROZEN/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
def prepare_fixture():
    import state
    patch=program/'parser.patch'
    assert sha(patch)=='08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff'
    # Reuse the registered state constructor at the directory containing its immutable patch.
    # H5 already has the original historical commit, the exact pinned worktree, and its real Git index.
    old=state.H
    try:
        state.H=program
        return state.inputs(O)
    finally:
        state.H=old
def invoke(out,opts,arg,input_bytes=None):
    out.mkdir();dump(out/'argv.json',arg)
    z=subprocess.run([*opts,*arg],env=cfg,cwd=RUFF,input=input_bytes,capture_output=True)
    (out/'stdout').write_bytes(z.stdout);(out/'stderr').write_bytes(z.stderr);dump(out/'status.json',{'rc':z.returncode})
    return z
def options(state):
    opts=spawn_args(skeleton_base,O,state,state/'registry-home',[],cargo,a.driver);k=opts.index('--');opts[k:k]=source_binds(state);return opts
def hd(md,st,out):
    v=invoke(out,options(st),['rustc','+ohm','--sysroot',str(FROZEN),'-Zls=root',str(md)]);assert v.returncode==0
    m=re.search(r'^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)',v.stdout.decode(),re.M);assert m
    return dict(private=m[1],stable=m[2],public=m[3])
def phys(st,logical):
    for n,root in [('target',TARGET),('shared',SHARED)]:
        if logical.is_relative_to(root):return st/n/logical.relative_to(root)
    raise ValueError(logical)
def run(out,st,mode,edited=None):
    d=O/'records'/out;d.mkdir(parents=True)
    set_source(st,fixture,(mode=='edited') if edited is None else edited)
    cmd=['cargo','+ohm','build','--locked','--offline','--message-format=json'];dump(d/'argv.json',cmd)
    with(d/'stdout').open('xb') as output,(d/'stderr').open('xb') as errors:
        z=subprocess.run([*options(st),'strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat,prctl','-o',str(d/'exec'),*cmd],cwd=RUFF,env=cfg,stdout=output,stderr=errors)
    dump(d/'status.json',{'rc':z.returncode});assert z.returncode==0,(d,(d/'stderr').read_text()[-1500:])
    items=[r for l in(d/'stdout').read_bytes().splitlines() if (r:=json.loads(l))['reason']=='compiler-artifact']
    assert len(items)==501,len(items)
    rustc=[v for _,f,v in records(d) if Path(f).name=='rustc' and '--crate-name' in v and '--out-dir' in v]
    rr,=[r for r in items if r['target']['name']=='ruff_python_parser']
    md,=[Path(f) for f in rr['filenames'] if f.endswith('.rmeta')];shown,=[Path(f) for f in rr['filenames'] if f.endswith('.rlib')]
    macro,=[r for r in items if r['target']['name']=='get_size_derive2'];plugin,=[Path(f) for f in macro['filenames'] if f.endswith('.so')];plugbytes=sha(phys(st,plugin))
    actual=next((v for v in rustc if v[v.index('--crate-name')+1]=='ruff_python_parser'),None)
    if mode=='fresh':
        assert not rustc and all(r['fresh'] for r in items)
    else:
        assert not rr['fresh'] and actual and '-Zlink-only' not in actual
        if mode=='edited':assert all(r['fresh'] for r in items if r['target']['name']=='ruff_python_ast') and macro['fresh']
    direct={}
    for i,k in enumerate(actual or []):
        if k=='--extern':
            name,path=actual[i+1].split('=',1);direct[name]={'logical':path,'sha256':sha(phys(st,Path(path)))}
    hdinfo=hd(md,st,d/'parser-header')
    unit=md.with_suffix('.rlib');assert phys(st,unit).samefile(phys(st,shown))
    parsed={'mode':mode,'units':len(items),'dirty_rustc_argv':rustc,'dirty_units':[(r['package_id'],r['target']['name']) for r in items if not r['fresh']],'parser':actual,'externs':direct,'header':hdinfo,'get_size_derive':str(plugin),'get_size_sha256':plugbytes,'rlib':str(unit),'rlib_sha256':sha(phys(st,unit)),'rmeta':str(md),'rmeta_sha256':sha(phys(st,md))}
    if mode=='edited':
        shutil.copyfile(phys(st,md),d/'parser.rmeta')
        archive=d/'archived-metadata.o';raw=d/'archived.rmeta'
        archive.write_bytes(subprocess.check_output(['ar','p',str(phys(st,unit)),'lib.rmeta']))
        subprocess.run(['objcopy','--dump-section','.rmeta='+str(raw),str(archive),str(d/'section-check.o')],check=True,capture_output=True)
        assert raw.read_bytes()==(d/'parser.rmeta').read_bytes(), 'archived raw parser metadata differs'
        parsed['archived_raw_sha256']=sha(raw)
        parsed['ruff_executable_sha256']=sha(phys(st,TARGET/'debug/ruff'))

        cli=[str(TARGET/'debug/ruff'),'check','--isolated','--no-cache','--output-format','json','--target-version','py314','-'];user_src=b"t'first' b'second'\n"
        c=invoke(d/'native-ruff',options(st),cli,user_src);(d/'native-ruff/stdin').write_bytes(user_src)
        assert c.returncode==1 and not c.stderr and [r['message'] for r in json.loads(c.stdout)]==['Bytes literal cannot be mixed with non-bytes literals']
        parsed['native_ruff_diagnostic_sha256']=sha(d/'native-ruff/stdout')
    dump(d/'result.json',parsed);return parsed
with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);assert source_clean();assert shutil.disk_usage(X).free>107*2**30
    gate_free(J,65*2**30);O.mkdir(mode=0o700);skeleton_base=skeleton(O);fixture=prepare_fixture()
    dump(O/'subject.json',{'cargo':str(cargo),'cargo_sha256':sha(cargo),'driver':str(a.driver),'driver_sha256':a.sha,'frontend_sha256':sha(FROZEN/'bin/rustc'),'historical_source':load(fixture/'manifest.json'),'timings':0})
    train=O/'state/training';train.parent.mkdir();seed(train,fixture,CARGO_HOME);rs={}
    rs['train']=run('train',train,'original');rs['fresh']=run('fresh',train,'fresh')
    paths=[Path(s.removeprefix('incremental=')).relative_to(TARGET) for s in rs['train']['parser'] if s.startswith('incremental=')];inc,=paths
    states={}
    for name in ['warm','empty']:
        st=O/'state'/name;gate_free(O,9*2**30);subprocess.run(['cp','-a','--reflink=auto','--',str(train),str(st)],check=True);states[name]=st
        ip,=(st/'target'/inc).glob('ruff_python_parser-*')
        assert any(ip.glob('s-*-*-*/query-cache.bin'))
        if name=='empty':ip.rename(O/'disabled-parser-session')
        rs[name]=run(name,st,'edited');dump(O/'results.json',rs)
    arow,brow=rs['warm'],rs['empty']
    for k in ['parser','externs','get_size_sha256','native_ruff_diagnostic_sha256']: assert arow[k]==brow[k],(k,arow[k],brow[k])
    assert len(arow['externs'])==16
    raw_equal=(arow['rmeta_sha256']==brow['rmeta_sha256'])
    header_equal=(arow['header']==brow['header'])
    dump(O/'raw-gate.json',{'eligible':raw_equal and header_equal,'raw_equal':raw_equal,'header_equal':header_equal,'timed_commands':0})
    for n,st in states.items():rs[n+'-fresh']=run(n+'-fresh',st,'fresh',True)
    dump(O/'results.json',rs)
    assert arow['get_size_sha256']==rs['train']['get_size_sha256']
    caller=O/'readers';caller.mkdir();bridge={};link=caller/'libbridge-input.rlib';link.touch()
    (caller/'bridge.rs').write_text('pub fn observed() -> String { match ruff_python_parser::parse_module("t\'first\' b\'second\'\\n") { Err(e) => e.to_string(), Ok(_) => panic!("expected invalid syntax") } }\n')
    (caller/'main.rs').write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
    jobs={};parser_args=arow['parser'];search=[v for i,k in enumerate(parser_args[:-1]) if k=='-L' for v in ['-L',parser_args[i+1]]];lib=Path(arow['rlib'])
    for n,st in states.items():
        op=options(st);d=caller/(n+'-bridge');q=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','-L','dependency='+str(lib.parent),*search,'--crate-name','ordinary_bridge','--crate-type','rlib',str(caller/'bridge.rs'),'--extern','ruff_python_parser='+str(lib),'-o',str(d/'libordinary_bridge.rlib')]
        z=invoke(d,op,q);assert z.returncode==0,z.stderr.decode();bridge[n]=d/'libordinary_bridge.rlib'
    for n,st in states.items():
        for t,b in bridge.items():
            op=options(st);i=op.index('--');op[i:i]=['--ro-bind',str(b),str(link)];d=caller/(n+'-caller-'+t)
            q=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','-L','dependency='+str(lib.parent),*search,str(caller/'main.rs'),'--extern','ordinary_bridge='+str(link),'-o',str(d/'app')]
            z=invoke(d,op,q);assert z.returncode==0,z.stderr.decode();v=invoke(d/'native',op,[str(d/'app')]);assert v.returncode==0 and v.stdout.strip()==b'Bytes literal cannot be mixed with non-bytes literals at byte range 0..18'
            jobs[n+'/'+t]=dict(bridge_sha256=sha(b),native_stdout=v.stdout.decode().strip())
    dump(O/'complete.json',{'results_sha256':sha(O/'results.json'),'callers':jobs,'source_index':source_clean(),'timings':0})
    print('qualified private hash',arow['header'],'raw',arow['rmeta_sha256'],'get-size-derive2',arow['get_size_sha256'],flush=True)
