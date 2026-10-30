"""Exercise a current real native search directory on the restored Ruff workspace in the enrolled namespace."""
import argparse
import ast
import collections
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

# These values are supplied by the private independent-run launcher after its ordinary result is sealed.
WORK = OUT = TMP = WILD = RUSTC = None
DISK_FLOOR = MEM_FLOOR = None
CARGO = ['cargo','+ohm','test','--no-run','--locked','--offline','-j4','--message-format=json','-p','ruff_wasm','-p','ruff_source_file']
ASM = b""" .section .text.ohm_crlf_provider,"ax",@progbits
.type .Lobserver,@function
.Lobserver:
    mov $231,%eax
    mov $83,%edi
    syscall
    ud2
.size .Lobserver,.-.Lobserver
.section .init_array,"aw",@init_array
.p2align 3
.quad .Lobserver
.section .note.GNU-stack,"",@progbits
"""
def h(b):
    return hashlib.sha256(b).hexdigest()
def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(p, obj):
    with p.open('x') as stream:json.dump(obj,stream,sort_keys=True,indent=2);stream.write('\n')
def read(p):return json.loads(p.read_bytes())
def health():
    remain = int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
    assert remain > MEM_FLOOR and shutil.disk_usage(OUT).free>DISK_FLOOR and shutil.disk_usage(WORK).free>DISK_FLOOR
def execute(name, cmd, env):
    health()
    with (OUT/(name+'.stdout')).open('xb') as o,(OUT/(name+'.stderr')).open('xb') as e:
        child = subprocess.Popen(cmd,cwd=WORK/'source',env=env,stdout=o,stderr=e,start_new_session=True)
        try:
            start=time.monotonic()
            while child.poll() is None:
                health();assert time.monotonic()-start<3600;time.sleep(.4)
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    write(OUT/(name+'.status.json'),{'exit':child.returncode,'argv':[str(x) for x in cmd]})
    return child.returncode
def joined(text):
    pending=None
    for line in text.splitlines():
        if line.endswith('<unfinished ...>'):
            assert pending is None; pending=line[:line.rfind('<unfinished ...>')];continue
        if line.startswith('<... ') and ' resumed>' in line:
            assert pending is not None
            before,_,tail=line.partition(' resumed>');assert before[5:]==pending.split('(',1)[0]; line=pending+tail;pending=None
        yield line
    if pending is not None:assert not pending.startswith(('execve(','openat(','clone(','clone3(')),pending[:70]
def physical(tr, provider):
    graph=collections.defaultdict(set); opens=set(); core=[];raw={}
    for p in sorted(tr.glob('exec.*')):
        pid=int(p.name.rsplit('.',1)[1]);body=p.read_bytes()
        raw[str(pid)]=body.decode()
        for line in joined(body.decode()):
            born=re.match(r'(?:clone|clone3|fork|vfork)\(.*\)\s+= (\d+)$',line)
            if born:graph[pid].add(int(born[1]));continue
            if not re.search(r'\)\s+= \d+$',line):continue
            if line.startswith('openat('):
                m=re.match(r'openat\([^,]+, ("(?:[^"\\]|\\.)*"), (?:O_RDONLY|O_RDWR)',line)
                if m and ast.literal_eval(m[1])==str(provider):opens.add(pid)
                continue
            if not line.startswith('execve(') or not line.endswith('= 0'):continue
            m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), .*\)\s+= 0',line);assert m
            fp=Path(ast.literal_eval(m[1]));argv=ast.literal_eval(m[2])
            if not fp.is_absolute() or not fp.is_file():continue
            if fp.samefile(WILD):role='wild'
            elif fp.samefile(RUSTC):role='rustc'
            elif fp.name in ('cc','gcc','collect2'):role=fp.name
            else:continue
            core.append({'pid':pid,'kind':role,'program':str(fp),'argv':argv})
    def family(pid):
        seen={pid};todo=[pid]
        while todo:
            new=graph[todo.pop()]-seen;seen.update(new);todo.extend(new)
        return seen
    links=[]
    for j in core:
        if j['kind']=='wild':
            argv=j['argv'];path=argv[argv.index('-o')+1];links.append({'out':path,'wild_pid':j['pid'],'actual_provider_open_pids':sorted(opens&family(j['pid']))})
    return raw,core,links
def main():
    global WORK,OUT,TMP,WILD,RUSTC,DISK_FLOOR,MEM_FLOOR
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('work','sdk','out','ordinary'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--arm',choices=('W','F'),required=True)
    ap.add_argument('--cpus',required=True);ap.add_argument('--min-free-gib',type=int,required=True);ap.add_argument('--min-memory-gib',type=int,required=True)
    a=ap.parse_args();arm=a.arm;WORK=a.work.resolve(strict=True);OUT=a.out.absolute();TMP=WORK/'tmp/native-provider-study'
    assert not OUT.exists() and OUT.parent.is_dir() and not TMP.exists() and os.getuid()!=0
    cpus={int(x) for x in a.cpus.split(',')};assert len(cpus)==4 and cpus<=os.sched_getaffinity(0);os.sched_setaffinity(0,cpus)
    MEM_FLOOR=a.min_memory_gib*2**30;DISK_FLOOR=a.min_free_gib*2**30
    if min(MEM_FLOOR,DISK_FLOOR)<=0 or shutil.disk_usage(OUT.parent).free<=DISK_FLOOR+2*2**30:raise RuntimeError('insufficient native control reserve')
    sdk=a.sdk.resolve(strict=True);WILD=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';RUSTC=sdk/'bin/rustc'
    base=a.ordinary.resolve(strict=True)
    old=read(base/'input.json');assert old['arm']==arm and old['wild']==sha(WILD) and old['cargo']==sha(sdk/'bin/cargo')
    driver,=(sdk/'lib').glob('librustc_driver-*.so');assert old['driver']==sha(driver)
    for name,actual in [('rustc',RUSTC),('cargo',sdk/'bin/cargo')]:
        assert Path(subprocess.check_output(['rustup','which','--toolchain','ohm',name],text=True).strip()).samefile(actual)
    OUT.mkdir(mode=0o700);TMP.mkdir(mode=0o700)
    env={k:os.environ[k] for k in ('HOME','PATH','RUSTUP_HOME')}
    env.update(CARGO_HOME=str(WORK/'cargo-home'),CARGO_TARGET_DIR=str(WORK/'target'),CARGO_BUILD_BUILD_DIR=str(WORK/'shared'),CARGO_NET_OFFLINE='true',CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never',RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',TMPDIR=str(WORK/'tmp'),INSTA_UPDATE='no',LC_ALL='C',TZ='UTC')
    rt=read(base/'terminal.json'); assert rt['arm']==arm
    raw_rows=[json.loads(row) for row in gzip.decompress((base/'restored.stdout.gz').read_bytes()).splitlines()]
    def locate(name, suffix):
        vals={Path(f) for r in raw_rows if r.get('reason')=='compiler-artifact' and r['target']['name']==name and 'ruff_wasm' in r['package_id'] for f in r['filenames'] if f.endswith(suffix)}
        p,=vals;assert p.resolve(strict=True).is_relative_to(WORK);return p
    api,={Path(r['executable']) for r in raw_rows if r.get('reason')=='compiler-artifact' and r['target']['name']=='api' and r.get('executable') and 'ruff_wasm' in r['package_id']}
    so=locate('ruff_wasm','.so')
    root,={Path(r['executable']) for r in raw_rows if r.get('reason')=='compiler-artifact' and r['target']['name']=='ruff_source_file' and r.get('executable')}
    original=rt['results']['restored']['product'];assert sha(api)==original['api'] and sha(root)==original['root']
    selected={}; outputs={'api':api,'so':so};dirs={}
    for j in read(base/'restored.json')['wild']:
        a=j['argv'];out=Path(a[a.index('-o')+1])
        for n,typed in outputs.items():
            if out.exists() and out.samefile(typed):
                assert n not in selected and '-lgcc_s' in a
                selected[n]=out
                dirs[n],=[Path(s[2:]) for s in a if s.startswith('-L') and '/psm/' in s and s.endswith('/out')]
                assert a.index('-L'+str(dirs[n])) < next(i for i,s in enumerate(a) if s.startswith('-L/usr/lib/gcc/'))
    assert set(selected)==set(outputs) and dirs['api']==dirs['so']
    folder=dirs['api'];assert folder.resolve(strict=True).is_relative_to(WORK) and folder.stat().st_dev==WORK.stat().st_dev
    prov=folder/'libgcc_s.so';assert not prov.exists() and not prov.is_symlink()
    script=Path(subprocess.check_output(['/usr/bin/cc','-print-file-name=libgcc_s.so'],text=True).strip());assert script.is_absolute() and script.is_file() and b'libgcc_s.so.1' in script.read_bytes();STD_SHA=sha(script)
    src=TMP/'provider.s';obj=TMP/'provider.o';src.write_bytes(ASM)
    assert execute('assemble',['/usr/bin/as','--64',src,'-o',obj],env)==0
    good=b'INPUT ( "'+os.fsencode(obj)+b'" )\n'+script.read_bytes();bad=b'OHM_CRLFWASM_MALFORMED_PROVIDER (\n'
    write(OUT/'basis.json',{'selector':str(folder),'system':str(script),'script_sha256':sha(script),'source_sha256':sha(src),'object_sha256':sha(obj),'valid':h(good),'bad':h(bad),'canonical_outputs':{n:str(x) for n,x in selected.items()},'typed_outputs':{n:str(x) for n,x in outputs.items()},'sdk_wild':sha(WILD),'rustc':sha(RUSTC),'baseline':original,'typed_so_sha256':sha(so)})
    so_start=sha(so);rows={}
    def verdict(label, code):
        status1=execute(label+'-api',[api,'--list'],env)
        status2=execute(label+'-native-so',['/usr/bin/python3','-IB','-c','import ctypes,os,sys;ctypes.CDLL(sys.argv[1],mode=os.RTLD_LAZY|os.RTLD_LOCAL)',so],env)
        assert (status1,status2)==(code,code),(label,status1,status2)
        return [status1,status2]
    def visit(name,kind,force=False):
        if force:
            for p in set((*selected.values(),*outputs.values())):
                assert p.absolute().is_relative_to(WORK) and (not p.exists() or p.is_file() and not p.is_symlink())
                if p.exists():
                    assert any(p.resolve().is_relative_to(WORK/x) for x in ('target','shared'))
                    backups=OUT/(name+'-before');backups.mkdir(exist_ok=True)
                    backup=backups/(str(len(list(backups.iterdir())))+'.elf')
                    inode=p.stat().st_ino;shutil.copyfile(p,backup);assert p.stat().st_ino==inode and sha(backup)==sha(p);p.unlink()
        if kind=='regular':assert not prov.exists() and not prov.is_symlink()
        else:assert prov.read_bytes()==(good if kind=='good' else bad)
        tr=TMP/(name+'-trace');tr.mkdir()
        rc=execute(name,['/usr/bin/strace','-ff','-qq','-s','131072','-e','trace=execve,clone,clone3,fork,vfork,openat','-o',tr/'exec',*CARGO],env)
        raw,core,links=physical(tr,prov)
        tape=gzip.compress(json.dumps(raw,sort_keys=True,separators=(',',':')).encode(),compresslevel=2,mtime=0)
        with (OUT/(name+'.trace.json.gz')).open('xb') as f:f.write(tape)
        implicated={n:[pid for j in links if j['out']==str(x) for pid in j['actual_provider_open_pids']] for n,x in selected.items()}
        row={'exit':rc,'receipt':h(tape),'provider_open_pids':implicated,'native':core,'links':links,'forced':force,'kind':kind}
        write(OUT/(name+'.native.json'),row)
        js=[json.loads(line) for line in (OUT/(name+'.stdout')).read_bytes().splitlines()]
        assert js[-1]=={'reason':'build-finished','success':kind!='bad'} and rc==(101 if kind=='bad' else 0),(name,rc)
        if kind=='good':
            assert all(implicated.values()),(name,implicated)
        if kind=='bad':
            assert any(implicated.values()) and (b'libgcc_s.so' in (OUT/(name+'.stdout')).read_bytes() or b'libgcc_s.so' in (OUT/(name+'.stderr')).read_bytes()),(name,implicated)
        else:
            out={n:sha(p) for n,p in outputs.items()};row['products']=out;row['runtime']=verdict(name,83 if kind=='good' else 0)
            assert sha(root)==original['root']
            if kind=='regular':
                assert out=={'api':original['api'],'so':so_start},out
            else:
                assert out['api']!=original['api'] and out['so']!=so_start
        rows[name]=row
    try:
        assert verdict('original',0)==[0,0]
        with prov.open('xb') as f:f.write(good)
        visit('valid','good');visit('forced-valid','good',True);assert rows['valid']['products']==rows['forced-valid']['products']
        prov.write_bytes(bad);visit('malformed','bad');visit('forced-malformed','bad',True)
        prov.unlink();visit('restored','regular')
        reader=WORK/'tmp/reader'
        assert sha(reader)==original['reader'] and execute('restored-public-reader',[reader],env)==0
        assert (OUT/'restored-public-reader.stdout').read_text().strip()==original['verdict']=='1 1 1 0'
    finally:
        if prov.exists():
            assert not prov.is_symlink() and prov.read_bytes() in (good,bad);prov.unlink()
        assert sha(script)==STD_SHA
    write(OUT/'terminal.json',{'arm':arm,'original':original,'visits':{k:{q:v[q] for q in ('exit','receipt','forced','kind','products','runtime','provider_open_pids') if q in v} for k,v in rows.items()},'private_provider_absent':not prov.exists(),'original_system_sha256':sha(script)})
if __name__=='__main__':
    main()

