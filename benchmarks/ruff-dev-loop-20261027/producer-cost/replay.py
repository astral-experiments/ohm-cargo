"""Unscored intrinsic producer cost guard using complete fresh Ruff compiler inputs and no child counting."""
from pathlib import Path
import collections,hashlib,json,os,subprocess,tempfile
d=Path(__file__).resolve().parent;n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');sr=n/'trait-pgo-state';sysroot=sr/'sysroot';lib='librustc_driver-774a793a844d5500.so';dr=Path('/home/dev-user/.cache/ohm-dynamorio-20261026');source=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');out=d/'compiler-cost';out.mkdir(exist_ok=True);route=out/'active';route.mkdir(exist_ok=True)
def sha(f):
    with f.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
cases={'check':(n/'trait-confirm-current/discovery-C01B',sr/'confirmation-current/seedB',sr/'confirmation-current/store'),'build':(n/'trait-codegen-screen/receipts/objects-v2-0A',n/'trait-codegen-screen/seed',n/'trait-codegen-screen/store')}
plan={q:{'argv':sha(next(f for f in rec.glob('compile.*.argv') if b'\0ruff_python_parser\0' in f.read_bytes())),'paired_order':['AB','BA','BA','AB']} for q,(rec,_,_) in cases.items()}
(out/'plan.json').write_text(json.dumps({'scope':'Cold exact rustc process including in-process LLVM, excludes Cargo, linker children, assembly and test execution. Four matched pairs per mode. Descriptive check for per-producer overhead, no performance endpoint.','cases':plan})+'\n')
for mode in ('check','build'):
    rec,seed,canonical=cases[mode];f=next(f for f in rec.glob('compile.*.argv') if b'\0ruff_python_parser\0' in f.read_bytes());argv=[s.decode() for s in f.read_bytes().split(b'\0') if s];assert argv[0]==str(sysroot/'bin/rustc');argv[argv.index('--out-dir')+1]=str(route);argv=['incremental='+str(route/'incremental') if a.startswith('incremental=') else a for a in argv]
    for i,order in enumerate(plan[mode]['paired_order'],1):
        for arm in order:
            dst=out/f'{mode}-{i:02d}{arm}';dst.mkdir()
            drv=(sr/'armB' if arm=='A' else d/'stage2-candidate')/lib
            env=dict(os.environ,RUSTUP_TOOLCHAIN='ohm',RUSTUP_HOME=str(sr/'rustup'),GIT_OPTIONAL_LOCKS='0',CARGO_MANIFEST_DIR=str(source/'crates/ruff_python_parser'),CARGO_PKG_NAME='ruff_python_parser',CARGO_PKG_VERSION='0.0.17')
            with tempfile.TemporaryDirectory(dir=out) as temp:
                st=Path(temp);ns=['taskset','-c','24-25','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(seed),str(canonical),'--bind',str(st),str(route),'--bind',str(dst),str(dst),'--ro-bind',str(drv),str(sysroot/'lib'/lib),'--chdir',str(source),'--']
                cmd=ns+[str(dr/'sdk/bin64/drrun'),'-no_follow_children','-c',str(dr/'client/libpidcounter.so'),str(dst/'rustc.ir'),'--']+argv
                with (dst/'stdout').open('wb') as o,(dst/'stderr').open('wb') as e:r=subprocess.run(cmd,env=env,stdout=o,stderr=e)
                assert r.returncode==0,(dst,(dst/'stderr').read_text()[-1000:])
                lines=[l.split() for l in (dst/'rustc.ir').read_text().splitlines()];pid=lines[0][1];assert lines[0]==['B',pid,'0','0'] and lines[-1]==['P',pid,'0','0'] and all(r[1]==pid for r in lines);assert collections.Counter(r[2] for r in lines if r[0]=='T')==collections.Counter(r[2] for r in lines if r[0]=='F');assert all(r[0] in ('B','P','T','F') or r[0]=='S' and int(r[3]) in (10,17) for r in lines)
                count=sum(int(r[3]) for r in lines if r[0]=='F');meta=next(st.glob('*.rmeta'));public=subprocess.check_output(ns+['/home/dev-user/.cargo/bin/rustc','+ohm','-Zls=public_hash',str(route/meta.name)],env=env).decode().strip().split()[-1]
                ref=json.loads((d/(('check-direct-'if mode=='check' else 'release-direct-')+('control' if arm=='A' else 'candidate')+'-original')/'receipt.json').read_bytes());assert public==ref['public']
                result={'mode':mode,'arm':arm,'pair':i,'ir':count,'threads':len([r for r in lines if r[0]=='T']),'public':public,'rmeta_sha256':sha(meta),'compiler':sha(drv),'compiler_argv_sha256':sha(f)}
                (dst/'receipt.json').write_text(json.dumps(result)+'\n');print(mode,i,arm,count,flush=True)
