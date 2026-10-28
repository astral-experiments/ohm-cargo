from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
assert not any(w.iterdir())and not any(t.iterdir())and not any(s.iterdir())and not any(r.iterdir())
before=guard();orig=q/'reference';assert git('rev-parse','HEAD',cwd=orig).decode().strip()==plan['pin']
oldobjects=Path(git('rev-parse','--path-format=absolute','--git-path','objects',cwd=orig).decode().strip());osh=Path(git('rev-parse','--path-format=absolute','--git-path','shallow',cwd=orig).decode().strip())
assert oldobjects.is_dir()and osh.is_file()
go(['git','init','-q',w]);(w/'.git/objects/info/alternates').write_text(str(oldobjects)+'\n');shutil.copy2(osh,w/'.git/shallow')
pack=(q/'ops/revisions.pack').read_bytes();assert H(pack)==plan['sha_pack'];go(['git','index-pack','--stdin','--fix-thin'],input=pack)
go(['git','switch','--detach',plan['heads']['A']]);view('A');diff=git('diff','--name-only','-z',plan['pin'],'HEAD').split(b'\0');unmatched=set(diff)
touched=0
for n in git('ls-files','-z').split(b'\0')[:-1]:
 if n in unmatched:continue
 src=orig/os.fsdecode(n);dest=w/os.fsdecode(n);assert src.is_file()and dest.is_file()
 srcst=src.lstat();os.utime(dest,ns=(srcst.st_atime_ns,srcst.st_mtime_ns),follow_symlinks=False);touched+=1
for tag,dst in [('target',t),('shared',s),('registry-home',r)]:
 monitor(['cp','-a','--reflink=auto','--',str(seed/tag)+'/.',dst],q/('copy-'+tag+'.stdout'),q/('copy-'+tag+'.stderr'))
 assert sum(1 for _ in (seed/tag).iterdir())==sum(1 for _ in dst.iterdir())
f=seed/'target/debug/ruff';d=t/'debug/ruff';assert not os.path.samefile(f,d)and sha(f)==sha(d)
release={'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','driver':next((sdk/'lib').glob('librustc_driver*.so')),'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
actual={k:sha(v)for k,v in release.items()};assert actual==plan['release'];view('A')
put(q/'prepared.json',{'before':before,'after':guard(),'seed_cli':sha(d),'source_mtime_restored_entries':touched,'unshared_seed':not os.path.samefile(f,d),'private_filesystems':{str(f):[f.stat().st_dev, f.stat().st_ino]for f in (t,s,r,w,ram)},'source_pin':plan['pin'],'release':actual,'seed_version':json.loads(go([d,'version','--output-format','json']).stdout),'heads':plan['heads']});print('prepared',touched,flush=True)
