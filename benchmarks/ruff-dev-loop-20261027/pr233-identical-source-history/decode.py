"""Decode the private/public crate IDs from real settled H5 parser and mixed library outputs."""
from pathlib import Path
import fcntl, hashlib, json, os, re, subprocess, sys
home=Path.home()
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
base=home/'.cache/ohm-233-position-qualified-20261027'
suite=base/'first-occurrence-classic-pr233-h5-v2'
proto=base/'pr233-three-parser-protocol-h5-v2'
control=base/'pr233-h5-control-v2'
w=base/'pr233-h5-private-parser-witness-v2'
sys.path.insert(0,str(proto))
from common import FROZEN,SONAME
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
assert (suite/'build-complete.json').exists() and not (suite/'failure.txt').exists()
assert sha(proto/'binding.json')=='74b5d88f422ccb9751653ca595d99a78c95c8b469f1d83a5749b7db1cdc99d3a'

meta={'missed':[],'pending':[]};assert not (w/'failure.txt').exists()
os.sched_setaffinity(0,{30});os.nice(14)
b=read(proto/'binding.json');plan=read(proto/'novel-plan.json')
env=dict(HOME=str(home),PATH=str(home/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(p/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(p/'registry-home'),LC_ALL='C.UTF-8')
rx=re.compile(r'^private hash ([0-9a-f]{32}) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]{32})',re.M)
data={'samples':{},'missed':meta['missed'],'pending':meta['pending'],'source_snapshot_program_sha256':sha(base/'pr233-h5-parser-witness-v2.py'),'runner':sha(proto/'binding.json'),'initial_registry_plugin':{}}
def selected(d,name):
    rows=[j for line in (d/'stdout').read_bytes().splitlines() if (j:=json.loads(line)).get('reason')=='compiler-artifact' and j['target']['name']==name and not j['profile']['test']]
    path,={path for row in rows for path in row['filenames'] if path.endswith('.so')};return Path(path)
def physical(state,path):
    for src,seg in ((p/'native-target','target'),(p/'shared','shared')):
        if path.is_relative_to(src):return state/seg/path.relative_to(src)
    raise ValueError(path)
for mode in ('build',):
    data['samples'][mode]={}
    for arm in 'BC':
        root=suite/'receipts'/mode/arm;state=suite/'state'/mode/arm
        old=base/'first-occurrence-classic-pr233-h5'
        builds=[(suite,state,root)]
        if mode=='build':builds.append((old,old/'state/build'/arm,old/'receipts/build'/arm))
        profiles=[]
        for cohort,st,rr in builds:
            pf=selected(rr/'original-baseline','get_size_derive2');f=physical(st,pf)
            orig=read(rr/'original-baseline/receipt.json')
            profiles.append({'cohort':cohort.name,'actual_registry_macro':pf.name,'actual_registry_so_sha256':sha(f),
                             'mixed':{cr:{k:m[k] for k in ('private_svh','public_svh','stable_crate_id','rmeta_sha256')} for cr,m in orig['product']['mixed'].items()}})
        data['initial_registry_plugin'][mode+'-'+arm]=profiles
        rows={};data['samples'][mode][arm]=rows
        for rec in sorted((w/mode/arm).glob('*/record.json')):
            st=read(rec);m=rec.parent/st['parser_rmeta_file'];assert sha(m)==st['rmeta_sha256'] and st['actual_driver']==b['arms'][arm]['driver_sha256']
            if st['rmeta_sha256'] in {z['parser_rmeta_sha256'] for z in rows.values()}:
                prev=next(z for z in rows.values() if z['parser_rmeta_sha256']==st['rmeta_sha256']);private,stable,public=prev['parsed_hashes']
                txtsha=prev['root_listing_sha256']
            else:
                cmd=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind',b['arms'][arm]['driver'],str(FROZEN/'lib'/SONAME),'--','rustc','+ohm','--sysroot',str(FROZEN),'-Zls=root',str(m)]
                try:
                    txt=subprocess.check_output(cmd,env=env,stderr=subprocess.PIPE)
                except subprocess.CalledProcessError as err:
                    raise RuntimeError((err.returncode,err.stderr[-1200:])) from err
                match=rx.search(txt.decode());assert match,txt[:450];private,stable,public=match.groups();txtsha=hashlib.sha256(txt).hexdigest()
            full=read(root/st['phase']/'receipt.json')
            rows[st['phase']]={'source':st['view'],'record_sha256':sha(rec),'parser_rmeta_sha256':st['rmeta_sha256'],'root_listing_sha256':txtsha,'parsed_hashes':[private,stable,public],
                'mixed':{cr:{k:m[k] for k in ('private_svh','public_svh','stable_crate_id','rmeta_sha256')} for cr,m in full['product']['mixed'].items()}}
print(json.dumps(data,sort_keys=True,indent=2))
