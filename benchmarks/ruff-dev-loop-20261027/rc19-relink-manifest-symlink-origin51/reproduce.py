#!/usr/bin/env python3
"""Reproduce the original Cargo relink record's initialization and refresh handoff."""
import argparse
import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import struct
import subprocess
import sys
import time

FRONTEND = {'head':'6a89ea01e1f5689919845cbe619f4d6ece36193d63f3839508d27cc8b9171511','parent':'5b9c30978ad2145ef9a237d47ba10d36b7e55fc266568384b12d3b70dd40bde1'}
COMMITS = {'head':'caac2566f0fbdf3984f519c2141a6d78e18b01b2','parent':'30004d93bdf3b07003fb8cd7097be81d862a9f41'}
def hash_stream(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hb(b):return hashlib.sha256(b).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def watch(path):
    libc=ctypes.CDLL(None,use_errno=True);fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    if fd<0 or libc.inotify_add_watch(fd,os.fsencode(path),0x200)<0:raise OSError(ctypes.get_errno(),path)
    return fd
def place_on_delete(fd,path,sentinel,proc):
    poll=select.poll();poll.register(fd,select.POLLIN)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if not poll.poll(50):
            if proc.poll() is not None:break
            continue
        buf=os.read(fd,65536);pos=0
        while pos+16<=len(buf):
            _,mask,_,length=struct.unpack_from('iIII',buf,pos);start=pos+16;pos=start+length
            if mask&0x200 and buf[start:pos].split(b'\0')[0]==os.fsencode(path.name):
                assert not path.exists() and not path.is_symlink()
                path.symlink_to(sentinel);assert path.samefile(sentinel)
                return {'mask':mask,'name':path.name,'time_ns':time.time_ns()}
    raise RuntimeError('no matching inotify delete')
def native_execution(logs):
    jobs=[]
    for f in sorted(logs.glob('trace.*')):
        for line in f.read_text(errors='replace').splitlines():
            m=re.match(r'^(\d+\.\d+) execve\("([^"]+)", (\[.*?\]), .*\)\s*= 0$',line)
            if not m:continue
            exe=Path(m[2]);args=ast.literal_eval(m[3]);name=exe.name
            if name=='rustc' and '--crate-name' in args:
                unit=args[args.index('--crate-name')+1]
                jobs.append({'time':m[1],'kind':'rustc','binary':hash_stream(exe),'unit':unit,'link_only':any(x=='link-only' or x=='-Zlink-only' for x in args),'no_link':any(x=='no-link' or x=='-Zno-link' for x in args),'public_hash':'-Zpublic-api-hash' in args,'argv_sha256':hb(json.dumps(args,separators=(',',':')).encode())})
            elif name in ('cc','gcc','collect2','ld','ld.bfd','ld.lld','rust-lld','wild') and '-o' in args:
                out=Path(args[args.index('-o')+1]).name
                if out=='probe' or out.startswith('probe-'):
                    jobs.append({'time':m[1],'kind':'link','executable':name,'binary':hash_stream(exe),'output':out,'argv_sha256':hb(json.dumps(args,separators=(',',':')).encode())})
    return jobs
def fs_events(logs,manifest,victim):
    events=[]
    if not manifest:return events
    paths=[(manifest,'manifest')]+([(victim,'victim')] if victim else [])
    for f in sorted(logs.glob('trace.*')):
        for line in f.read_text(errors='replace').splitlines():
            stamp,_,rest=line.partition(' ')
            match=re.match(r'(unlinkat|unlink|renameat2|renameat|rename|openat|readlinkat|readlink)\(',rest)
            if not match:continue
            roles=[role for path,role in paths if '"'+str(path)+'"' in line]
            if roles:events.append({'time':stamp,'call':match[1],'paths':roles,'result':rest.rsplit(' = ',1)[-1].split(' ',1)[0],'raw_line_sha256':hb(line.encode())})
    return sorted(events,key=lambda z:z['time'])

def study(root,sdk,mode,traced):
    root=root.absolute();sdk=sdk.resolve(strict=True)
    assert not root.exists() and root.parent.is_dir() and os.geteuid()!=0
    scope='parent' if mode.startswith('parent') else 'head'
    assert hash_stream(sdk/'bin/cargo')==FRONTEND[scope]
    assert hash_stream(sdk/'bin/rustc')=='e173035a5dd384e17ca6a178e1987a0a746260c3669459cfab3af580880927ba'
    assert shutil.disk_usage(root.parent).free>25*2**30
    root.mkdir(mode=0o700);project=root/'project';(project/'src').mkdir(parents=True);(project/'producer/src').mkdir(parents=True)
    (root/'private-rustup/toolchains').mkdir(parents=True);(root/'private-rustup/toolchains/ohm').symlink_to(sdk)
    cargo=shutil.which('cargo');assert cargo
    env={'HOME':str(root),'PATH':os.environ['PATH'],'LANG':'C','RUSTUP_TOOLCHAIN':'ohm','RUSTUP_AUTO_INSTALL':'0','RUSTUP_HOME':str(root/'private-rustup'),'CARGO_HOME':str(root/'cargo-home'),'CARGO_TARGET_DIR':str(root/'products'),'CARGO_BUILD_BUILD_DIR':str(root/'build-store'),'CARGO_NET_OFFLINE':'true','CARGO_INCREMENTAL':'0','CARGO_TERM_COLOR':'never'}
    origin=subprocess.check_output([cargo,'+ohm','-Vv'],cwd=project,env=env).decode()
    assert COMMITS[scope] in origin
    (project/'Cargo.toml').write_text('[package]\nname="probe"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nproducer={path="producer"}\n')
    (project/'producer/Cargo.toml').write_text('[package]\nname="producer"\nversion="0.1.0"\nedition="2024"\n')
    app=project/'src/main.rs';lib=project/'producer/src/lib.rs'
    def update_app(offset):app.write_text(f'fn main() {{ println!("{{}}",producer::value()+{offset}u32); }}\n')
    def update_lib(value):lib.write_text(f'#[inline(never)]\npub fn value() -> u32 {{ {value} }}\n')
    update_app(0);update_lib(17)
    args=[cargo,'+ohm']
    if mode not in ('parent-plain','head-plain'):args+=['--config','build.rustflags=["-Zpublic-api-hash"]']
    enabled=mode=='head-relink'
    if enabled:args+=['-Zrelink-only']
    args+=['build','--offline','-j1','--bin','probe','--message-format=json']
    cmd_arg=json.loads(json.dumps(args)); cmd_arg[0]='cargo'
    input_hash=lambda:{'app':hash_stream(app),'producer':hash_stream(lib)}
    records=[];manifest=None
    if mode in ('head-relink','parent-plain'):
        for literal in (['-Zrelink-only=yes'] if enabled else ['-Zrelink-only','-Zrelink-only=yes']):
            check=subprocess.run([cargo,'+ohm',literal,'build','--offline'],env=env,cwd=project,capture_output=True)
            (root/(literal.lstrip('-')+'.stderr')).write_bytes(check.stderr)
            assert check.returncode==101 and ('does not take a value' if enabled else 'unknown') in check.stderr.decode()
    def run(phase,value,method=None):
        nonlocal manifest
        assert shutil.disk_usage(root).free>25*2**30
        out=root/phase;out.mkdir()
        victim=None;prior=None;fd=None;observed=None
        if method:
            victim=out/'owned-sentinel'
            if method=='pre-valid':
                assert manifest.is_file()
                old=json.loads(manifest.read_bytes())
                old['owner_note']='private marker preceding a dependency-only rebuild'
                prior=(json.dumps(old,indent=2)+'\n').encode()
            else:prior=('private ordinary '+phase+'\n').encode()
            victim.write_bytes(prior);(out/'sentinel-before.bin').write_bytes(prior); before=victim.stat()
            if method=='during':fd=watch(manifest.parent)
            else:
                # Only the disposable fixture's own sidecar may be replaced.
                assert root in manifest.parents
                if manifest.is_symlink() or manifest.exists():manifest.unlink()
                manifest.symlink_to(victim)
                assert manifest.samefile(victim)
        actual=args if not traced else ['strace','-ff','-qq','-ttt','-s','131072','-e','trace=execve,unlink,unlinkat,rename,renameat,renameat2,readlink,readlinkat,openat','-o',str(out/'trace'),*args]
        with (out/'cargo.stdout').open('xb') as o,(out/'cargo.stderr').open('xb') as e:
            proc=subprocess.Popen(actual,env=env,cwd=project,stdout=o,stderr=e)
            try:
                if fd is not None:observed=place_on_delete(fd,manifest,victim,proc)
                rc=proc.wait(timeout=90)
            finally:
                if fd is not None:os.close(fd)
                if proc.poll() is None:proc.kill();proc.wait()
        msgs=[json.loads(l) for l in (out/'cargo.stdout').read_bytes().splitlines()]
        arts=[v for v in msgs if v['reason']=='compiler-artifact']
        assert rc==0 and {z['target']['name'] for z in arts}=={'probe','producer'},(phase,rc)
        exe=Path(next(v['executable'] for v in arts if v.get('executable')));value_raw=subprocess.check_output([exe]);(out/'program.stdout').write_bytes(value_raw)
        assert int(value_raw)==value,(phase,value_raw,value)
        if manifest is None:
            physical=set()
            for d in (root/'products',root/'build-store'):
                if d.is_dir():
                    physical.update(x for x in d.rglob('probe-*') if x.is_file() and x.suffix=='' and not x.is_symlink() and x.stat().st_size==exe.stat().st_size and hash_stream(x)==hash_stream(exe))
            assert len(physical)==1,physical
            manifest=physical.pop().with_suffix('.rlink-cache.json')
            found=[f for d in (root/'products',root/'build-store') if d.exists() for f in d.rglob('*.rlink-cache.json')]
            assert (found==[manifest] and not manifest.is_symlink()) if enabled else not found,found
        data={'phase':phase,'mode':mode,'argv':cmd_arg,'trace_external':traced,'source_sha256':input_hash(),'returncode':rc,'program':int(value_raw),'elf_sha256':hash_stream(exe),'typed':[(m['target']['name'],m['fresh']) for m in arts],'manifest_regular':manifest.is_file() and not manifest.is_symlink(),'manifest_symlink':manifest.is_symlink(),'manifest_exists':manifest.exists(),'manifest_location':str(manifest.relative_to(root)),'watch':observed,'execs':[],'stdout_sha256':hash_stream(out/'cargo.stdout'),'stderr_sha256':hash_stream(out/'cargo.stderr')}
        if traced:
            data['execs']=native_execution(out);data['manifest_operations']=fs_events(out,manifest,victim)
            data['raw_trace_files']={f.name:hash_stream(f) for f in sorted(out.glob('trace.*'))}
        if method:
            after=victim.read_bytes();(out/'sentinel-after.bin').write_bytes(after);st=victim.stat()
            data['victim']={'before':hb(prior),'after':hb(after),'before_bytes':len(prior),'after_bytes':len(after),'inode_before':before.st_ino,'inode_after':st.st_ino,'changed':after!=prior,'symlink_reaches_victim':manifest.is_symlink() and manifest.samefile(victim)}
            expect=enabled and method in ('during','pre-valid')
            assert (after!=prior)==expect and (st.st_ino!=before.st_ino)==expect,(phase,data['victim'])
            if expect:
                assert manifest.is_symlink() and manifest.samefile(victim)
                after_json=json.loads(after);assert after_json['version']==3 and after_json['objects'] and 'owner_note' not in after_json
                assert Path(after_json['executable']['path']).samefile(exe)
                data['victim']['new_manifest_version']=after_json['version'];data['victim']['object_count']=len(after_json['objects'])
        dump(out/'receipt.json',data);records.append(data);print(mode,traced,phase,value,'unchanged' if not method or not data['victim']['changed'] else 'SENTINEL REPLACED',flush=True)
    run('01-cold',17)
    update_app(1)
    run('02-own-source-edit',18,'during' if enabled else 'pre-arbitrary')
    update_app(2)
    run('03-preexisting-unrelated',19,'pre-arbitrary')
    update_lib(29)
    run('04-dependency-edit',31,'pre-valid' if enabled else 'pre-arbitrary')
    run('05-unchanged',31)
    update_app(0);update_lib(17)
    run('06-restore',17)
    dump(root/'terminal.json',{'mode':mode,'traced':traced,'cargo_sha256':FRONTEND[scope],'cargo_commit':COMMITS[scope],'source_rust':'f6270311094cd4b48fefce03debdffcf8396c64c','no_wrapper':True,'phases':{x['phase']:hash_stream(root/x['phase']/'receipt.json') for x in records},'source':hb(Path(__file__).read_bytes()),'argv':cmd_arg})
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_owned_output',type=Path);parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--setting',required=True,choices=['head-relink','head-public','head-plain','parent-plain','parent-public'])
    parser.add_argument('--trace',action='store_true')
    args=parser.parse_args();study(args.new_owned_output,args.sdk,args.setting,args.trace)
