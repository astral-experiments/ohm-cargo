"""Compile a pinned 8-thread accelerated BLAKE3 reader alongside the private released linker replay."""
from pathlib import Path
import base64,hashlib,io,json,subprocess,tarfile
p=Path(__file__).resolve().parent
crate,=Path.home().glob('.cargo/registry/cache/*/blake3-1.8.7.crate')
archive='6d9e454fc11f76977dc803893aff6304ed33d6a26efae8696573bea74baa27ae'
assert hashlib.sha256(crate.read_bytes()).hexdigest()==archive
names=['blake3.c','blake3.h','blake3_impl.h','blake3_portable.c','blake3_dispatch.c','blake3_sse2_x86-64_unix.S','blake3_sse41_x86-64_unix.S','blake3_avx2_x86-64_unix.S','blake3_avx512_x86-64_unix.S']
with tarfile.open(crate)as t:parts={n:t.extractfile('blake3-1.8.7/c/'+n).read()for n in names}
parts.update({'hash-inputs.c':(p/'hash-inputs.c').read_bytes(),'width.py':(p/'hashing-replay.py').read_bytes()});commit={k:hashlib.sha256(v).hexdigest()for k,v in parts.items()}
inner="""from pathlib import Path
import hashlib,io,json,shlex,shutil,subprocess,sys,tarfile
p=Path.home()/'.cache/ohm-ron-native-positive-input-cost-h4-20261028-v1';p.mkdir(mode=0o700);assert shutil.disk_usage(p).free>30*2**30 and shutil.disk_usage('/mnt/devbox-scratch/dev-user').free>25*2**30
m=json.loads(sys.argv[1]);buf=sys.stdin.buffer.read();assert hashlib.sha256(buf).hexdigest()==sys.argv[2]
with tarfile.open(fileobj=io.BytesIO(buf))as t:
 for n in m:
  assert '/'not in n and n not in('.','..');d=t.extractfile(n).read();assert hashlib.sha256(d).hexdigest()==m[n];(p/n).write_bytes(d)
cmd=['cc','-O3','-std=gnu11','-Wall','-Wextra','-pthread','-I.','-o','hash-inputs','hash-inputs.c','blake3.c','blake3_dispatch.c','blake3_portable.c',*sorted(n for n in m if n.endswith('.S'))]
res=subprocess.run(['taskset','-c','4-11',*cmd],cwd=p,capture_output=True);(p/'cc.stderr').write_bytes(res.stderr);assert res.returncode==0,res.stderr
for name,data,expect in [('empty',b'','af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262'),('abc',b'abc','6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85')]:
 code=p/(name+'.test');code.write_bytes(data);assert subprocess.check_output([p/'hash-inputs',code],text=True).strip()==expect
(p/'build.json').write_text(json.dumps({'archive':sys.argv[3],'sources':m,'argv':cmd,'cc':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'hasher':hashlib.sha256((p/'hash-inputs').read_bytes()).hexdigest(),'known_answers':['empty','abc']},sort_keys=True))
shim=p/'shim';shim.write_text('#!/bin/sh\\nWIDTH_REPLAY_MODE=interposed exec /usr/bin/python3 -IB '+shlex.quote(str(p/'width.py'))+' "$@"\\n');shim.chmod(0o755)
cmd='/usr/bin/python3 -IBu '+shlex.quote(str(p/'width.py'))+' > '+shlex.quote(str(p/'log'))+' 2>&1; echo $? > '+shlex.quote(str(p/'rc'));subprocess.run(['tmux','new-session','-d','-s','ohm-native-operand-hash-cost',cmd],check=True)
"""
f=io.BytesIO()
with tarfile.open(fileobj=f,mode='w:gz')as t:
    for n,d in parts.items():
        i=tarfile.TarInfo(n);i.size=len(d);t.addfile(i,io.BytesIO(d))
bundle=f.getvalue()
subprocess.run(['dbox','ssh','charlie-ohm-generic-perf-1024','--no-tmux','--','/usr/bin/python3','-IB','-c',inner,json.dumps(commit,sort_keys=True),hashlib.sha256(bundle).hexdigest(),archive],input=bundle,check=True)
