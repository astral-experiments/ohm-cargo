"""Check complete debug-string inventories and decoded DIEs and macro records in both arms."""
from pathlib import Path
import fcntl
import hashlib
import json
import mmap
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile

p=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
assert socket.gethostname()=='charlie-ohm-cargo5-build-1025'
os.sched_setaffinity(0,{20,21,22,23})
glob='logical/ruff-target/debug/build/workspaces/2abf155240aec459/v2-'
info_str=re.compile(rb'\(strp\) \(offset: (0x[0-9a-f]+|0)\): ')
sha=lambda b:hashlib.sha256(b).hexdigest()

def inspect(path,old):
    scope=(str(p)+'/'+glob+old).encode()
    constant=(str(p)+'/'+glob+'@same-compiler@@').encode()
    assert len(scope)==len(constant)
    result={}
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mem:
        sh=struct.unpack_from('<Q',mem,40)[0];size,num,idx=struct.unpack_from('<HHH',mem,58)
        heads=[struct.unpack_from('<IIQQQQIIQQ',mem,sh+size*i) for i in range(num)]
        base=heads[idx][4]
        h,=[h for h in heads if mem[base+h[0]:mem.find(b'\x00',base+h[0])]==b'.debug_str']
        strings=mem[h[4]:h[4]+h[5]]
        assert strings.endswith(b'\x00')
        canonical=strings.replace(scope,constant)
        entries=sorted(canonical.split(b'\x00'));inventory=hashlib.sha256()
        for val in entries:
            inventory.update(struct.pack('<I',len(val)));inventory.update(val)
        result['debug_strings']=dict(entries=len(entries),stored=len(strings),inventoried=inventory.hexdigest(),namespace_occurrences=strings.count(scope))
        actual=strings.count(scope)
        assert actual<=6 and (not actual or len(canonical)==len(strings))
        del entries
        for section in ('macro','info'):
            with tempfile.TemporaryFile() as error:
                proc=subprocess.Popen(['readelf','--wide','--debug-dump='+section,str(path)],stdout=subprocess.PIPE,stderr=error,env={'LC_ALL':'C','PATH':'/usr/bin:/bin'})
                digest=hashlib.sha256();raw=hashlib.sha256();lines=refs=rewritten=0;found_examples=[]
                for line in proc.stdout:
                    raw.update(line);lines+=1
                    if section=='info' and b'(strp) (offset: ' in line:
                        match=info_str.search(line);assert match,line[:150]
                        off=int(match[1],0);assert 0<=off<len(strings) and strings.find(b'\x00',off)>=off
                        # readelf renders the actual referenced string after the offset. Retain all
                        # its bytes and all printed DIE/attribute addresses, forms and flags.
                        line=line[:match.start(1)]+b'@str-offset@'+line[match.end(1):];refs+=1
                    copies=line.count(scope)
                    if copies:line=line.replace(scope,constant);rewritten+=copies
                    digest.update(line)
                assert not proc.wait();error.seek(0);err=error.read()
                result[section]=dict(lines=lines,str_offsets=refs,namespaces=rewritten,raw=raw.hexdigest(),decoded=digest.hexdigest(),stderr_len=len(err),stderr=sha(err))
    return result

def main():
    records=json.loads(sys.stdin.buffer.read())
    with (p/'matched-qualify.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        results={}
        for name,raw in records.items():
            pair=[]
            for arm,token,subject in [('B','d23031a6115abf10','matched-parent'),('C','26fd4b9f9691cd6c','checked-paths-v4')]:
                rel=name.replace('@matched-compiler@','v2-'+token)
                path=p/('matched-native-rc17-'+subject)/'workspace/state/target'/rel
                assert path.is_file() and len(raw)==2
                with path.open('rb') as file:assert hashlib.file_digest(file,'sha256').hexdigest()==raw['BC'.index(arm)]
                pair.append(inspect(path,token))
            results[name]=pair
        print(json.dumps({'readelf':sha(Path('/usr/bin/readelf').read_bytes()),'version':subprocess.check_output(['readelf','--version']).decode().splitlines()[0],'pairs':results}),flush=True)

if __name__=='__main__':main()
