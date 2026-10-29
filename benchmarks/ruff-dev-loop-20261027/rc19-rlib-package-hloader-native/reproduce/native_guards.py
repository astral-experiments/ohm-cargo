"""True GNU archives, native C consumers, one-shot mapped inputs, and the kernel size limit."""
from pathlib import Path
from contextlib import ExitStack
import errno,hashlib,json,os,resource,select,shutil,stat,subprocess as sp
def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def native_suite(root,work,shared):
    g=work/'native-guards-v2';g.mkdir();d=g/'sources';d.mkdir()
    (d/'consumer.c').write_text('#include <stdio.h>\nextern int answer(void); int main(void){printf("%d\\n", answer());}\n')
    archives={}
    for answer in (17,29):
        (d/'answer.c').write_text(f'int answer(void){{return {answer};}}\n')
        sp.run(['cc','-O1','-c','answer.c','-o','answer.o'],cwd=d,check=True)
        lib=d/f'{answer}.a';sp.run(['ar','rcsD',lib,'answer.o'],cwd=d,check=True);archives[answer]=lib.read_bytes()
    assert set(map(len,archives.values()))=={len(archives[17])} and archives[17]!=archives[29]
    writer=g/'mini-writer';sp.run(['cc','-O2','-Wall','-Wextra','-Werror',root/'qa_writer.c','-o',writer],check=True)
    results={}
    def test(tag,mode,prior_kind,start,swap=None,limit=False,failpub=False,limited_regular=False):
        folder=g/tag;folder.mkdir();out=folder/'out';out.mkdir();tempdir=out/'.tmpA9b8Cd.temp-archive';tempdir.mkdir();tmp=tempdir/'tmp.a';final=out/'libruff_linter-ff00.rlib'
        source=folder/'mapped-input.a';source.write_bytes(archives[start]);old=folder/'old';old.write_bytes(archives[17]);origin=folder/'prior'
        if prior_kind=='valid':os.link(old,origin)
        elif prior_kind=='wrong-magic':origin.write_bytes(b'bad magic'+b'a'*1400)
        elif prior_kind=='symlink':origin.symlink_to(old)
        elif prior_kind=='fifo':os.mkfifo(origin)
        elif prior_kind=='directory':origin.mkdir()
        elif prior_kind=='larger':origin.write_bytes(archives[17]+b'old-tail'*181)
        elif prior_kind=='smaller':origin.write_bytes(archives[17][:987])
        elif prior_kind=='missing':pass
        else:raise AssertionError(prior_kind)
        if failpub:final.mkdir()
        l=origin.lstat()if origin.exists()or origin.is_symlink()else old.stat()
        e={**os.environ,'QA_INPUT':str(source),'QA_TMP':str(tmp),'QA_FINAL':str(final),'OHM_AR_RUSTC':str(writer),'OHM_AR_CRATE':'ruff_linter','OHM_AR_OUT':str(out),'OHM_AR_FINAL':str(final),'OHM_AR_PRIOR':str(origin),'OHM_AR_PRIOR_DEV':str(l.st_dev),'OHM_AR_PRIOR_INO':str(l.st_ino),'OHM_AR_LOG':str(folder/'io.jsonl'),'OHM_AR_REFERENCE':str(folder/'reference.a')}
        if mode!='stock':e.update({'LD_PRELOAD':str(shared),'OHM_AR_MODE':mode})
        if limit:e['QA_LIMIT']='512'
        if swap is not None:
            a=folder/'arrived';b=folder/'release';os.mkfifo(a);os.mkfifo(b);e.update(OHM_AR_QA_ARRIVED=str(a),OHM_AR_QA_RELEASE=str(b))
        args=[writer,'--crate-name','ruff_linter','--crate-type','lib','--emit=dep-info,metadata,link','--out-dir',out,'-C','extra-filename=-ff00']
        with ExitStack()as closer:
            pipe_log=limit and mode!='stock' and not limited_regular
            passed=()
            if pipe_log:
                log_read,log_write=os.pipe();closer.callback(os.close,log_read);e['OHM_AR_QA_LOG_FD']=str(log_write);passed=(log_write,)
            if swap is not None:
                ar=os.open(a,os.O_RDWR|os.O_NONBLOCK);closer.callback(os.close,ar)
                br=os.open(b,os.O_RDWR|os.O_NONBLOCK);closer.callback(os.close,br)
            proc=sp.Popen(args,cwd=folder,env=e,stdout=sp.PIPE,stderr=sp.PIPE,pass_fds=passed)
            if pipe_log:os.close(log_write)
            if swap is not None:
                assert select.select([ar],[],[],15)[0] and os.read(ar,1)==b'1',(tag,'no file-acquisition signal',proc.poll())
                before=source.stat()
                with source.open('r+b')as f:f.write(archives[swap]);f.flush();os.fsync(f.fileno())
                os.utime(source,ns=(before.st_atime_ns,before.st_mtime_ns))
                assert (source.stat().st_ino,source.stat().st_size,source.stat().st_mtime_ns)==(before.st_ino,before.st_size,before.st_mtime_ns)
                os.write(br,b'1')
            so,se=proc.communicate(timeout=20)
            if pipe_log:
                chunks=[] 
                while (part:=os.read(log_read,65536)):chunks.append(part)
                (folder/'io.jsonl').write_bytes(b''.join(chunks))
        assert proc.returncode==(11 if failpub else 0),(tag,proc.returncode,so,se)
        ks=[int(v)for v in so.split()];assert len(ks)==7,(tag,ks)
        if limit:assert ks[:6]==[512,0,-1,errno.EFBIG,1,0],(tag,ks)
        else:assert ks[:6]==[len(archives[start]),0,0,0,0,0],(tag,ks)
        assert ks[6]==(-1 if failpub else 0)
        body=tmp if failpub else final
        expected=archives[start][:512] if limit else archives[start]
        assert body.read_bytes()==expected,(tag,sha(body),hashlib.sha256(expected).hexdigest())
        receipt=None;ref=folder/'reference.a'
        if mode!='stock' and not limited_regular:
            events=[json.loads(z)for z in (folder/'io.jsonl').read_text().splitlines()];last=events[-1]
            assert len(events)==4 and last['found_output']==1 and not last['fatal_errno']and last['publications']==1,(tag,events)
            if not limit:assert not last['reference_errno']and ref.read_bytes()==expected
            assert last['did_clone']==int(mode=='cow'and not limit and prior_kind in ('valid','larger','smaller')),(tag,last)
            if prior_kind in ('symlink','missing'):assert last['decision']=='prior-open'
            if prior_kind in ('fifo','directory'):assert last['decision']=='prior-type-identity'
            if prior_kind=='wrong-magic':assert last['decision']=='prior-magic'
            if limit:assert last['decision']=='finite-fsize'
            if swap and mode=='cow':assert last['skipped_bytes']==(len(expected)if start==17 else 0)
            receipt=last
        native=None
        if not limit:
            binary=folder/'run';sp.run(['cc',d/'consumer.c',body,'-o',binary],check=True)
            native=int(sp.check_output([binary]));assert native==start
        results[tag]={'exit':proc.returncode,'syscall_observation':ks,'required_input_sha256':hashlib.sha256(expected).hexdigest(),'body':sha(body),'input_after':sha(source),'reference':sha(ref) if ref.is_file()and not limit else None,'native':native,'io':receipt}
    for arm in ('stock','observe','cow'):
        test(arm+'-unlimited',arm,'valid',17)
        test(arm+'-limited',arm,'valid',17,limit=True)
        test(arm+'-rename-error',arm,'valid',29,failpub=True)
    for arm in ('observe','cow'):test(arm+'-limited-regular-log',arm,'valid',17,limit=True,limited_regular=True)
    for k in ['wrong-magic','symlink','fifo','directory','missing','larger','smaller']:
        test('cow-'+k,'cow',k,29)
    for a,b in [(17,29),(29,17)]:
        for arm in ['observe','cow']:test(f'{arm}-sync-{a}-{b}',arm,'valid',a,swap=b)
    (root/'reports/native-guards-v2.json').write_text(json.dumps({'cases':results,'writer':sha(writer),'case_count':len(results),'shared':sha(shared),'file_size':len(archives[17])},sort_keys=True,indent=2)+'\n')
