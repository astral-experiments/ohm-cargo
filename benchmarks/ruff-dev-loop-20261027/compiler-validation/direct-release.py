from pathlib import Path
import hashlib,json,os,subprocess,sys
d=Path(__file__).resolve().parent;n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');sr=n/'trait-pgo-state';rt=sr/'sysroot';old=n/'trait-codegen-screen';source=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');arm=sys.argv[1];drv=sr/'armB' if arm=='control' else d/'stage2-candidate';lib='librustc_driver-774a793a844d5500.so'
def sha(f):
    with open(f,'rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
entry=next(p for p in (old/'receipts/objects-v2-0A').glob('compile.*.argv') if b'\0ruff_python_parser\0' in p.read_bytes());args0=[s.decode() for s in entry.read_bytes().split(b'\0') if s];assert '--emit=dep-info,metadata,link' in args0 and 'opt-level=1' in args0 and 'lto=off' in args0 and any(s.startswith('incremental=') for s in args0);assert args0[0]==str(rt/'bin/rustc')
route=d/'direct-active';route.mkdir(exist_ok=True);assert not any(route.iterdir())
env=dict(os.environ,RUSTUP_TOOLCHAIN='ohm',RUSTUP_HOME=str(sr/'rustup'),GIT_OPTIONAL_LOCKS='0',CARGO_MANIFEST_DIR=str(source/'crates/ruff_python_parser'),CARGO_PKG_NAME='ruff_python_parser',CARGO_PKG_VERSION='0.0.17')
results={}
for phase in ('original','modified'):
    st=d/('release-direct-'+arm+'-'+phase);st.mkdir()
    args=args0[:];args[args.index('--out-dir')+1]=str(route);args=['incremental='+str(route/'incremental') if a.startswith('incremental=') else a for a in args]
    ns=['taskset','-c','20-23','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(old/'seed'),str(old/'store'),'--bind',str(st),str(route),'--ro-bind',str(drv/lib),str(rt/'lib'/lib)]
    if phase=='modified':
        fi=d/'3ea20f6161-native/fixtures'
        for f in fi.rglob('*'):
            if f.is_file():ns+=['--ro-bind',str(f),str(source/f.relative_to(fi))]
    ns+=['--chdir',str(source),'--']
    with (st/'stderr').open('wb') as e,(st/'stdout').open('wb') as o:proc=subprocess.run(ns+args,env=env,stdout=o,stderr=e)
    assert proc.returncode==0,(st/'stderr').read_text()[-600:]
    meta=next(st.glob('*.rmeta'));archive=next(st.glob('*.rlib'));out=subprocess.check_output(ns+['/home/dev-user/.cargo/bin/rustc','+ohm','-Zls=public_hash',str(route/meta.name)],env=env)
    result=dict(metasum=sha(meta),archivesum=sha(archive),public=out.decode().strip().split()[-1],argv_sha=sha(entry),driver=sha(drv/lib));(st/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');results[phase]=result
print(arm,json.dumps(results),flush=True)
