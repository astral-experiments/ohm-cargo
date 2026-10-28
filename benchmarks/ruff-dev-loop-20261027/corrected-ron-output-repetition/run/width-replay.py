"""Replay the same released Wild invocation at each width before its transient operands disappear."""
from pathlib import Path
import ast,fcntl,hashlib,json,os,re,shutil,subprocess,sys,traceback
H=Path(__file__).resolve().parent
origin=H.parent/'ohm-ron-fixed-whole-native-h4-20261028-v1'
proto=H.parent/'ohm-noquery-full-native-h4-20261028-v2/protocol'
sys.path.insert(0,str(proto));import engine as q
def shim():
    args=sys.argv[1:];cube=Path(os.environ['WIDTH_REPLAY_CAPTURE']);binary=cube.parent/'stock-wild'
    if '-o' not in args:os.execv(str(binary),[sys.argv[0],*args])
    output=Path(args[args.index('-o')+1]);assert output.name==os.environ['WIDTH_REPLAY_EXPECTED'];assert not any(x.startswith('--threads')for x in args)
    raw=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
    def operands():
        selected={}
        for i,val in enumerate(args):
            if i and args[i-1]=='-o':continue
            if val.startswith('-') or not Path(val).is_file():continue
            selected[i]={'basename':Path(val).name,'bytes':Path(val).stat().st_size,'sha256':raw(val)}
        return selected
    before=operands();assert len(before)>80
    out={}
    for width in ('default',1,2,4,8,16):
        argv=[sys.argv[0],*args]+([] if width=='default' else ['--threads='+str(width)])
        pr=subprocess.run(argv,executable=binary)
        assert pr.returncode==0 and output.is_file(),(width,pr.returncode)
        sig=raw(output);dest=cube/'bodies'/sig
        if not dest.exists():shutil.copyfile(output,dest);assert raw(dest)==sig
        out[str(width)]=sig
    assert operands()==before
    q.dump(cube/'wild.json',{'widths':out,'simultaneous_operands':before,'same_resolved_positive_operand_bytes_after_all_links':True,'unclassified_libraries':[x for x in args if x.startswith('-l')],'actual_argv_sha256':hashlib.sha256(json.dumps(args,separators=(',',':')).encode()).hexdigest(),'native_binary':raw(binary)})
def caller():
    assert (origin/'rc').read_text().strip()=='0'
    st=origin/'states/fixed-release-rust';rep=origin/'results/fixed-release-rust/unchanged-3';sub=q.load(proto/'subject-binding.json')
    spec=Path(sub['old_driver']['path']);assert q.sha(spec)=='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'
    trace=q.load(rep/'native-processes.json');names=('document','ty_python_semantic')
    stock=Path(next(iter({r[-1] for r in trace['linkers']})));assert q.sha(stock)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    shutil.copy2(stock,H/'stock-wild');assert q.sha(stock)==q.sha(H/'stock-wild')
    env=q.env();env.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');env.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');env['CARGO_BUILD_JOBS']='8'
    with q.LOCK.open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert shutil.disk_usage(H).free>30*2**30
        for name in names:
            w=H/name;w.mkdir();(w/'bodies').mkdir()
            pid,=[j[0] for j in trace['jobs'] if j[1]==name and j[2]=='link-only'];raw=q.Path(rep/'trace'/('exec.'+str(pid))).read_bytes()
            good=[l for l in raw.splitlines() if b'execve(' in l and re.search(rb'\)\s+= 0$',l)];assert len(good)==1
            m=re.search(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',good[0]);args=ast.literal_eval(m[2].decode())
            link,=[Path(a)for a in args if a.endswith('.rlink')];canonical=link.parent;original=st/'target'/canonical.relative_to(q.TARGET);subprocess.run(['cp','-a','--reflink=auto',str(original),str(w/'out')],check=True)
            opts=q.load(st/'secure-options.json')
            for a,b in [(st/'target',q.TARGET),(st/'build',q.BUILD),(st/'home',q.CH),(st/'rustup',q.P/'rustup'),(origin/'fixed-cargo',q.FROZEN/'bin/cargo'),(spec,q.FROZEN/'lib'/q.SONAME),(H/'shim',stock)]:opts+=['--ro-bind',str(a),str(b)]
            for a,b in [(w,w),(w/'out',canonical)]:opts+=['--bind',str(a),str(b)]
            env['WIDTH_REPLAY_CAPTURE']=str(w);env['WIDTH_REPLAY_EXPECTED']=link.stem
            res=subprocess.run([*opts,'--','taskset','-c','0-23',*args],env=env,cwd=q.WT,capture_output=True,timeout=240)
            (w/'stdout').write_bytes(res.stdout);(w/'stderr').write_bytes(res.stderr);assert res.returncode==0,(name,res.stderr[-1100:])
            x=q.load(w/'wild.json');assert len(x['widths'])==6
            targets={f.parent.name:q.load(f)[str(canonical/link.stem)] for f in (origin/'results/fixed-release-rust').glob('*/native-elf.json')}
            q.dump(w/'result.json',{'captured_rustc_exec':hashlib.sha256(good[0]).hexdigest(),'recipe_sha256':q.sha(original/link.name),'native':x,'workspace_outputs':targets,'reproduced':{k:v in x['widths'].values() for k,v in targets.items()}})
        q.dump(H/'complete.json',{n:q.load(H/n/'result.json')for n in names})
if os.environ.get('WIDTH_REPLAY_MODE')=='interposed':shim()
else:
    try:caller()
    except BaseException:(H/'failure.txt').write_text(traceback.format_exc());raise
