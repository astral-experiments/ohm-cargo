#!/usr/bin/env python3
"""Replay the portable input/identity gates; optional local trees and binaries add direct checks."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--checkout',type=Path)
ap.add_argument('--binaries',type=Path,help='Directory containing A/cargo and B/cargo')
args=ap.parse_args()
root=Path(__file__).resolve().parent;read=lambda n:json.loads((root/n).read_bytes())
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
s=read('attestation.json');r=read('rust-inputs.json');n=read('native-inputs.json')
assert s['qualified'] and not s['historical_control_byte_identical'] and s['historical_control_sha256'].startswith('6aaa263e')
assert not s['first_preflight']['admitted'] and s['first_preflight']['compiler_commands']==0
assert s['old_independent_candidate']['excluded'] and s['old_independent_candidate']['differing_ordered_externs']==12
assert s['old_independent_candidate']['differing_unique_crates']==['curl','futures_timer','git2','gix','rusqlite','rustc_stable_hash']
assert len({x['binary_sha256'] for x in s['roles'].values()}|{s['old_independent_candidate']['binary_sha256'],s['historical_control_sha256']})==4
assert s['common_pgo_sha256']=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7'
commits={'A':'235f9228651b74c591e6f62cae4c9b761448dd2d','B':'b3360c5eda186845b9a2ba6e5330a97c07d4acf2'}
trees={}
for arm,v in s['roles'].items():
    assert v['commit']==commits[arm] and v['effective_uid']==1000 and v['root_uid']==0 and v['source_files']==3108
    f=root/(arm+'.ls-tree');assert sha(f)==v['source_inventory_sha256']
    tree={e.split(b'\t',1)[1]:e.split(b'\t',1)[0] for e in f.read_bytes().split(b'\0') if e}
    assert len(tree)==v['source_files'];trees[arm]=tree
    assert all(v['extern_counts'][p]==len(rows) for p,rows in r.items())
    if args.checkout:
        assert subprocess.check_output(['git','-C',args.checkout,'ls-tree','-rz',v['commit']])==f.read_bytes()
        assert subprocess.check_output(['git','-C',args.checkout,'rev-parse',v['commit']+'^{tree}'],text=True).strip()==v['tree']
    if args.binaries:
        b=(args.binaries/arm/'cargo').resolve()
        assert sha(b)==v['binary_sha256'] and b.stat().st_size==v['bytes']
        assert subprocess.check_output([b,'-Vv'],text=True)==s['control_version']
assert trees['A'].keys()==trees['B'].keys() and [f for f in trees['A'] if trees['A'][f]!=trees['B'][f]]==[b'src/compiler/fingerprint/mod.rs']
assert s['roles']['A']['rustc_argv_sha256']==s['roles']['B']['rustc_argv_sha256']
count=0;own=[]
for p,items in r.items():
    assert [x['order'] for x in items]==list(range(len(items)))
    for x in items:
        assert all(re.fullmatch('[0-9a-f]{64}',x[k]) for k in ('path_sha256','A_sha256','B_sha256'))
        if p=='src/bin/cargo/main.rs' and x['crate']=='cargo':own.append(x);continue
        assert x['A_sha256']==x['B_sha256'];count+=1
assert count==s['ordered_stable_externs']==239 and len(own)==2
assert any(x['library_extension']=='.rlib' and x['A_sha256']!=x['B_sha256'] for x in own)
assert s['current_pair']['candidate_recompiled_packages']==['cargo']
assert len(n['common_argument_sha256'])==s['current_pair']['selected_native_argument_count']==411
assert len(n['common_file_operands'])==s['current_pair']['independent_linker_file_observations']==335
assert sum(r['suffix']=='.rlib' for r in n['common_file_operands'].values())==s['current_pair']['independent_linker_rlib_observations']==326
assert len(n['rust_native_search_dir_files'])==s['native_search_directories']==6
assert sum(map(len,n['rust_native_search_dir_files'].values()))==s['native_regular_inputs']==404
assert len(n['build_tools'])==s['physical_tool_count']==6
assert n['raw_private_receipt_sha256']==s['native_inputs_sha256']
assert set(n['generation'])=={'A','B'}
for role,rec in n['generation'].items():
    assert sorted(rec['role_args'])==['gcc-resolution','rustc-raw-dylibs','rustc-symbols']
    for key,v in rec['role_args'].items():
        assert n['common_argument_sha256'][v['index']]==hashlib.sha256(('<'+key+'>').encode()).hexdigest()
print('Verified 3,108 source files per arm, one changed product source, two literal rustc commands, 239 nonproduct externs, 326 linked dependency/SDK rlibs, and the excluded independent pair.')
