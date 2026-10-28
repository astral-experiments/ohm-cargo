"""Bind only the tested native-child boundary in a private SDK. Preserve the actual Cargo selection flags."""
from pathlib import Path
import hashlib,json,os,platform,shutil,subprocess,sys
root=Path(__file__).resolve().parent
label=sys.argv[1];assert label.isalnum()
if len(sys.argv)==3:
 # Distribution proof is a separate subject with its own complete source/binary identity.
 install=Path(sys.argv[2]).resolve();art={'cargo':install/'bin/cargo','rustc':install/'bin/rustc','driver':next((install/'lib').glob('librustc_driver-*.so'))}
 expected=json.loads((root/'official.json').read_bytes()); lineage='official-18'
else:
 base=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');install=base/'frozen-toolchain'
 art={'cargo':Path('/mnt/devbox-scratch/dev-user/ohm-rc18-pgo-qualification-20261028/cargo'),'rustc':install/'bin/rustc','driver':base/'mixed-module-children-17-v1-20261028/tool-rc18-export-r2/candidate-driver.so'}
 expected={'cargo':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8','rustc':'4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f','driver':'22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f'};lineage='source-qualified-R2-rehearsal'
stem=Path('lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd');stock=(install/stem).resolve();helper=root/'qa-native-handoff'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
actual={k:sha(p) for k,p in art.items()};assert actual==expected,(actual,expected)
assert sha(stock)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert platform.machine()=='x86_64' and os.geteuid()==1000 and shutil.disk_usage(root).free>=8*1024**3
sdk=root/'sdk';sdk.mkdir(exist_ok=True);ru=root/'rustup';(ru/'toolchains').mkdir(parents=True,exist_ok=True);alias=ru/'toolchains/ohm'
if not alias.exists():alias.symlink_to(sdk)
stock_alias=root/'real-stock-wild';stock_alias.touch(exist_ok=True)
so=next((install/'lib').glob('librustc_driver-*.so')).name
cmd=['taskset','-c','24,25','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--bind',str(root),str(root),'--tmpfs','/tmp','--ro-bind',str(install),str(sdk),'--ro-bind',str(art['driver']),str(sdk/'lib'/so),'--ro-bind',str(art['cargo']),str(sdk/'bin/cargo'),'--ro-bind',str(stock),str(stock_alias),'--ro-bind',str(helper),str(sdk/stem),'--',sys.executable,'-IB',str(root/'witness.py'),str(root),label]
env={**os.environ,'RUSTUP_HOME':str(ru),'RUSTUP_AUTO_INSTALL':'0','PATH':str(Path.home()/'.cargo/bin')+':'+os.environ['PATH'],'OHM_QA_NATIVE_STOCK':str(stock_alias)}
binding={'lineage':lineage,'argv':cmd,'physical':actual,'wild':sha(stock),'qa':sha(helper),'source':sha(root/'witness.py'),'uid':os.geteuid(),'arch':platform.machine(),'floor':8*1024**3,'before':shutil.disk_usage(root).free}
(root/(label+'.binding.json')).write_text(json.dumps(binding,sort_keys=True,indent=2)+'\n')
cp=subprocess.run(cmd,env=env);binding.update(status=cp.returncode,after=shutil.disk_usage(root).free)
(root/(label+'.terminal.json')).write_text(json.dumps(binding,sort_keys=True,indent=2)+'\n');sys.exit(cp.returncode)
