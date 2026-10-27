from pathlib import Path
import base64,gzip,hashlib,io,json,subprocess,sys,tarfile
D=Path(__file__).resolve().parent
P=D.parent.parent/'build-script-timestamp-timing-plan';action=sys.argv[1]
pre="""from pathlib import Path
import base64,gzip,hashlib,io,json,os,shutil,subprocess,sys,tarfile
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';H=X/'build-script-generation-timing-worker-v1';Q=X/'build-script-generation-timing-v1'
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
"""
def remote(code,data=b''):
 q=subprocess.run(['dbox','ssh','charlie-ohm-relink-b-1024','--no-tmux','--','nice','-n','10','taskset','-c','30','python3','-B','-c',pre+code],input=data,capture_output=True,timeout=1200);sys.stderr.buffer.write(q.stderr);assert q.returncode==0,(q.returncode,q.stderr[-600:]);return q.stdout
if action in ('prepare','score'):
 files=([*P.glob('*'),D/'replay.py',D/'analyze.py',D/'controls.py',D/'check-controls.py',D/'source-binding.json',D/'verify-package.py'] if action=='prepare' else [D/'release-score.json'])
 data={p.name:base64.b64encode(p.read_bytes()).decode() for p in files if p.is_file()}
 code="""input_files=json.loads(gzip.decompress(sys.stdin.buffer.read()));H.mkdir(exist_ok=True,mode=0o700)
for n,s in input_files.items():
 p=H/n;b=base64.b64decode(s)
 if p.exists():assert p.read_bytes()==b,n
 else:p.write_bytes(b)
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=H,check=True)
"""
 code+="action="+repr(action)+"\n"+"""assert not (H/(action+'.log')).exists()
p=subprocess.Popen(['nice','-n','8','taskset','-c','0-23','python3','-B',str(H/'replay.py'),action],start_new_session=True,stdin=subprocess.DEVNULL,stdout=(H/(action+'.log')).open('xb'),stderr=subprocess.STDOUT);print('started',action,p.pid,'runner',h(H/'replay.py'))
"""
 print(remote(code,gzip.compress(json.dumps(data).encode(),mtime=0)).decode())
elif action=='status':
 print(remote("""for n in ('prepare','score'):
 p=H/(n+'.log');print(n,p.read_text(errors='replace')[-1400:] if p.exists() else None)
print('complete',[(n,(Q/n).is_file()) for n in ('prepared.json','complete.json')], 'disk',[(str(p),shutil.disk_usage(p).free//2**30) for p in (X,Path('/dev/shm'))])
""").decode())
elif action in ('qualification','results'):
 code='action='+repr(action)+'\n'+"""assert (Q/('prepared.json' if action=='qualification' else 'complete.json')).is_file()
rows=[p for p in Q.rglob('*.json') if p.is_file() and (p.name in {'receipt.json','physical-snapshots.json','raw-packaged-parity.json','change-family.json','restore-family.json','result.json','toolchain.json','seed.json','forced-three.json','elapsed.json','prepared.json','complete.json'}) and (not 'controls' in p.parts or p.name in ('toolchain.json','result.json')) and len(p.read_bytes())<6000000 and not any(s in p.parts for s in ('registry-home','active','target','shared','independent','independent-shared','active-shared','cargo-home')) and 'secure-root' not in p.parts]
out=io.BytesIO()
with gzip.GzipFile(fileobj=out,mode='wb',mtime=0,compresslevel=6) as gz,tarfile.open(mode='w',fileobj=gz) as t:
 for p in sorted(rows):
  by=p.read_bytes();i=tarfile.TarInfo(str(p.relative_to(Q)));i.mode=0o644;i.size=len(by);t.addfile(i,io.BytesIO(by))
print(base64.b64encode(out.getvalue()).decode())
"""
 out=base64.b64decode(remote(code));p=D/(action+'.tar.gz');p.write_bytes(out);print(p,len(out),hashlib.sha256(out).hexdigest())
else:raise ValueError(action)
