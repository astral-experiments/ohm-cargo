"""Check genuine same-thread and child creation ordering for every original library path."""
import json
import hashlib
import re
import sys
import subprocess
from pathlib import Path
r=Path(__file__).resolve().parent
def read(n):return json.loads((r/n).read_bytes())
good=lambda h: bool(re.fullmatch('[0-9a-f]{64}',h))
v=read('whole.json')['rows']
assert len(v)==len({z['crate']for z in v})==32
assert len([z for z in v if z['crate']!='ruff_python_ast'])==31
for z in v:
    u=z['cargo_unlink'];ren=z['rustc_publish'];drop=z['cargo_unlink_old_uplift'];up=z['cargo_link_new_uplift'];branch=z['spawn_branch']
    assert z['prior_reported_rlib']==z['current_reported_rlib']==['lib'+z['crate']+'.rlib']
    assert u['names']==[z['unit_rlib']] and ren['names']==['tmp.a',z['unit_rlib']]
    assert all(x['success'] and x['errno']is None and good(x['file_line_sha256']) for x in [u,ren,drop,up])
    assert u['tid']==drop['tid']==up['tid']
    assert branch[0][0]==z['rustc_root'] and branch[-1][1]==u['tid'] and not branch[-1][-1]
    for first,second in zip(branch,branch[1:]):assert first[1]==second[0]
    assert u['line']<branch[-1][2]<drop['line']<up['line']
    assert up['line']==drop['line']+1 and up['names']==[z['unit_rlib'],z['current_reported_rlib'][0]]
    assert [u['syscall'],ren['syscall'],drop['syscall'],up['syscall']]==['unlink','rename','unlink','linkat']
    assert good(z['spawn_raw_line_sha256']) and not z['writes_other_than_unlinks_rename_reuplift']
sc=read('scoped.json')['rows'];assert len(sc)==9
for z in sc:
    assert z['all_archive_count']==148 and z['rooted']==['ty_vendored'] and good(z['rows_sha256'])
    root=[j for j in z['local_libraries']if j['name']=='ty_vendored']
    parser=[j for j in z['local_libraries']if j['name']=='ruff_python_parser']
    assert len(root)==len(parser)==1 and root[0]['output_parent_role']=='debug' and parser[0]['output_parent_role']=='out'
disk=read('aftermath.json')
assert {z['crate']for z in disk['whole_workspace']}=={z['crate']for z in v}
assert all(z['incremental_rlib_count_after']==0 and z['links_after']>=2 and z['unit_uplift_same_after'] and good(z['published_sha256']) for z in disk['whole_workspace'])
tmp=disk['separate_package_selected'];assert {z['state']for z in tmp}=={'cold','warm'}
assert all(not z['top_level_parser_rlib'] and [j['name']for j in z['root_archive_files']]==['libty_vendored.rlib']for z in tmp)
a=read('individual-alignment.json');assert a['alignment']==4096 and a['initial_object_file_offset']==0
am=a['rows'];assert len(am)==31 and sum(z['native_objects']for z in am)==4306
align=[(z['crate'],o)for z in am for o in z['aligned']]
assert len(align)==2 and all(k=='ruff_db' and o['offset']%4096==0 and good(o['sha256'])for k,o in align)
assert sum(o['whole_pages_bytes']for k,o in align)==45056
whole=r.parent/'rc18-ruff-fstring-private-cutoff';layout=r.parent/'rc18-parser-cgu-alias-operations'
if whole.exists() and layout.exists():
    assert json.loads(subprocess.check_output([sys.executable,'-IB',r/'reproduce/object_offsets.py',whole,layout]))==a
    assert hashlib.sha256((whole/'SHA256SUMS').read_bytes()).hexdigest()=='a070a8dbba5b3ce8a873bc314d6adf8d203965be5c3c46de9c22395d8ee76bd9'
    assert hashlib.sha256((layout/'SHA256SUMS').read_bytes()).hexdigest()=='6d3ef263d86741c5670bac21662aa6558cea4569f981db260ba984f545595e9e'
print('31 downstream and the edited producer removed before rustc; 32 old uplifts replaced; 9 real package-selected builds; only 2/4,306 individually aligned')
