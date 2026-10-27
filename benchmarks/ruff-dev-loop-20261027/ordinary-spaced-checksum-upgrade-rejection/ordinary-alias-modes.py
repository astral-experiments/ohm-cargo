"""Test ordinary Cargo checksum records on a binary include, on the released compiler."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import subprocess

p=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
assets=p.parent/'ohm-observer-shipping-20261027'
sdk=assets/'assets/stock16-sdk'
fixed=assets/'subjects/raw-fixed'
o=p/'ordinary-binary-alias-v2'
sha=lambda b:hashlib.sha256(b).hexdigest()
def dump(f,x):f.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def run_case(workflow,case):
    root=o/(workflow+'-'+case);root.mkdir()
    src=root/('source space' if case.endswith('root-prefix') else 'source');(src/'src').mkdir(parents=True)
    (src/'Cargo.toml').write_text('[package]\nname="byte_reader"\nversion="0.1.0"\nedition="2024"\n[workspace]\n')
    data=src/'ordinary-input/value.bin';data.parent.mkdir()
    if case.endswith('alias'):
        (src/'alias space').symlink_to(data.parent,target_is_directory=True)
        decoy=src/('alias'+chr(92)+' space/value.bin')
        inc='"../alias space/value.bin"'
    else:
        assert case.endswith('root-prefix')
        decoy=root/('source'+chr(92)+' space/ordinary-input/value.bin')
        inc='concat!(env!("CARGO_MANIFEST_DIR"),"/ordinary-input/value.bin")'
    before=bytes([17,255,0,254]);after=bytes([29,255,0,254])
    data.write_bytes(before)
    decoy.parent.mkdir(parents=True);decoy.write_bytes(after)
    rust='const INPUT: &[u8] = include_bytes!('+inc+');\n'
    if workflow=='check':
        rust+='const _: [();17] = [();INPUT[0] as usize];\n'
    rust+='fn main() { println!("{}",INPUT[0]); }\n'
    (src/'src/main.rs').write_text(rust)
    for n in ('home','cargo','target','shared','clean-target','clean-shared'):(root/n).mkdir()
    env=dict(HOME=str(root/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
             CARGO_HOME=str(root/'cargo'),CARGO_TARGET_DIR=str(root/'target'),CARGO_BUILD_BUILD_DIR=str(root/'shared'),
             CARGO_BUILD_JOBS='2',CARGO_NET_OFFLINE='true',RUSTUP_HOME=str(p/'rustup'),RUSTUP_TOOLCHAIN='ohm',
             RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',LANG='C.UTF-8',LC_ALL='C.UTF-8')
    ledger={}
    def command(label,candidate=False,clean=False):
        dot=root/label;dot.mkdir()
        e=dict(env);target=root/('clean-target' if clean else 'target');shared=root/('clean-shared' if clean else 'shared')
        e.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared))
        br=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(root),str(root)]
        if candidate:br+=['--ro-bind',str(fixed),str(sdk/'bin/cargo')]
        br+=['--chdir',str(src),'--']
        actual=subprocess.check_output([*br,'sha256sum',str(sdk/'bin/cargo')],env=e).split()[0].decode()
        assert actual==(sha(fixed.read_bytes()) if candidate else '42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568')
        config=['-Zohm-worktree-seeds=no','-Zchecksum-freshness'] if case.startswith('legacy-') else []
        cmd=['cargo','+ohm',*config,workflow,'--offline','-j2','--message-format=json']
        done=subprocess.run([*br,*cmd],env=e,capture_output=True)
        (dot/'stdout').write_bytes(done.stdout);(dot/'stderr').write_bytes(done.stderr)
        rows=[json.loads(v) for v in done.stdout.splitlines()]
        assert rows and rows[-1]=={'reason':'build-finished','success':done.returncode==0}
        arts=[v for v in rows if v['reason']=='compiler-artifact'];assert len(arts)<=1
        errors=[v['message'] for v in rows if v['reason']=='compiler-message' and v['message']['level']=='error']
        runtime=None
        if workflow=='build' and done.returncode==0:
            (art,)=arts
            exe=Path(art['executable'])
            val=subprocess.run([str(exe)],capture_output=True,check=True)
            assert not val.stderr and val.stdout in (b'17\n',b'29\n')
            (dot/'program.stdout').write_bytes(val.stdout);runtime=int(val.stdout)
        files={}
        for base in (target,shared):
            for f in base.rglob('*'):
                if not f.is_file() or not (f.suffix=='.d' or f.name=='dep-bin-byte_reader'):continue
                b=f.read_bytes()
                if b'value.bin' not in b:continue
                dest='input-'+str(len(files));(dot/dest).write_bytes(b)
                files[dest]=dict(path=str(f),sha=sha(b),observer=b'ohm-foreign-span-bytes' in b,
                                  trailer=b[-41:-37].decode(errors='replace') if b[-41:-37] in (b'OBS1',b'OBS2') else None)
        assert not any(v['observer'] or v['trailer'] for v in files.values())
        ledger[label]=dict(cargo=actual,cmd=cmd,rc=done.returncode,fresh=[v['fresh'] for v in arts],runtime=runtime,
                           errors=[(v.get('code') or {}).get('code') for v in errors],source=sha((src/'src/main.rs').read_bytes()),
                           data=sha(data.read_bytes()),decoy=sha(decoy.read_bytes()) if decoy.is_file() else None,
                           physical_files=files,stdout=sha(done.stdout),stderr=sha(done.stderr))
        dump(dot/'record.json',ledger[label])
    command('baseline');command('unchanged')
    old=data.stat();data.write_bytes(after);os.utime(data,ns=(old.st_atime_ns,old.st_mtime_ns))
    assert data.stat().st_mtime_ns==old.st_mtime_ns and data.stat().st_size==old.st_size
    command('changed')
    decoy.unlink()
    command('cargo-upgrade',candidate=True)
    command('clean',candidate=True,clean=True)
    active=ledger['changed']
    assert active['fresh']==[True] and active['rc']==0
    assert ledger['cargo-upgrade']['fresh']==[True]
    assert ledger['clean']['runtime']==29 if workflow=='build' else ledger['clean']['errors']==['E0308']
    encoded=[d for d,v in active['physical_files'].items() if Path(v['path']).name=='dep-bin-byte_reader']
    assert len(encoded)==1,active['physical_files']
    b=(root/'changed'/encoded[0]).read_bytes()
    assert b[:6]==bytes([1,0,0,0,255,2]) and b'OBS1' not in b and b'OBS2' not in b
    import struct
    pos=6
    def word():
        nonlocal pos
        n=struct.unpack_from('<I',b,pos)[0];pos+=4
        return n
    count=word();names=[]
    for _ in range(count):
        pos+=1;size=word();names.append(b[pos:pos+size]);pos+=size
        valid=b[pos];pos+=1
        if valid:
            assert valid==1;pos+=8;size=word();pos+=size
    assert any(n.endswith(b'value.bin') for n in names),names
    dump(root/'encoded-paths.json',[n.decode() for n in names])
    dump(root/'result.json',ledger)
    return dict(native={k:[v['rc'],v['fresh'],v['runtime'],v['errors']] for k,v in ledger.items()},
                saved=[n.decode() for n in names],has_space=any(b' ' in n for n in names))
assert socket.gethostname()=='charlie-ohm-cargo5-build-1025' and not o.exists()
assert sha(fixed.read_bytes())=='dc377742bbae74011f4dca99b7c5ea3002e5af5b979149a6a2f8c0ba7bc726c4'
assert shutil.disk_usage(p).free>60*2**30
os.sched_setaffinity(0,{6,7})
assert (p/'ordinary-binary-alias-v1/build-alias/clean/record.json').is_file()
o.mkdir(mode=0o700)
results={}
for cmd in ('build','check'):
    for kind in ('default-alias','default-root-prefix','legacy-alias','legacy-root-prefix'):
        results[cmd+'-'+kind]=run_case(cmd,kind)
        dump(o/'progress.json',results)
dump(o/'complete.json',results)
print(json.dumps(results,sort_keys=True))
