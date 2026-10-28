"""Replay the same released Wild invocation at each width before its transient operands disappear."""
from pathlib import Path
import ast,fcntl,hashlib,json,os,re,shutil,subprocess,sys,traceback
H=Path(__file__).resolve().parent
origin=H.parent/'ohm-ron-fixed-whole-native-h4-20261028-v1'
proto=H.parent/'ohm-noquery-full-native-h4-20261028-v2/protocol'
sys.path.insert(0,str(proto));import engine as q
def shim():
    import time
    args=sys.argv[1:];cube=Path(os.environ['WIDTH_REPLAY_CAPTURE']);binary=cube.parent/'stock-wild';hasher=cube.parent/'hash-inputs'
    if '-o' not in args:os.execv(str(binary),[sys.argv[0],*args])
    output=Path(args[args.index('-o')+1]);assert output.name==os.environ['WIDTH_REPLAY_EXPECTED'] and set(os.sched_getaffinity(0))==set(range(4,12))
    before_load=Path('/proc/loadavg').read_text().split()[:3];df=cube/'actual.d'
    wild=[sys.argv[0],*args,'--threads=8']
    cap=subprocess.run([*wild,'--dependency-file='+str(df)],executable=binary,capture_output=True)
    assert cap.returncode==0,(cap.returncode,cap.stderr[-800:]);whole=q.sha(output)
    raw=df.read_bytes();lines=raw.decode().splitlines();prefix=str(output)+': ';assert lines[0].startswith(prefix)
    deps=[Path(n)for n in lines[0][len(prefix):].split()];assert len(deps)==len(set(deps)) and len(deps)>10 and all(f.is_file()for f in deps)
    assert set(l[:-1]for l in lines[1:]if l)==set(map(str,deps));sigs=[];rec=[]
    for p in deps:
        st=p.stat();area='sdk'if p.is_relative_to(q.FROZEN)else'target'if p.is_relative_to(q.TARGET)else'shared-build'if p.is_relative_to(q.BUILD)else'system'if any(p.is_relative_to(r) for r in ['/usr','/lib','/lib64'])else'other'
        with p.open('rb')as f:magic=f.read(8);kind='elf'if magic.startswith(b'\x7fELF')else'archive'if magic==b'!<arch>\n'else'bitcode'if magic.startswith(b'BC\xc0\xde')else'thin'if magic==b'!<thin>\n'else'other'
        v={'name':p.name,'class':area,'bytes':st.st_size,'kind':kind,'path_sha256':hashlib.sha256(os.fsencode(p)).hexdigest(),'node':[st.st_dev,st.st_ino],'mtime_ns':st.st_mtime_ns}
        if area=='system':
            v['given']=str(p);v['resolved']=str(p.resolve())
            if kind=='other' and st.st_size<65536:
                script=p.read_text('ascii');body=re.sub(r'/\*.*?\*/',' ',script,flags=re.S);v['script_tokens']=re.findall(r'\(|\)|[^\s()]+',body)
        rec.append(v)
    assert all(v['class'] not in('other','shared-build') or Path(p).is_file()for v,p in zip(rec,deps))
    def hash_all():
        call=subprocess.run([hasher,*deps],capture_output=True,check=True);result=call.stdout.splitlines();assert len(result)==len(deps) and all(re.fullmatch(b'[0-9a-f]{64}',k) for k in result);return result
    first=hash_all()
    for p,v,hashval in zip(deps,rec,first):
        v['blake3']=hashval.decode()
    independent=[]
    picks=[next(i for i,v in enumerate(rec) if v['kind']=='elf'),next(i for i,v in enumerate(rec)if v['kind']=='archive'),max(range(len(rec)),key=lambda i:rec[i]['bytes'])]
    for i in sorted(set(picks)):
        simple=subprocess.run([q.BLAKE,deps[i]],capture_output=True,check=True);other=re.findall(rb'[0-9a-f]{64}',simple.stdout);assert first[i]in other,(i,simple.stdout[:120]);independent.append(rec[i]['blake3'])
    def link():
        x=subprocess.run(wild,executable=binary,capture_output=True,check=True);return x
    link();assert q.sha(output)==whole
    # A fixed balanced engineering diagnostic. These are six warm isolated pairs per family, with no endpoint eligibility attached.
    schedules=['WH','HW','HW','WH','HW','WH'];rows=[]
    for seq in schedules:
        row={'order':seq}
        for k in seq:
            before=time.monotonic_ns();res=link() if k=='W' else hash_all();elapsed=time.monotonic_ns()-before;row[k]=elapsed
            if k=='W':assert q.sha(output)==whole
            else:assert res==first
        rows.append(row)
    last=hash_all();assert last==first
    q.dump(cube/'candidate-cost.json',{'native_binary':q.sha(binary),'hasher':q.sha(hasher),'oracle':whole,'explicit_width':8,'affinity':sorted(os.sched_getaffinity(0)),'raw_depfile_sha256':hashlib.sha256(raw).hexdigest(),'native_depfile_paths':rec,'library_flags':[a for a in args if a.startswith('-l')],'rows':rows,'selected_double_checked_blake3':independent,'all_positive_operand_hashes_equal_throughout':True,'host_load_before':before_load,'host_load_after':Path('/proc/loadavg').read_text().split()[:3]})

def caller():
    assert (origin/'rc').read_text().strip()=='0'
    st=origin/'states/fixed-release-rust';rep=origin/'results/fixed-release-rust/unchanged-3';sub=q.load(proto/'subject-binding.json')
    spec=Path(sub['old_driver']['path']);assert q.sha(spec)=='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'
    trace=q.load(rep/'native-processes.json');names={'simple_tokenizer':'simple_tokenizer-c639259863b397fa','document':'document-1dd8f0784781d62c','ruff':'ruff-9c601305a3f3b4b8'}
    stock=Path(next(iter({r[-1] for r in trace['linkers']})));assert q.sha(stock)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    shutil.copy2(stock,H/'stock-wild');assert q.sha(stock)==q.sha(H/'stock-wild')
    env=q.env();env.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');env.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');env['CARGO_BUILD_JOBS']='8'
    with q.LOCK.open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert shutil.disk_usage(H).free>30*2**30
        for name in names:
            w=H/name;w.mkdir();(w/'bodies').mkdir()
            pid,=[j[0] for j in trace['jobs'] if j[1]==name and j[2]=='link-only' and (names[name]+'.rlink').encode() in (rep/'trace'/('exec.'+str(j[0]))).read_bytes()];raw=q.Path(rep/'trace'/('exec.'+str(pid))).read_bytes()
            good=[l for l in raw.splitlines() if b'execve(' in l and re.search(rb'\)\s+= 0$',l)];assert len(good)==1
            m=re.search(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',good[0]);args=ast.literal_eval(m[2].decode())
            link,=[Path(a)for a in args if a.endswith('.rlink')];canonical=link.parent;original=st/'target'/canonical.relative_to(q.TARGET);subprocess.run(['cp','-a','--reflink=auto',str(original),str(w/'out')],check=True)
            opts=q.load(st/'secure-options.json')
            for a,b in [(st/'target',q.TARGET),(st/'build',q.BUILD),(st/'home',q.CH),(st/'rustup',q.P/'rustup'),(origin/'fixed-cargo',q.FROZEN/'bin/cargo'),(spec,q.FROZEN/'lib'/q.SONAME),(H/'shim',stock)]:opts+=['--ro-bind',str(a),str(b)]
            for a,b in [(w,w),(w/'out',canonical)]:opts+=['--bind',str(a),str(b)]
            env['WIDTH_REPLAY_CAPTURE']=str(w);env['WIDTH_REPLAY_EXPECTED']=link.stem
            res=subprocess.run([*opts,'--','taskset','-c','4-11',*args],env=env,cwd=q.WT,capture_output=True,timeout=360)
            (w/'stdout').write_bytes(res.stdout);(w/'stderr').write_bytes(res.stderr);assert res.returncode==0,(name,res.stderr[-1100:])
            x=q.load(w/'candidate-cost.json');assert len(x['rows'])==6
            targets={f.parent.name:q.load(f)[str(canonical/link.stem)] for f in (origin/'results/fixed-release-rust').glob('*/native-elf.json')}
            extra1=origin.parent/'ohm-ron-fixed-whole-native-h4-20261028-supplement-v1/results/fixed-release-rust/extra-1/native-elf.json';supp=origin.parent/'ohm-ron-fixed-whole-native-h4-20261028-supplement-v2/results/fixed-release-rust'
            for f in [extra1,*sorted(supp.glob('extra-*/native-elf.json'))]:targets[f.parent.name]=q.load(f)[str(canonical/link.stem)]
            q.dump(w/'result.json',{'captured_rustc_exec':hashlib.sha256(good[0]).hexdigest(),'recipe_sha256':q.sha(original/link.name),'native':x,'workspace_outputs':targets,'reproduced_one_exact_native':x['oracle'] in targets.values()})
        q.dump(H/'complete.json',{n:q.load(H/n/'result.json')for n in names})
if os.environ.get('WIDTH_REPLAY_MODE')=='interposed':shim()
else:
    try:caller()
    except BaseException:(H/'failure.txt').write_text(traceback.format_exc());raise
