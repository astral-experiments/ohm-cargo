"""Replay Ruff's actual registry compiler invocations, writing only to a private per-run output dir."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys,tempfile,traceback
H=Path(__file__).resolve().parent
base=Path.home()/'.cache/ohm-noquery-full-native-h4-20261028-v2'
sys.path.insert(0,str(base/'protocol'));import engine as eng
st=base/'states/unscored-B';jobs=base/'results/unscored-B/cold'
old=base.parent/'ohm-noquery-full-native-h4-20261028-v1/results/unscored-B/first'
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
J=lambda p:json.loads(p.read_bytes())
def dump(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def captured(d):
    hits=[]
    for f in sorted((d/'trace').glob('exec.*')):
        for l in f.read_bytes().splitlines():
            if b'"--crate-name", "ron"' not in l or not re.search(rb'\)\s+= 0$',l):continue
            m=re.search(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',l)
            assert m,(f.name,l[:50]);args=ast.literal_eval(m[2].decode());assert args[0]==ast.literal_eval(m[1].decode())
            if '--crate-name' in args and args[args.index('--crate-name')+1]=='ron':hits.append((args,hashlib.sha256(l).hexdigest(),f.name))
    assert len(hits)==1;return hits[0]
def files(d):
    product={}
    for f in sorted(d.iterdir()):
        if f.is_file():
            desc=dict(bytes=f.stat().st_size,sha256=sha(f))
            if f.suffix=='.rlib':
                members=subprocess.check_output(['ar','t',f],text=True).splitlines()
                assert len(members)==len(set(members));desc['ordered_members']=[]
                for n in members:
                    raw=subprocess.check_output(['ar','p',f,n]);desc['ordered_members'].append([n,len(raw),hashlib.sha256(raw).hexdigest()])
            product[f.name]=desc
    return product
def native_data(record):return {k:v for k,v in record.items() if k.endswith(('.rlib','.rmeta'))}
try:
    assert int((base/'native.rc').read_text())==1 and int(J(jobs/'status.json')['rc'])==0
    normal,sig1,pid1=captured(jobs);explicit,sig2,pid2=captured(old)
    assert explicit[:len(normal)]==normal and explicit[len(normal):]==['-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=blake3']
    out=Path(normal[normal.index('--out-dir')+1]);assert out.is_relative_to(eng.TARGET)
    dat=st/'target'/out.relative_to(eng.TARGET);initial=files(dat);dump(H/'donor.json',initial)
    assert len(native_data(initial))==2
    ext=[normal[i+1] for i,w in enumerate(normal) if w=='--extern'];assert len(ext)==6
    def physical(path):
        for anchor,n in [(eng.TARGET,'target'),(eng.BUILD,'build'),(eng.CH,'home')]:
            if path.is_relative_to(anchor):return st/n/path.relative_to(anchor)
        return path
    source=next(Path(a) for a in normal if a.endswith('/ron-0.12.0/src/lib.rs'));fp={v.split('=',1)[0]:sha(physical(Path(v.split('=',1)[1]))) for v in ext};assert not any('incremental' in x for x in normal)
    # Recover the actual compilation working directory from a debug info member from this precise Cargo job.
    ar,=dat.glob('libron-*.rlib');members=subprocess.check_output(['ar','t',ar],text=True).splitlines();cgu=next(n for n in members if n.endswith('.rcgu.o'))
    obj=H/'captured-member.o';obj.write_bytes(subprocess.check_output(['ar','p',ar,cgu]))
    dw=subprocess.check_output(['readelf','--debug-dump=info',obj],stderr=subprocess.DEVNULL,text=True)
    m=re.search(r'DW_AT_comp_dir\s*:\s*(?:\([^\n]*?\):\s*)?(/[^\n]+)',dw)
    assert m,'missing producer comp_dir';cwd=Path(m[1].strip());assert cwd==eng.WT or cwd==source.parents[1],str(cwd)
    sign={k:v for k,v in [('normal_argv_sha256',sig1),('explicit_argv_sha256',sig2),('normal_trace',pid1),('explicit_trace',pid2),('externs',fp),('source',sha(physical(source))),('working_directory','ruff-workspace' if cwd==eng.WT else 'ron-package'),('new_driver_exact_artifact_context',True)]}
    dump(H/'inputs.json',sign)
    arm,drv=eng.arm_subject('B');base_ns=eng.load(st/'secure-options.json')
    for fr,to in [(st/'target',eng.TARGET),(st/'build',eng.BUILD),(st/'home',eng.CH),(st/'rustup',eng.P/'rustup'),(arm['path'],eng.FROZEN/'bin/cargo'),(drv['path'],eng.FROZEN/'lib'/eng.SONAME)]:base_ns+=['--ro-bind',str(fr),str(to)]
    osenv=eng.env();osenv.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');osenv.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');osenv.update(CARGO_BUILD_JOBS='8',CARGO_MANIFEST_DIR=str(source.parents[1]),CARGO_MANIFEST_PATH=str(source.parents[1]/'Cargo.toml'),CARGO_PKG_NAME='ron',CARGO_PKG_VERSION='0.12.0',CARGO_CRATE_NAME='ron')
    sequence=['normal1','normal2','explicit1','explicit2','normal3'];summary={}
    for label in sequence:
        rec=H/label;rec.mkdir();write=rec/'out';write.mkdir()
        argv=explicit if label.startswith('explicit') else normal
        with (rec/'stdout').open('xb') as so,(rec/'stderr').open('xb') as se:
            pr=subprocess.run([*base_ns,'--bind',str(write),str(out),'--chdir',str(cwd),'--','taskset','-c','4-11',*argv],env=osenv,stdout=so,stderr=se,timeout=120)
        assert pr.returncode==0,(label,(rec/'stderr').read_text()[-600:])
        rr=files(write);dump(rec/'products.json',rr)
        assert len(native_data(rr))==2
        summary[label]=dict(exact_native_with_donor=native_data(rr)==native_data(initial),raw_sha256={k:v['sha256'] for k,v in rr.items()},source_digests={k:v for k,v in fp.items()})
    assert files(dat)==initial
    dump(H/'complete.json',{'donor_untouched':True,'sequence':summary,'normal_replicated_capture':summary['normal1']['exact_native_with_donor'],'same_ordinary_products':J(H/'normal1/products.json')==J(H/'normal2/products.json')==J(H/'normal3/products.json'),'same_explicit_products':J(H/'explicit1/products.json')==J(H/'explicit2/products.json')})
except BaseException:(H/'failure.txt').write_text(traceback.format_exc());raise
