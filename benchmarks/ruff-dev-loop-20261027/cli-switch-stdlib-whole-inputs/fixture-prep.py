"""Prepare a pinned changed-view of just the two historical source paths and the private study layout."""
from pathlib import Path
import base64,hashlib,json,os,shutil,subprocess,sys
H=Path.home();P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');W=H/'code/oss/ruff-ohm-whole-native-20261027';Q=P/'cli-switch-native609e-v1';T=Q/'target';S=Q/'shared';R=Q/'registry-home';B=Q/'before';E=Q/'edited';x=H/'.cache/ohm-cli-switch-609e-native-v1';M=Path('/dev/shm/ohm-cli-switch-native609e-v1');N=Path('/run/user/1000/ohm-cli-switch-native609e-v1')
D=Path('/run/user/1000/ohm-cli-switch-selected16-20261027-v2');old=P/'build-script-producer-reuse16-v1'
sha=lambda b:hashlib.sha256(b).hexdigest()
orig='93526150df078af7dd8fc4226cdcc469539d2001';target='609e184aa35f0034b7ef63e3e04327081c484af6';file=Path('crates/ruff_python_stdlib/src/builtins.rs');folder=Path('crates/ruff_linter/resources/mdtest/pyflakes')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip()==orig and not subprocess.check_output(['git','status','--porcelain','-uno'],cwd=W)
for d in (Q,x,M,N):d.mkdir(exist_ok=False)
for d in (T,S,R,B,E,Q/'records',Q/'src',Q/'runtime-cwd'):d.mkdir()
patch=(Q/'historical.patch');patch.write_bytes(base64.b64decode(sys.stdin.buffer.read()));assert sha(patch.read_bytes())=='37b435620d826e6cbeccf3830c23b745bc63c6691e860d3c0421cc9894c90d4b'
for s in (B,E):
    (s/file).parent.mkdir(parents=True);shutil.copy2(W/file,s/file);(s/folder).parent.mkdir(parents=True);shutil.copytree(W/folder,s/folder,copy_function=shutil.copy2)
subprocess.run(['git','apply','--check','--reverse',str(patch)],cwd=E,check=True)
subprocess.run(['git','apply','--reverse',str(patch)],cwd=E,check=True)
assert sha((B/file).read_bytes())!=sha((E/file).read_bytes())
assert (B/folder/'undefined-name.md').is_file() and not(E/folder/'undefined-name.md').exists()
env=dict(HOME=str(H),PATH=str(H/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',LC_ALL='C.UTF-8',RUSTUP_HOME=str(old/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(R),CARGO_TARGET_DIR=str(T),CARGO_BUILD_BUILD_DIR=str(S),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='6',GIT_OPTIONAL_LOCKS='0')
def which(t):return Path(subprocess.check_output(['rustup','which','--toolchain','ohm',t],env=env,text=True).strip())
c=which('cargo');rc=which('rustc');assert sha(c.read_bytes())=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568' and sha(rc.read_bytes())=='b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5'
data={'pin':orig,'patch':target,'patch_sha256':sha(patch.read_bytes()),'cargo':sha(c.read_bytes()),'rustc':sha(rc.read_bytes()),'parent_rust_dir':str(c.parent.parent),'source_blobs':{k:sha((s/file).read_bytes())for k,s in [('original',B),('reversed',E)]},'release_graph':sha((D/'survey.json').read_bytes()),'source_file':str(file),'fixture_dir':str(folder),'copy_limit':{'scratch_home_tmpfs_floor':25*2**30,'run_user_floor':750*2**20},'targets':str(Q)}
(Q/'binding.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(json.dumps(data,sort_keys=True))
