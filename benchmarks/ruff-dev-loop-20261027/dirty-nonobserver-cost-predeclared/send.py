from pathlib import Path
import gzip,hashlib,io,json,os,shlex,subprocess,sys,tarfile
i=Path(__file__).resolve().parent;root=Path.home();k=i.parent
sdk=root/'.cache/ohm-ruff-packed-edges-20261026/nonleaf/trait-pgo-state/sysroot';cache,=(root/'.cargo/registry/index').glob('*/.cache')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
files={k:i/k.split('/')[-1] for k in ('inputs/fixture.py','inputs/caller.rs','inputs/range.rs','inputs/edited.rs','inputs/preflight-inputs.json','inputs/package.patch')}
for name in ('schedule.json','run-times.py','inside.py'):
    if (i/name).is_file():files['inputs/'+name]=i/name
files['inputs/B']=root/'.cache/ohm-ruff-cargo-link-skip-20261027/native-span-observer/ruff-sdk-prefetch-corrected-subjects/guardv3';files['inputs/C']=k/'cargo-v3/cargo-release-bind/cargo'
for p in [sdk/'bin/rustc',sdk/'lib/libLLVM-23-rust-1.99.0-beta.so',*(sdk/'lib/rustlib').rglob('*')]:
    if p.is_file():files['sdk/'+str(p.relative_to(sdk))]=p
for fn in json.loads((i/'index-paths.json').read_bytes()):files['inputs/index/.cache/'+fn]=cache/fn
namespace=cache.parent.name.encode();assert b'/' not in namespace
assets={k:sha(v) for k,v in files.items()};assets['inputs/cache-namespace']=hashlib.sha256(namespace).hexdigest()
label=sys.argv[1];assert label.isidentifier();dest=i/'receipts'/label;dest.mkdir(parents=True);(dest/'sources.json').write_text(json.dumps(assets,sort_keys=True,indent=2)+'\n')
cmd=['dbox','ssh','charlie-ohm-mono-bench','--no-tmux','--','/usr/bin/python3','-B','-c',(i/'receive.py').read_text(),label,*sys.argv[2:]]
with (dest/'raw.stdout').open('xb') as out,(dest/'raw.stderr').open('xb') as err:
    d=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=out,stderr=err)
    try:
        with tarfile.open(fileobj=d.stdin,mode='w|gz',compresslevel=1) as t:
            def put(n,stream,mode,length):
                fi=tarfile.TarInfo(n);fi.mode=mode;fi.size=length;t.addfile(fi,stream)
            for n,p in sorted(files.items()):
                with p.open('rb') as f:put(n,f,p.stat().st_mode&0o777,p.stat().st_size)
            put('inputs/cache-namespace',io.BytesIO(namespace),0o444,len(namespace))
            data=json.dumps(assets,sort_keys=True).encode();put('inputs/asset-manifest.json',io.BytesIO(data),0o444,len(data))
    except BrokenPipeError:pass
    finally:d.stdin.close()
    rc=d.wait()
(dest/'rc').write_text(str(rc)+'\n')
print('rc',rc,'errors', (dest/'raw.stderr').read_text(errors='replace')[-2000:])
if rc==0:
    v=json.loads((dest/'raw.stdout').read_bytes());print('accepted',v.keys())
sys.exit(rc)
