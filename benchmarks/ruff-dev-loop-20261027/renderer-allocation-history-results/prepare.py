from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
assert not any(w.iterdir())and not any(t.iterdir())and not any(s.iterdir())and not any(r.iterdir())
before=guard();orig=q/'reference';assert git('rev-parse','HEAD',cwd=orig).decode().strip()==plan['pin']
monitor(['cp','-a','--reflink=auto','--',str(orig)+'/.',w],q/'copy-source.stdout',q/'copy-source.stderr')
assert git('rev-parse','HEAD').decode().strip()==plan['pin']and not git('status','--porcelain','-z')
assert H((q/'ops/edit.patch').read_bytes())==plan['patch'] and H((q/'ops/reader.rs').read_bytes())==plan['caller']
assert all(sha(w/n)==v for n,v in plan['sha_original'].items())
go(['git','apply','--reverse','--check',q/'ops/edit.patch'])
for tag,dst in [('target',t),('shared',s),('registry-home',r)]:
 monitor(['cp','-a','--reflink=auto','--',str(seed/tag)+'/.',dst],q/('copy-'+tag+'.stdout'),q/('copy-'+tag+'.stderr'))
 assert sum(1 for _ in (seed/tag).iterdir())==sum(1 for _ in dst.iterdir())
f=seed/'target/debug/ruff';d=t/'debug/ruff';assert not os.path.samefile(f,d)and sha(f)==sha(d)
release={'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','driver':next((sdk/'lib').glob('librustc_driver*.so')),'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
actual={k:sha(v)for k,v in release.items()};assert actual==plan['release']
put(q/'prepared.json',{'before':before,'after':guard(),'seed_cli':sha(d),'unshared_seed':not os.path.samefile(f,d),'private_filesystems':{str(f):[f.stat().st_dev, f.stat().st_ino]for f in (t,s,r,w,ram)},'source_pin':plan['pin'],'release':actual,'seed_version':json.loads(go([d,'version','--output-format','json']).stdout)});print('prepared',plan['pin'],flush=True)
