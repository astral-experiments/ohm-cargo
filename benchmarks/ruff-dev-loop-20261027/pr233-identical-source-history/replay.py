"""Read an original and restored native parser from the very same physical Cargo dependency build."""
from pathlib import Path
import ast, collections, hashlib, itertools, json, os, re, shutil, socket, subprocess, sys
h=Path.home();x=h/'.cache/ohm-233-position-qualified-20261027';p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
s=x/'first-occurrence-classic-pr233-h5-v2';proto=x/'pr233-three-parser-protocol-h5-v2';snap=x/'pr233-h5-private-parser-witness-v2';out=x/'pr233-h5-ordinary-readers-build-v4'
assert socket.gethostname()=='charlie-ohm-loader-perf-1024' and (s/'build-complete.json').exists() and not out.exists()
out.mkdir(mode=0o700);os.sched_setaffinity(0,{29});os.nice(14)
sys.path.insert(0,str(proto))
from common import FROZEN,SONAME,RUFF
from processes import records
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def get(p):return json.loads(p.read_bytes())
def save(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
bound=get(proto/'binding.json');assert sha(proto/'binding.json')=='74b5d88f422ccb9751653ca595d99a78c95c8b469f1d83a5749b7db1cdc99d3a'
bridge=out/'bridge.rs';bridge.write_text('pub use ruff_python_parser as parser;\npub fn marker() -> usize { 0x233 }\n')
consumer=out/'caller.rs';consumer.write_text('pub use ordinary_parser_bridge::parser::lexer::lex as observed_lexer;\npub fn observed() -> usize { ordinary_parser_bridge::marker() }\n')
empty=out/'view';empty.mkdir();stub=out/'libordinary_parser_bridge.rmeta';stub.touch()
env=dict(HOME=str(h),PATH=str(h/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(p/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(p/'registry-home'),LC_ALL='C.UTF-8')
summary={}
for arm in 'BC':
    state=s/'state/build'/arm;reg=s/'receipts/build'/arm
    d=out/arm;d.mkdir();sel=d/'rustup';shutil.copytree(state/'rustup',sel,symlinks=True)
    source=get(reg/'cold/receipt.json');pids={j['pid'] for j in source['processes']['jobs'] if j['crate']=='ruff_linter' and j['kind']=='full'}
    assert len(pids)==1
    events=[(pid,av) for pid,img,av in records(reg/'cold') if pid in pids and img.endswith('/rustc') and '--crate-name' in av and av[av.index('--crate-name')+1]=='ruff_linter']
    assert len(events)==1
    trace,av=events[0];search=[]
    for i,t in enumerate(av):
        if t=='-L':search+=['-L',av[i+1]]
        elif t.startswith('-L') and len(t)>2:search.append(t)
    assert search
    tags={'cold':'original-baseline','restored':'lexer-pending-indentation-restore'}
    versions={}
    for tag,phase in tags.items():
        rec=snap/'build'/arm/phase/'record.json';r=get(rec);md=rec.parent/r['parser_rmeta_file'];assert r['view']=='original' and sha(md)==r['rmeta_sha256']
        versions[tag]=(r,md)
    assert versions['cold'][0]['source_inputs']==versions['restored'][0]['source_inputs']
    assert versions['cold'][0]['logical_reported_path']==versions['restored'][0]['logical_reported_path']
    def physical(path):
        for name,seg in (('native-target','target'),('shared','shared')):
            orig=p/name
            if path.is_relative_to(orig):return state/seg/path.relative_to(orig)
        return path
    reported=Path(versions['cold'][0]['logical_reported_path'])
    dirs={reported.parent}
    for i,arg in enumerate(search):
        if arg=='-L':arg=search[i+1]
        elif arg.startswith('-L'):arg=arg[2:]
        else:continue
        arg=arg.split('=',1)[-1]
        if Path(arg).is_absolute():dirs.add(Path(arg))
    views=d/'metadata-only-lookup';views.mkdir()
    projections={tag:[] for tag in tags}
    def parser_file(name):return name.startswith('libruff_python_parser') and name.endswith(('.rmeta','.rlib','.so'))
    for idx,logical_dir in enumerate(sorted(dirs)):
        host=physical(logical_dir)
        if not host.is_dir() or not any(parser_file(f.name) for f in host.iterdir()):continue
        for tag in tags:
            vdir=views/(str(idx)+'-'+tag);vdir.mkdir()
            for original in host.iterdir():
                if not parser_file(original.name): (vdir/original.name).symlink_to(original)
            if logical_dir==reported.parent:(vdir/reported.name).symlink_to(versions[tag][1])
            projections[tag].extend(['--ro-bind',str(vdir),str(logical_dir)])
    assert all(projections.values())

    results=[]
    for action,producer,inputtag in [('produce',a,a) for a in tags]+[('consume',a,b) for a,b in itertools.product(tags,tags)]:
        leaf=d/(action+'-'+producer+'-'+inputtag);leaf.mkdir()
        r,md=versions[inputtag];logical=Path(r['logical_reported_path'])
        opts=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--bind',str(leaf),str(empty),'--bind',str(sel),str(p/'rustup')]
        for sd,dest in [('target','native-target'),('shared','shared'),('registry-home','registry-home')]:
            opts+=['--ro-bind',str(state/sd),str(p/dest)]
        opts+=['--ro-bind',bound['arms'][arm]['driver'],str(FROZEN/'lib'/SONAME),*projections[inputtag]]
        opt=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','--crate-type=rlib','--emit=metadata','--error-format=json','-L','dependency='+str(logical.parent),*search]
        if action=='produce':
            cmd=opt+['--crate-name','ordinary_parser_bridge',str(bridge),'--extern','ruff_python_parser='+str(logical),'-o',str(empty/stub.name)]
        else:
            upstream=d/('produce-'+producer+'-'+producer)/stub.name
            assert upstream.is_file();opts+=['--ro-bind',str(upstream),str(stub)]
            cmd=opt+['--crate-name','ordinary_parser_caller',str(consumer),'--extern','ordinary_parser_bridge='+str(stub),'-o',str(empty/'libordinary_parser_caller.rmeta')]
        run=subprocess.run([*opts,'--','strace','-f','-qq','-s','8192','-e','trace=openat,openat2','-o',str(empty/'opens'),*cmd],cwd=RUFF,env=env,capture_output=True)
        (leaf/'stderr.jsonl').write_bytes(run.stderr);(leaf/'stdout').write_bytes(run.stdout);assert not run.stdout
        diag=[json.loads(z) for z in run.stderr.splitlines() if z.strip()]
        codes=[v['code']['code'] for v in diag if v.get('code')]
        live=(leaf/(stub.name if action=='produce' else 'libordinary_parser_caller.rmeta'))
        row=dict(action=action,producer=producer,loaded_parser=inputtag,status=run.returncode,diagnostic_codes=codes,primary_messages=[v['message'] for v in diag if v.get('code')],output_sha256=sha(live) if live.is_file() else None,parser_rmeta=sha(md),compiler=bound['arms'][arm]['driver_sha256'],compiler_argv=cmd,real_linter_search_trace_sha256=sha(reg/'cold'/trace),raw_diagnostics_sha256=sha(leaf/'stderr.jsonl'))
        lines=(leaf/'opens').read_text().splitlines()
        reads=sorted({m[1] for line in lines if (m:=re.search(r'openat(?:2)?\(AT_FDCWD, "([^"]*libruff_python_parser[^"]*\.(?:rmeta|rlib|so))".*?\)\s+=\s+\d+',line))})
        assert reads and set(reads)<={str(logical),str(md.resolve())},(arm,action,producer,inputtag,reads,codes)
        row.update(actual_successful_parser_opens=reads,lookup_open_trace_sha256=sha(leaf/'opens'))
        save(leaf/'receipt.json',row);results.append(row)
        if action=='produce' or producer==inputtag:assert run.returncode==0 and row['output_sha256'],row
        else:assert run.returncode==0 or (run.returncode==1 and bool(codes)),(action,producer,inputtag,run.returncode,codes)
    summary[arm]=results;save(out/'observations.json',summary)
save(out/'complete.json',{'observations':sha(out/'observations.json'),'driver_source':sha(proto/'binding.json')})
print(json.dumps({a:[[r['producer'],r['loaded_parser'],r['status'],r['diagnostic_codes']] for r in rows] for a,rows in summary.items()}))
