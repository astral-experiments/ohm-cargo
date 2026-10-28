"""Capture the real ELF variants seen in four earlier successful, clock-free ordinary builds."""
from pathlib import Path
import fcntl,hashlib,json,mmap,os,re,shutil,struct,subprocess,sys,traceback

H=Path(__file__).resolve().parent
orig=H.parent/'ohm-ron-fixed-whole-native-h4-20261028-v1'
proto=H.parent/'ohm-noquery-full-native-h4-20261028-v2/protocol'
sys.path.insert(0,str(proto))
import engine as q
key='fixed-release-rust'
st=orig/'states'/key
old=orig/'results'/key
sha=q.sha;load=q.load;dump=q.dump
targets=('document-1dd8f0784781d62c','ty_python_semantic-a879b0690f634244')
def translated(path):
    return st/'target'/Path(path).relative_to(q.TARGET)
def capture(label,roster,all_f):
    digest=load(roster/'native-elf.json')
    info={};rs={}
    for name in targets:
        canonical,=[n for n in digest if Path(n).name==name];actual=translated(canonical);expected=digest[canonical];dest=H/'bodies'/expected
        assert sha(actual)==expected
        if not dest.exists():
            assert shutil.disk_usage(H).free>30*2**30
            with actual.open('rb') as inf,dest.open('xb') as outf:shutil.copyfileobj(inf,outf)
            assert sha(dest)==expected
        stat=actual.stat()
        info[name]={'sha256':expected,'size':stat.st_size,'ino':stat.st_ino,'nlink':stat.st_nlink,'ctime_ns':stat.st_ctime_ns,'mtime_ns':stat.st_mtime_ns}
    bysuffix={f.suffix:f for f in (roster/'ron').glob('libron-*')}
    lib,=list((st/'target').rglob(bysuffix['.rlib'].name))
    delta=lib.parent.parent/'fingerprint'
    for f in [lib,lib.with_suffix('.rmeta'),*lib.parent.glob('ron-*.d'),*delta.iterdir()]:
        if not f.is_file():continue
        v=f.stat();rs[f.name]={'size':v.st_size,'ctime_ns':v.st_ctime_ns,'mtime_ns':v.st_mtime_ns,'ino':v.st_ino,'nlink':v.st_nlink,'sha256':sha(f)}
        assert rs[f.name]['sha256']==sha(roster/'ron'/f.name)
    rec={'date_ns':__import__('time').time_ns(),'ron_generation':rs,'elfs':info,'in_process':False}
    all_f[label]=rec;dump(H/(label+'-files.json'),rec)
def decode(p):
    with p.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as e:
        assert e[:6]==b'\x7fELF\x02\x01';offset=struct.unpack_from('<Q',e,40)[0];width,n,i=struct.unpack_from('<HHH',e,58);assert width==64
        tab=[struct.unpack_from('<IIQQQQIIQQ',e,offset+j*width) for j in range(n)];names=tab[i][4];regions=[];sections={}
        for idx,h in enumerate(tab):
            start=names+h[0];name=e[start:e.find(b'\0',start)].decode();assert name not in sections
            sections[name]={'header':list(h),'data':hashlib.sha256(memoryview(e)[h[4]:h[4]+h[5]]).hexdigest() if h[1]!=8 else None}
            if name=='.rodata':
                regions.append((offset+idx*width+56,8,'sh_entsize'));entsize=h[9]
            if name=='.note.gnu.build-id':
                s=h[4];n_n,sz,k=struct.unpack_from('<III',e,s);assert n_n==4 and k==3 and e[s+12:s+16]==b'GNU\0' and sz+16==h[5]
                regions.append((s+16,sz,'build-id'));build_id=e[s+16:s+16+sz].hex()
        excluded=hashlib.sha256();pos=0;assert len(regions)==2
        for s,sz,kind in sorted(regions):excluded.update(memoryview(e)[pos:s]);pos=s+sz
        excluded.update(memoryview(e)[pos:]);return {'sha256':sha(p),'size':len(e),'rodata_sh_entsize':entsize,'gnu_build_id':build_id,'exact_fields':regions,'every_other_byte_sha256':excluded.hexdigest(),'sections':sections}
def main():
    assert (orig/'rc').read_text().strip()=='0'
    source={n:{load(old/k/'native-elf.json')[next(p for p in load(old/k/'native-elf.json') if Path(p).name==n)] for k in ['cold','unchanged-1','unchanged-2','unchanged-3']} for n in targets}
    for f in ['results','results/'+key,'results/'+key+'/cold','bodies']: (H/f).mkdir()
    for n in ['record.json','native-elf.json']:shutil.copyfile(old/'cold'/n,H/'results'/key/'cold'/n)
    shutil.copyfile(old/'input-commitments.json',H/'results'/key/'input-commitments.json')
    previous=H.parent/'ohm-ron-fixed-whole-native-h4-20261028-supplement-v1'
    assert (previous/'rc').read_text().strip()=='1' and load(previous/'results'/key/'extra-1/status.json')=={'elapsed_ns':None,'rc':0}
    assert 'input-commitments.json' in (previous/'log').read_text()
    # The preceding first native command succeeded; the reporter lacked one copied manifest.
    for artifact in (previous/'bodies').iterdir():shutil.copyfile(artifact,H/'bodies'/artifact.name)
    assert all(sha(f)==f.name for f in (H/'bodies').iterdir())
    opts=load(st/'secure-options.json')
    for a,b in [(H,H),(H/'results',orig/'results'),(st/'target',q.TARGET),(st/'build',q.BUILD),(st/'home',q.CH),(st/'rustup',q.P/'rustup')]:opts+=['--bind',str(a),str(b)]
    subj=load(proto/'subject-binding.json');drv=Path(subj['old_driver']['path'])
    assert sha(drv)=='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955' and sha(orig/'fixed-cargo')=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
    for a,b in [(orig/'fixed-cargo',q.FROZEN/'bin/cargo'),(drv,q.FROZEN/'lib'/q.SONAME)]:opts+=['--ro-bind',str(a),str(b)]
    env=q.env();env.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');env.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');env['CARGO_BUILD_JOBS']='8';env['CARGO_LOG']='cargo::compiler::fingerprint=info'
    files={'initial':load(previous/'initial-files.json')}
    with q.LOCK.open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);capture('extra-1',previous/'results'/key/'extra-1',files)
        for i in range(2,7):
            label='extra-'+str(i)
            subprocess.run([*opts,'--','taskset','-c','0-23','/usr/bin/python3','-IBu',str(orig/'worker.py'),'inside',label],env=env,cwd=q.WT,check=True)
            capture(label,H/'results'/key/label,files)
            if i>=2 and all({v['elfs'][n]['sha256'] for v in files.values()}>=a for n,a in source.items()):break
    decoded={p.name:decode(p) for p in sorted((H/'bodies').iterdir())}
    dump(H/'complete.json',{'seed':{n:sorted(a) for n,a in source.items()},'files':files,'decoded':decoded,'all_earlier_bodies_recovered':all(set(decoded)>=v for v in source.values()),'no_clocks':True})
try:main()
except BaseException:(H/'failure.txt').write_text(traceback.format_exc());raise
