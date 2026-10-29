from pathlib import Path
import json,hashlib,collections,sys
p=Path.home()/'.cache/ohm-ty-vendored-script-consumer-20261028-v1'
def sha(p):
    return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
cases=[]
for logfile in sorted(p.glob('*/cargo.out')):
    try:rows=[json.loads(l)for l in logfile.read_text().splitlines()]
    except ValueError:continue
    if not rows or not rows[-1].get('success'):continue
    libs=[]
    for r in rows:
        if r.get('reason')!='compiler-artifact':continue
        for filename in r['filenames']:
            f=Path(filename)
            if f.suffix!='.rlib':continue
            libs.append({'name':r['target']['name'],'local':r['package_id'].startswith('path+file:'),'output':f.name,'output_parent_role':f.parent.name if f.parent.name in ('debug','out','deps') else 'other','fresh':r['fresh']})
    cases.append({'case':logfile.parent.name,'rows_sha256':sha(logfile),'all_archive_count':len(libs),'rooted':sorted(z['name']for z in libs if z['output_parent_role']=='debug'),
        'local_libraries':sorted([z for z in libs if z['local']],key=lambda z:z['name']),
        'unit_output_roster_sha256':hashlib.sha256(json.dumps(libs,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
assert cases
for c in cases: print(c['case'],c['all_archive_count'],c['rooted'],[(a['name'],a['output_parent_role'])for a in c['local_libraries']])
y=Path(__file__).resolve().parent/'archive-fs-restore/incumbent'
(y/'scoped.json').write_text(json.dumps({'command':['cargo','+ohm','build','--locked','--offline','-p','ty_vendored','--message-format=json'],'previous_fresh_root':'pinned published -18 historical ty_vendored study','systype':'existing exec/open/clone trace did not trace unlink or rename','rows':cases},sort_keys=True,indent=2)+'\n')
