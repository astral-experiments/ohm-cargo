"""Supplement the original phase receipts with real stdout and native section hashes from the remaining layout."""
from pathlib import Path
import fcntl,gzip,json,shutil,struct,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
import run_data as trace
dir=q/'unicode-lifetime-v1';sdir=dir/'run-output-supplement';sdir.mkdir();plan=json.loads((q/'ops/unicode-plan.json').read_bytes())
def sections(f):
    v=f.read_bytes();assert v[:6]==b'\x7fELF\x02\x01';off=struct.unpack_from('<Q',v,40)[0];w,n,ii=struct.unpack_from('<HHH',v,58);sh=[struct.unpack_from('<IIQQQQIIQQ',v,off+i*w)for i in range(n)];tab=sh[ii];ss=v[tab[4]:tab[4]+tab[5]];return {ss[s[0]:ss.index(0,s[0])].decode():[s[5],H(v[s[4]:s[4]+s[5]])]for s in sh if s[1]!=8}
def read(n):return json.loads(n.read_bytes())
with(p/'native-measure.lock').open('rb')as lk:
    fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);assert (dir/'complete.json').is_file()
    for phase in ('original','edited','restored'):
        d=sdir/phase;d.mkdir()
        if phase!='original':
            go(['git','apply',*(['-R'] if phase=='edited'else []),q/'ops/unicode.patch'])
            (d/'trace').mkdir();monitor(['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/run',*plan['command']],d/'cargo.stdout',d/'cargo.stderr')
            j=trace.jobs(d);put(d/'jobs.json',j);actual=[(v['kind'],v['name'])for v in j];expected=read(dir/phase/'result.json')['procs'];assert sorted(actual)==sorted(map(tuple,expected)),actual
            wf,=[v for v in j if v['kind']=='wild' and v['name']=='build_script_build'];native=Path(wf['out']);assert sha(native)==wf['out_digest'][1]
        else:
            old=read(dir/'restored'/'jobs.json');j=[];native=Path(next(v['out']for v in old if v['kind']=='wild' and v['name']=='build_script_build'))
        assert sha(w/plan['file'])==plan['edited'if phase=='edited'else'original']
        orig=read(dir/phase/'generated.json');od=Path(orig['typed']['out_dir']);outroot=od.parent/'run';assert all(sha(od/f)==row['sha']for f,row in orig['files'].items())
        ch={}
        for name in ('stdout','stderr','root-output'):
            f=outroot/name;sz=f.stat().st_size;v=f.read_bytes();(d/('script.'+name)).write_bytes(v);ch[name]={'bytes':sz,'sha':H(v),'path':str(f)}
        assert b'cargo:rerun-if-changed=build.rs' in (d/'script.stdout').read_bytes()
        cli=t/'debug/ruff';objroot=next(Path(v['out_dir'])for v in read(dir/'edited'/'jobs.json')if v['kind']=='partial');rl,=objroot.glob('*.rlink')
        codegen={str(f):sha(f)for f in sorted(objroot.glob('*.rlink-objects/*.o'))};assert len(codegen)==22
        snap=(dir/'private-final-elves'/(phase+'-script.gz'))
        with native.open('rb')as src,snap.open('wb')as raw,gzip.GzipFile(filename='',mode='wb',compresslevel=2,fileobj=raw,mtime=0)as gz:shutil.copyfileobj(src,gz,1<<20)
        with gzip.open(snap,'rb')as z:assert hashlib.file_digest(z,'sha256').hexdigest()==sha(native)
        a={'phase':phase,'status':0,'source':sha(w/plan['file']),'run_files':ch,'typed_generated':orig['files'],'script':{'sha':sha(native),'bytes':native.stat().st_size,'sections':sections(native),'gz_sha':sha(snap)},'cli':{'sha':sha(cli),'sections':sections(cli),'rlink':sha(rl),'objects':codegen}};put(d/'result.json',a);print(phase,a['script']['sha'],a['cli']['sha'],[(k,v['sha'])for k,v in ch.items()],flush=True)
    assert not git('diff','--name-only')and git('rev-parse','HEAD').decode().strip()==plan['pin'];put(sdir/'complete.json',{'status':0,'end':plan['pin'],'full_additional_cargo_commands':2,'first_source_read_only':True})
