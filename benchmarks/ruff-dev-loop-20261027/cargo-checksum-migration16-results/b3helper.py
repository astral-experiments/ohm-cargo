"""Build a private standalone portable BLAKE3 verifier against a pinned stock crate's C implementation."""
from pathlib import Path
import hashlib,subprocess,ctypes,json,tarfile,sys,io
p=Path(__file__).resolve().parent
s,=sorted((Path.home()/'.cargo/registry/src').glob('*/blake3-1.8.2/c'))[:1]
sources=['blake3.c','blake3.h','blake3_impl.h','blake3_dispatch.c','blake3_portable.c']
csrc=b'#include "blake3.h"\nvoid cargo_depinfo_b3(const void *in, size_t len, void *out) { blake3_hasher h; blake3_hasher_init(&h); blake3_hasher_update(&h, in, len); blake3_hasher_finalize(&h, out, 32); }\n'
out=p/'libcargo_depinfo_b3.so';cc='/usr/bin/cc'
args=[cc,'-shared','-fPIC','-O2','-DBLAKE3_NO_SSE2','-DBLAKE3_NO_SSE41','-DBLAKE3_NO_AVX2','-DBLAKE3_NO_AVX512','-DBLAKE3_USE_NEON=0','-I',str(s),'-x','c','-',str(s/'blake3.c'),str(s/'blake3_dispatch.c'),str(s/'blake3_portable.c'),'-o',str(out)]
subprocess.run(args,input=csrc,check=True)
def hh(b):return hashlib.sha256(b).hexdigest()
a=ctypes.CDLL(str(out)).cargo_depinfo_b3;a.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p)
for input_,exp in [(b'','af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262'),(b'abc','6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85')]:
    b=ctypes.create_string_buffer(32);a(input_,len(input_),b);assert b.raw.hex()==exp
rec={'source_crate':'blake3 1.8.2','source_files':{f:hh((s/f).read_bytes()) for f in sources},'helper_c':csrc.decode(),'cc':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'cc_sha':hh(Path(cc).resolve().read_bytes()),'helper_sha256':hh(out.read_bytes()),'known_inputs':['zero-length','abc']}
(p/'b3helper.json').write_text(json.dumps(rec,sort_keys=True,indent=2)+'\n')
print(rec['helper_sha256'])
