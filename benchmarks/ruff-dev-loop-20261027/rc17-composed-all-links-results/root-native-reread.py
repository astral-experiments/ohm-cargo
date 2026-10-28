"""Recompute every finished stock verifier output in a read-only physical namespace."""
from pathlib import Path
import collections
import contextlib
import fcntl
import hashlib
import io
import json
import socket
import sys

assert socket.gethostname()=='charlie-ohm-c5-check-1025' and not sys.flags.optimize
base=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
r=base/'whole-wild-width-v1';physical=base/'whole-wild-width-v2'
boot=base/'whole-wild-width-v2-bootstrap';cont=base/'whole-wild-width-v2-protocol'
assert r.samefile(physical) and (boot/'exit').read_text().strip()=='0'
assert (cont/'exit').read_text().strip()=='1' and (r/'exit').read_text().strip()=='1'
assert not (base/'early-scheduler-wall-rc17-v3c').exists()
def read(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def manifest(d,expected):
    assert sha(d/'SHA256SUMS')==expected
    for l in (d/'SHA256SUMS').read_text().splitlines():
        h,n=l.split('  ',1);assert sha(d/n)==h
manifest(r/'source','d116e7b75a81b1a5b8664248ab26425cc6ed4912abf7631e8cccdb4a14c7ead7')
manifest(cont/'source','fa7ba5a8f256ce55d4e44eabd3a6ab777d0a786d5e45942bf1bea5e8781522f8')
manifest(boot/'source','72fbc1e3b648cdd6a89ca117bf6ba8b4cb8a163e2610327389dbe5a97f58f159')
assert sha(r/'source/verify.py')=='ef9d5f2ae76597aea7070ca978909d7fa38ec69a369b4ad2ca058642ed8aca35'
assert sha(r/'continuation-failure.txt')=='89caf4045b6b3a8a76c48cf959f9603a9814cc4d2931504e134afaa62ef5f127'
assert sha(cont/'stderr')=='db0f412df381cb624919eaaf3b60f46dc7ad974eda534550308e8481075cdaf0'
sys.path.insert(0,str(base/'wall-protocol-v2'));sys.path.insert(0,str(r/'source'))
import verify as v
known={p for p in (r/'targets').iterdir() if p.is_dir()}
assert len(known)==50
expect={d/'all-widths.json' for d in known}|{r/'terminal.json',r/'independent.json',r/'wall-view.json'}
dirs=set();files=set();pids=set();outputs={}
def check_dir(self,*args,**kwargs):
    assert not args and not kwargs and self in known and self.is_dir() and self not in dirs
    dirs.add(self)
def check_output(path,obj):
    encoded=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
    assert path in expect and path not in files and encoded==path.read_bytes(),path.name
    files.add(path)
    outputs[str(path.relative_to(r))]=hashlib.sha256(encoded).hexdigest()
original=v.process
def process(tr,pid,argv):
    key=(tr,pid)
    assert key not in pids
    pids.add(key)
    return original(tr,pid,argv)
with (base/'combined-native-measure.lock').open('r') as l:
    fcntl.flock(l,fcntl.LOCK_SH|fcntl.LOCK_NB)
    # All acquisition paths are read-only. These two verifier output operations become byte comparisons.
    v.write=check_output;v.process=process
    prior=Path.mkdir
    try:
        Path.mkdir=check_dir
        with contextlib.redirect_stdout(io.StringIO()) as captured:v.verify()
    finally:Path.mkdir=prior
assert files==expect and dirs==known and len(pids)==9867
ind=read(r/'independent.json');assert json.loads(captured.getvalue())==ind and ind['accepted']
view=read(r/'wall-view.json')
assert len(view['targets'])==50 and sum(map(len,view['fresh'].values()))==297
for name,row in ind['registry'].items():
    f=r/row['file'];assert sha(f)==row['sha256'] and len(read(f))==78
assert len(ind['registry'])==4 and ind['explicit_reported_and_plain']==9568 and ind['ordinary_stock_controls']==299
hold=read(r/'physical-preservation.json');seed=read(r/'tree-before-resume.json')
assert seed['cross_root_regular_inode_overlap']==0 and seed['preserved_original']==seed['byte_matched_copy']
assert hold['old_complete_tree_final_sha256']==seed['preserved_original']['digest']=='4b91f1b8d572612351ea5261e0bd3fdc0444ebc62d18ec64e51a3a4cf0cd0237'
report=dict(independent_review='accepted',historical_native_ref=v.NREF,workspace_linked_targets=50,fresh_occurrences=297,registry_exact=78,
            view_sha256=sha(r/'wall-view.json'),terminal_sha256=sha(r/'terminal.json'),verifier_receipt_sha256=sha(r/'independent.json'),
            original_verifier_sha256=sha(r/'source/verify.py'),reopened_unique_stock_processes=len(pids),explicit_processes=9568,ordinary_controls=299,
            byte_recomputed_outputs=outputs,previous_v2_startup_failure_sha256=sha(r/'continuation-failure.txt'),
            full_predecessor_commitment=hold['old_complete_tree_final_sha256'],counted_clocks=0,read_only=True)
print(json.dumps(report,sort_keys=True,indent=2))
