"""Verify an OBS1 raw record using the portable upstream BLAKE3 C implementation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

def sha(data):return hashlib.sha256(data).hexdigest()
def check(raw,src):
    r=raw.read_bytes();src=src.resolve();impl=['blake3.c','blake3_portable.c','blake3_dispatch.c'];s={n:sha((src/n).read_bytes()) for n in impl+['blake3.h','blake3_impl.h']}
    body="""#include <stdio.h>
#include "blake3.h"
int main(void){char b[8192];size_t n;unsigned char d[32];blake3_hasher h;blake3_hasher_init(&h);while((n=fread(b,1,sizeof b,stdin)))blake3_hasher_update(&h,b,n);if(ferror(stdin))return 1;blake3_hasher_finalize(&h,d,32);for(size_t i=0;i<32;i++)printf("%02x",d[i]);return 0;}"""
    with tempfile.TemporaryDirectory() as td:
        t=Path(td);c=t/'b3.c';c.write_text(body)
        exe=t/'b3';subprocess.run(['cc','-O2','-DBLAKE3_NO_SSE2','-DBLAKE3_NO_SSE41','-DBLAKE3_NO_AVX2','-DBLAKE3_NO_AVX512','-I',str(src),c,*[src/f for f in impl],'-o',exe],check=True)
        def digest(b):return subprocess.check_output([exe],input=b).decode()
        assert digest(b'')=='af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262'
        assert r[-41:-37]==b'OBS1' and r[-33]==0
        b=r[:-32];assert digest(b)==r[-32:].hex()
        mutated=bytearray(b);mutated[-1]=1;assert digest(mutated)!=r[-32:].hex()
        return {'source_crate':src.parent.name,'portable_source_sha256':s,'record_bytes':len(r),'record_sha256':sha(r),'body_sha256':sha(b),'blake3':r[-32:].hex(),'changing_status_detected':True}
if __name__=='__main__':print(json.dumps(check(Path(sys.argv[1]),Path(sys.argv[2])),sort_keys=True,indent=2))
