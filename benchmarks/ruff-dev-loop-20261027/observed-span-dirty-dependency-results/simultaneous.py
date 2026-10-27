"""A dirty prerequisite never excuses validation of a genuinely changed reader-local source."""
import gzip,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paired import Study,getargs,sha,log_json
s=Study(getargs());a=s.init('simultaneous')
without=('-Zohm-worktree-seeds=no',)
for i in range(3):r=s.run(a,'C',f'check-prime-{i}',trace=True,extra=without,mode='check',check_product=False)
assert not r['roster']
deps=[p for p in (a/'target').rglob('libhold_shapes-*.rmeta') if p.is_file()]
assert deps and len({sha(p) for p in deps})==1
old=sha(deps[0]);t=a/'src/hold_shapes/src/types.rs';time.sleep(.03);os.utime(t,None)
# The dependency is now mtime-dirty but should emit exactly the same metadata.
b=a/'src/hold_bridge/src/lib.rs';b.write_text(b.read_text()+'pub const MISMATCH: usize="not a number";\n')
r=s.run(a,'C','simultaneous-check',trace=True,extra=without,mode='check',check_product=False,expect=False)
raw=gzip.decompress((s.logs/'simultaneous-check/stderr.gz').read_bytes())
assert r['status']!=0 and b'E0308' in raw
assert {'hold_bridge','hold_shapes'} <= {x['crate'] for x in r['roster'] if x['mode']=='full'},r
assert all(sha(p)==old for p in deps if p.exists()),'producer metadata unexpectedly changed'
# Changing a reader's symlink on mtime-mode Cargo must track the lexical input retained in its receipt.
a=s.init('lexical');f=a/'src/hold_direct/src/main.rs';src=f.read_bytes();before=f.with_name('bank-a.rs');after=f.with_name('bank-b.rs')
f.rename(before);after.write_bytes(src.replace(b'println!("{} {}"',b'println!("{}={}"'));assert before.read_bytes()!=after.read_bytes() and before.stat().st_size==after.stat().st_size
mtime=before.stat().st_mtime_ns
for p in [before,after]:os.utime(p,ns=(mtime,mtime))
f.symlink_to(before.name)
for i in range(3):r=s.run(a,'C',f'symlink-prime-{i}',extra=without,trace=True)
assert not r['roster']; previous=r['native_products']['hold_direct']['output']
link=f.with_name('new-link');link.symlink_to(after.name);os.replace(link,f)
r=s.run(a,'C','retarget-preserved-mtime',extra=without,trace=True)
assert {x['crate'] for x in r['roster'] if x['mode']=='full'}=={'hold_direct'}
v=r['native_products']['hold_direct'];assert v['output']==previous.replace(' ','=',1)
cold=dict(CARGO_TARGET_DIR=str(a/'emptytarget'),CARGO_BUILD_BUILD_DIR=str(a/'emptyshared'))
r=s.run(a,'P','symlink-empty',extra=without,trace=True,envadd=cold,check_product=False)
import subprocess
g=subprocess.check_output([str(a/'emptytarget/debug/hold_direct')],text=True).strip()
assert g==v['output']
log_json(s.logs/'guard.json',{'subjects':s.digest,'identical_metadata_on_mtime_refire':old,'simultaneous_type_error':'E0308','retargeted_output':v,'independent':g})
