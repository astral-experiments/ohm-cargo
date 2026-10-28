"""Verify the real Ruff archive differences and the two compiled worktree/clean verdicts."""
from pathlib import Path
import gzip,hashlib,json
p=Path(__file__).resolve().parent
def read(n):
 data=(p/n).read_bytes()
 return json.loads(gzip.decompress(data) if n.endswith('.gz') else data)
def dig(b):return hashlib.sha256(b).hexdigest()
a=read('independent-real-script.json');m=read('independent-members.json.gz');w=read('workspace-transition.json');m2=read('workspace-members.json.gz');t=read('ordinary-seeded-worktrees.json')
assert a['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001' and a['build_script']=='5f3d2658fb5ada26e626804213f60918e287ac91c86314e8e52fa6d8bf553c05'
assert (a['tracked'],a['all_files_and_directories'],a['observations_per_tree'])==(772,835,2)
assert m['contents']==m2['contents'] and len(m['contents'])==len(set(n for n,_ in m['contents']))==819
all_names=sorted(n for n,_ in m['contents'])
for order in (*m['orders'].values(),*m2['orders'].values()):assert sorted(order)==all_names
for k,f in a['records'].items():
 assert f['order']==dig(b'\0'.join(n.encode() for n in m['orders'][k]))
 assert f['contents']==dig(json.dumps(m['contents'],separators=(',',':')).encode())
 assert f['members']==819 and f['bytes']==5577690
assert len({f['whole_zip'] for f in a['records'].values()})==len({f['fs_device'] for f in a['records'].values()})==3
assert len({f['source'] for f in a['records'].values()})==1
for k,comparison in a['compared_to_root'].items():
 changes=[(i,x,y) for i,(x,y) in enumerate(zip(m['orders']['root'],m['orders'][k],strict=True)) if x!=y]
 assert list(changes[0])==comparison['first_position_with_different_order'] and len(changes)==comparison['reordered_positions']
assert len(w['extra_dirty'])==15 and len({tuple(x) for x in w['extra_dirty']})==15
o,v=w['files'].values();assert o['deps']==v['deps'] and [x['local'][0]['Precalculated'] for x in (o,v)]==['1792012558.000000000s (Cargo.toml)','1792012558.000000000s (build.rs)']
real=w['observed_archives']['arms'];key=next(k for k in real['official'] if k.startswith('6b90'))
assert real['official'][key]['sha256']!=real['scratch-first'][key]['sha256']
for k in ('official','scratch-first'):
 assert real[k][key]['sha256']==m2['original_archive_sha256'][k] and real[k][key]['bytes']==1565618
assert real['matched-copy']==real['official'] and m2['orders']['official'][0]=='source_commit.txt' and m2['orders']['scratch-first'][0]=='LICENSE'
assert t['sdk']['images']['cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573'
for case,r in t['cases'].items():
 assert r['worktree']['seeded'] and r['worktree']['git_worktrees']==2 and '80 reflinked files' in r['worktree']['messages'][0]
 assert r['same_bytes'] and r['tracker_count']==38 and r['same_tracked_mtimes']==(38 if case=='equal-times' else 0)
 for n in ('donor','donor-repeat','recipient','recipient-repeat','empty'):assert r[n]['cargo_rc']==0 and r[n]['source_order']==r[n]['native_output']
 assert r['donor_order_differs'] and r['donor']['native_output']!=r['recipient']['native_output']==r['empty']['native_output']
 assert r['recipient']['actual_script_execs']==r['empty']['actual_script_execs']==1 and r['recipient-repeat']['actual_script_execs']==0
 assert r['recipient']['elf_sha256']==r['recipient-repeat']['elf_sha256']==r['empty']['elf_sha256']
rerun=read('portable-rerun.json')
assert rerun['runner_sha256']==dig((p/'worktree-replay.py').read_bytes()) and rerun['raw_result_sha256']=='504102c1e2aee7eb0dddf8786140cf780165b6b072b2c8acca4524f69d6b1f8e'
for case,r in rerun['cases'].items():
 assert r['same_bytes'] and r['tracker_count']==38 and r['same_tracked_mtimes']==(38 if case=='equal-times' else 0)
 assert r['worktree']['seeded'] and 'Seeded 83 files' in r['worktree']['messages'][0] and '80 reflinked files' in r['worktree']['messages'][0]
 assert r['donor_order_differs'] and r['donor']['native_output']!=r['recipient']['native_output']==r['empty']['native_output']
 for phase in ('donor','recipient','empty','donor-repeat','recipient-repeat'):
  assert r[phase]['cargo_rc']==0 and r[phase]['native_output']==r[phase]['source_order']
  assert r[phase]['actual_script_execs']==(0 if phase.endswith('repeat') else 1)
 assert r['recipient']['elf_sha256']==r['recipient-repeat']['elf_sha256']==r['empty']['elf_sha256']
print('Verified 819 member payloads across five observed serializations, 15 additional dirty units and four genuine 80-reflink imports matching clean executables.')
