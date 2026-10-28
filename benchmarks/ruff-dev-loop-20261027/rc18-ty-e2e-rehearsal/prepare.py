"""Create isolated Ruff source, authenticated offline registry, and clean build paths."""
from pathlib import Path
import hashlib, json, os, shutil, socket, subprocess, tomllib

R=Path.home()/'.cache/ohm-18-ty-e2e-link-20261028'
P=Path.home()/'.cache/ohm-rc18-r2-whole-ruff-20261028'
W=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
assert socket.gethostname()=='charlie-ohm-c5-check-1025' and shutil.disk_usage(R).free>120*2**30
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(root,*args):return subprocess.check_output(['git','--no-optional-locks','-C',root,*args])
pin='93526150df078af7dd8fc4226cdcc469539d2001'
rc=json.loads((P/'prepare.done').read_text())
assert git(P/'source','rev-parse','HEAD').decode().strip()==pin and not git(P/'source','status','--porcelain','-z')
assert (P/'source/.git').is_dir() and not (P/'source/.git').is_symlink()
source=R/'source';assert not source.exists()
subprocess.run(['cp','-a','--reflink=auto',P/'source',source],check=True)
assert git(source,'rev-parse','HEAD').decode().strip()==pin and not git(source,'status','--porcelain','-z')
assert hashlib.sha256(git(source,'ls-files','--stage','-z')).hexdigest()==rc['source_index']
crates=[c for c in tomllib.loads((source/'Cargo.lock').read_text())['package'] if 'source' in c]
reg=W/'registry-seed-v2'
registry_id=json.loads((W/'registry-v2.json').read_text())
cache,=[p for p in (reg/'registry/cache').iterdir() if hashlib.sha256(p.name.encode()).hexdigest()==registry_id['offline_registry_id_sha256']]
assert sha(reg/'registry/index'/cache.name/'config.json')==registry_id['offline_registry_config_sha256']
assert len(crates)==498 and not (reg/'credentials.toml').exists() and not (reg/'registry/src').exists()
for c in crates:
    assert c['source']=='registry+https://github.com/rust-lang/crates.io-index' and sha(cache/(c['name']+'-'+c['version']+'.crate'))==c['checksum']
subprocess.run(['cp','-a','--reflink=auto',reg,R/'cargo'],check=True)
for d in ('target','shared','home','tmp','reports','stores','saved','rustup/toolchains','install'):
    (R/d).mkdir(parents=True,exist_ok=False)
(R/'rustup/toolchains/ohm').symlink_to(P/'sdk',target_is_directory=True)
ref='crates/ty_server/src/document/range.rs'; original=(source/ref).read_bytes()
before=b'return Some(offset.min(cell_range.end()));';after=b'return Some(offset);'
assert original.count(before)==1 and before in git(source,'show',pin+':'+ref)
patch=original.replace(before,after)
result={'source':pin,'index_sha256':rc['source_index'],'packages':len(crates),'historical_fix':'eb9e9bdcf988fffcd619dcf5d2a2bd74d75be1c6','file':ref,'old_sha256':hashlib.sha256(original).hexdigest(),'edited_sha256':hashlib.sha256(patch).hexdigest(),'root':str(R),'previous_sdk_for_rehearsal':str(P/'sdk'),'registry_id_digest':registry_id['offline_registry_id_sha256']}
(R/'prepared.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps(result),flush=True)
