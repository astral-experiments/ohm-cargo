#!/usr/bin/env python3
"""Check whether a successful Cargo build follows its generated relink-manifest symlink."""

import argparse
import ctypes
import hashlib
import json
import os
import select
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def watch_directory(path):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0 or libc.inotify_add_watch(fd, os.fsencode(path), 0x200) < 0:
        raise OSError(ctypes.get_errno(), 'cannot watch the private manifest directory')
    return fd


def install_after_delete(fd, manifest, sentinel, process):
    poll = select.poll()
    poll.register(fd, select.POLLIN)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if not poll.poll(50):
            if process.poll() is not None:
                break
            continue
        events = os.read(fd,65536)
        position = 0
        while position < len(events):
            _, mask, _, name_size = struct.unpack_from('iIII', events, position)
            offset = position + 16
            name = events[offset:offset + name_size].split(b'\0')[0]
            position = offset + name_size
            if mask & 0x200 and name == os.fsencode(manifest.name):
                assert not manifest.exists() and not manifest.is_symlink()
                manifest.symlink_to(sentinel)
                assert manifest.samefile(sentinel)
                return
    raise RuntimeError('the exact prior manifest was not deleted during this build')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_directory',type=Path,help='new private directory for both package outputs and sentinels')
    parser.add_argument('--sdk',type=Path,help='installed Ohm SDK to link as the local +ohm toolchain')
    parser.add_argument('--expect',choices=['follows','protected'],required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('run as an ordinary user on Linux with a Rustup Cargo proxy')
    root = args.new_directory.absolute()
    root.mkdir(mode=0o700)
    source = root/'project'
    (source/'src').mkdir(parents=True)
    (source/'Cargo.toml').write_text('[package]\nname="probe"\nversion="0.1.0"\nedition="2024"\n')
    cargo = shutil.which('cargo')
    if cargo is None:
        parser.error('cargo was not found on PATH')
    env = {'HOME':str(root),'PATH':os.environ['PATH'],'LANG':'C','CARGO_HOME':str(root/'cargo-home'),
           'CARGO_TARGET_DIR':str(root/'products'),'CARGO_BUILD_BUILD_DIR':str(root/'build-store'),
           'CARGO_NET_OFFLINE':'true','RUSTUP_AUTO_INSTALL':'0','RUSTUP_TOOLCHAIN':'ohm','CARGO_INCREMENTAL':'0'}
    if args.sdk is None:
        env['RUSTUP_HOME'] = os.environ.get('RUSTUP_HOME', str(Path.home()/'.rustup'))
    else:
        sdk = args.sdk.resolve(strict=True)
        assert (sdk/'bin/cargo').is_file() and (sdk/'bin/rustc').is_file()
        rustup = root/'private-rustup'
        (rustup/'toolchains').mkdir(parents=True)
        (rustup/'toolchains/ohm').symlink_to(sdk)
        env['RUSTUP_HOME'] = str(rustup)
    command=[cargo,'+ohm','build','--offline','-j1','--message-format=json']
    manifest=None
    records=[]
    for phase,value in [('cold',17),('during',29),('before',31)]:
        (source/'src/main.rs').write_text('fn main() { println!("'+str(value)+'"); }\n')
        sentinel=root/(phase+'-owned-sentinel')
        sentinel.write_bytes(('unrelated '+phase+' contents\n').encode())
        old=sentinel.read_bytes()
        original_inode=sentinel.stat().st_ino
        watch=None
        if phase=='during':
            assert manifest.is_file() and not manifest.is_symlink()
            watch=watch_directory(manifest.parent)
        elif phase=='before':
            manifest.unlink()
            manifest.symlink_to(sentinel)
        proc=subprocess.Popen(command,env=env,cwd=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            if watch is not None:
                install_after_delete(watch,manifest,sentinel,proc)
            stdout,stderr=proc.communicate(timeout=120)
        finally:
            if watch is not None:
                os.close(watch)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        (root/(phase+'.stdout')).write_bytes(stdout)
        (root/(phase+'.stderr')).write_bytes(stderr)
        assert proc.returncode==0,(phase,stderr.decode()[-300:])
        messages=[json.loads(line) for line in stdout.splitlines()]
        assert messages[-1]=={'reason':'build-finished','success':True}
        artifacts=[x for x in messages if x['reason']=='compiler-artifact']
        assert len(artifacts)==1 and not artifacts[0]['fresh']
        assert subprocess.check_output([artifacts[0]['executable']],text=True).strip()==str(value)
        if phase=='cold':
            manifests=list((root/'products').rglob('*.rlink-cache.json'))+list((root/'build-store').rglob('*.rlink-cache.json'))
            assert len(manifests)==1,'this Cargo did not produce one relink manifest for the binary'
            manifest=manifests[0]
            assert manifest.parent.resolve().is_relative_to(root) and not manifest.is_symlink()
        after=sentinel.read_bytes()
        changed=after!=old
        if changed:
            assert json.loads(after)['objects'] and manifest.is_symlink() and manifest.samefile(sentinel)
        assert changed==(phase=='during' and args.expect=='follows'),(phase,changed,args.expect)
        if not changed:
            assert sentinel.stat().st_ino==original_inode and not manifest.is_symlink()
        records.append({'phase':phase,'program':value,'sentinel_sha256_before':hash_bytes(old),
                        'sentinel_sha256_after':hash_bytes(after),'sentinel_replaced':changed,
                        'manifest_is_symlink':manifest.is_symlink(),'cargo_stdout_sha256':hash_bytes(stdout),
                        'cargo_stderr_sha256':hash_bytes(stderr)})
    (root/'results.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    main()
