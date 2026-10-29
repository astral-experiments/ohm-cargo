"""Swap only Cargo at a stable SDK path and check the existing target after each upgrade."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess as sp,sys
q=Path(__file__).resolve().parent
root=q/'stable-target-and-sdk'
assert not root.exists() and root.parent.stat().st_uid==os.getuid()
assert shutil.disk_usage(root.parent).free>105*2**20 and shutil.disk_usage(q).free>24*2**30+600*2**20
root.mkdir(mode=0o700);sdk=root/'constant-sdk';(sdk/'bin').mkdir(parents=True)
original=q/'official19-published-linux-signed/sdk'
rustc='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511'
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
tools={
    'released':(original/'bin/cargo','789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1'),
    'original_282':(q/'asm-h4-a8f0c9aa0/cargo','ad893345f66ade1c886309b0fc2f98ec5b225d206c176e356531f0e3467eff81'),
    'original_284':(q/'measured-h4-8dc33c9cc/cargo','8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5'),
    'fixed':(q/'measured-h4-e2fa457aa/cargo','6d0449d4eb0aa490e04aa553bab278c7818efe2c7d529b1d5c9536f01ef90168')}
for label,(p,sha) in tools.items():assert h(p)==sha,label
assert h(original/'bin/rustc')==rustc
(sdk/'bin/rustc').symlink_to(original/'bin/rustc');(sdk/'lib').symlink_to(original/'lib',target_is_directory=True)
changes=[]
def swap(label):
    p,sha=tools[label];tmp=sdk/'bin/cargo.next';tmp.symlink_to(p);os.replace(tmp,sdk/'bin/cargo')
    assert h(sdk/'bin/cargo')==sha
    changes.append(dict(label=label,cargo=sha,version=sp.check_output([sdk/'bin/cargo','-Vv'],text=True)))
swap('released')
helper=q/'qualify-relink-collection-verdict.py';assert h(helper)=='5ed55ae83de8b1238c2504ba1a59702435a8e12318b6ea4415b2ec74d7feb2df'
body,sep,_=helper.read_text().partition("for arm,positive in [('implicit','default'),('explicit','yes')]:");assert sep
# The small private tmpfs is reserved for this fixture. The independent benchmark's
# durable volume retains its 45-GiB floor, checked above and again before each arm.
guard='assert shutil.disk_usage(dest.parent).free > 45*2**30 + 600*2**20'
assert body.count(guard)==1;body=body.replace(guard,'assert shutil.disk_usage(dest.parent).free > 100*2**20')
dest=root/'experiment';sys.argv=[str(helper),str(dest),str(sdk),tools['released'][1],rustc]
scope={};exec(compile(body,'verified-verdict-harness','exec'),scope);rows=scope['rows']
def call(arm,label,flag,status,root_count):
    scope['visit'](arm,label,flag);r=rows[-1];assert (r['exit'],r['root_rustc'])==(status,root_count),(arm,label,r)
    r['selected_cargo']=changes[-1]['label'];r['selected_cargo_sha']=changes[-1]['cargo']
    assert r['root_emit']==([flag!='no'] if root_count else []),(arm,label)
    if not status:assert r['runtime']=='17'
for arm in ['direct','development']:
    assert shutil.disk_usage(q).free>24*2**30+600*2**20 and shutil.disk_usage(root).free>68*2**20
    swap('released' if arm=='direct' else 'original_282')
    call(arm,'seed','default',0,1);call(arm,'seed-fresh','default',0,0)
    call(arm,'false-success','no',0,0);call(arm,'false-success-repeat','no',0,0)
    if arm=='development':
        swap('original_284');call(arm,'different-cargo-same-old-key','no',0,0)
    swap('fixed');call(arm,'upgrade-detects-error','no',101,1);call(arm,'error-repeat','no',101,1)
    call(arm,'recover','default',0,1);call(arm,'recover-fresh','default',0,0)
call('empty','clean','no',101,1)
assert len(set(json.dumps(x['errors'],sort_keys=True) for x in rows if x['exit']==101))==1
assert {n:h(scope['source']/n) for n in scope['files']}==scope['pins']['sources']
record=dest/'migration.json';record.write_text(json.dumps(dict(sdk_path_stable=True,cargo_images=changes,rows=rows),sort_keys=True,indent=2)+'\n');(dest/'terminal.json').write_text(json.dumps(dict(migration=h(record),inputs=h(dest/'inputs.json'),helper=h(helper),driver=h(Path(__file__)),visits=len(rows)),indent=2)+'\n');print('verified signed and same-key development upgrades',len(rows),h(record),flush=True)
