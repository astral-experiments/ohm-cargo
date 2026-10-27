"""Use the exact Ruff source edit through an external native Cargo consumer and both PGO+BOLT compilers."""
from pathlib import Path
import collections,hashlib,json,os,shutil,subprocess
base=Path(__file__).resolve().parent;root=base.parent;n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');sr=n/'trait-pgo-state';rt=sr/'sysroot';repo=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');src=Path('crates/ruff_source_file/src/line_index.rs');parent='93526150df078af7dd8fc4226cdcc469539d2001';patch_sha='914a91f649098a291c8796f446c5d28da80c6551cc33944489f10f239c859035';commit='88d851449d2345e11da991794f3e9bfbbd666719';patch=Path('/home/dev-user/.cache/ohm-ruff-whole-skips-20261027/patches/line-index.patch');lib='librustc_driver-774a793a844d5500.so'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(patch)==patch_sha and (subprocess.check_output(['git','--no-optional-locks','-C',repo,'rev-parse','HEAD']).decode().strip()==parent) and not subprocess.check_output(['git','--no-optional-locks','-C',repo,'status','--porcelain'])
fixture=base/'reversed';fixture.mkdir(exist_ok=True);(fixture/src).parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(repo/src,fixture/src);subprocess.run(['git','apply','-R','--check',patch],cwd=fixture,check=True);subprocess.run(['git','apply','-R',patch],cwd=fixture,check=True)
expected={False:[1,1,1],True:[1,2,1]};original=(repo/src).read_bytes();reversed=(fixture/src).read_bytes();carrier=base/'line_index.rs';consumer=base/'consumer';consumer.mkdir(exist_ok=True);(consumer/'src').mkdir(exist_ok=True)
(consumer/'Cargo.toml').write_text('[package]\nname="ruff_line_index_consumer"\nversion="0.0.0"\nedition="2024"\n[workspace]\n[dependencies]\nruff_source_file={path="'+str(repo/'crates/ruff_source_file')+'"}\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\nlto="off"\n')
(consumer/'src/main.rs').write_text('''use ruff_source_file::{LineIndex, OneIndexed, SourceCode};

fn main() {
    for text in ["a\\nb", "a\\r\\nb", "a\\rb"] {
        let index = LineIndex::from_source_text(text);
        let end = SourceCode::new(text, &index).line_end_exclusive(OneIndexed::from_zero_indexed(0));
        println!("{}", end.to_usize());
    }
}
''')
if not (consumer/'Cargo.lock').exists():shutil.copyfile(repo/'Cargo.lock',consumer/'Cargo.lock')
wrap=base/'record-rustc';wrap.write_text('''#!/bin/sh
printf '%s\\0' "$@" > "$LOGS/rustc.$$.argv"
exec "$@"
''');wrap.chmod(0o755)
scratch=Path('/dev/shm/ohm-line-index-v7a-release-20261027');scratch.mkdir(exist_ok=True);active=scratch/'active';active.mkdir(exist_ok=True);assert not any(active.iterdir())
registry=Path('/mnt/devbox-scratch/dev-user/ohm-nonleaf-perflint-20261026/stage-score/cargo-home/registry');assert registry.is_dir()
recs={}
for arm,driver in [('parent',sr/'armB'/lib),('candidate',root/'stage2-wire-v7a'/lib)]:
    warm=scratch/(arm+'-warm');warm.mkdir()
    def run(stage,changed,store,locked=True):
        logs=base/(arm+'-'+stage);logs.mkdir();home=store/'home';home.mkdir(exist_ok=True)
        if not (home/'registry').exists():(home/'registry').symlink_to(registry)
        ns=['taskset','-c','20-23','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(store),str(active),'--bind',str(consumer),str(consumer),'--bind',str(logs),str(logs),'--ro-bind',str(carrier),str(repo/src),'--ro-bind',str(driver),str(rt/'lib'/lib),'--ro-bind',str(n/'cargo-native'),str(rt/'bin/cargo'),'--chdir',str(consumer),'--','/home/dev-user/.cargo/bin/cargo','+ohm','build','--offline','--message-format=json'];ns+=['--locked'] if locked else []
        env=dict(os.environ,RUSTUP_HOME=str(sr/'rustup'),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(active/'home'),CARGO_TARGET_DIR=str(active/'target'),CARGO_BUILD_BUILD_DIR=str(active/'shared'),CARGO_BUILD_JOBS='4',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',GIT_OPTIONAL_LOCKS='0',RUSTC_WRAPPER=str(wrap),LOGS=str(logs))
        p=subprocess.run(ns,env=env,capture_output=True);(logs/'stdout').write_bytes(p.stdout);(logs/'stderr').write_bytes(p.stderr);arts=[];messages=[]
        for l in p.stdout.splitlines():
            j=json.loads(l)
            if j['reason']=='compiler-artifact':arts.append(j)
            if j['reason']=='compiler-message':messages.append(j)
        assert p.returncode==0,(stage,p.stderr[-1300:],[(v['message']['message'])for v in messages])
        ex=[Path(a['executable']) for a in arts if a['executable']];assert len(ex)==1
        elf=store/ex[0].relative_to(active);result=subprocess.check_output([str(elf)],text=True).splitlines();assert [int(s)for s in result]==expected[changed],(arm,stage,result)
        hashes=list(store.rglob('lib-ruff_source_file.public-api-hash'));assert len(hashes)==1
        src_art=next(a for a in arts if a['target']['name']=='ruff_source_file');sf={Path(f).suffix:sha(store/Path(f).relative_to(active)) for f in src_art['filenames']};actions=[]
        for f in logs.glob('rustc.*.argv'):
            a=[x.decode() for x in f.read_bytes().split(b'\0')if x];name=(a[a.index('--crate-name')+1]if '--crate-name'in a else None)
            if not name or name=='___':continue
            relink=any(x in ('link-only','-Zlink-only')for x in a)
            if relink:assert any(x.endswith('.rlink')for x in a)
            actions.append([name,'link-only'if relink else 'full',sha(f)])
        key=arm+'/'+stage;recs[key]={'arm':arm,'stage':stage,'source_changed':changed,'source_sha256':sha(carrier),'runtime_result':result,'compiler':sha(driver),'cargo_sha256':sha(n/'cargo-native'),'profile':{'opt-level':1,'debug':'line-tables-only','lto':'off'},'units':len(arts),'dirty':sorted(a['target']['name']for a in arts if not a['fresh']),'actions':sorted(actions),'producer_public':json.loads(hashes[0].read_bytes())['value'],'producer_rmeta':sf.get('.rmeta'),'producer_rlib':sf.get('.rlib'),'consumer_elf':sha(elf),'diagnostics':messages};(base/'receipts.json').write_text(json.dumps(recs,indent=2)+'\n');print(arm,stage,result,[(x,y)for x,y,z in sorted(actions)],recs[key]['producer_public'],flush=True)
        if stage.startswith('fresh'):assert not recs[key]['dirty'] and not actions
    carrier.write_bytes(original);run('original',False,warm,locked=arm!='parent');run('fresh-original',False,warm)
    carrier.write_bytes(reversed);run('warm-edit',True,warm);run('fresh-edit',True,warm)
    carrier.write_bytes(original);run('warm-restore',False,warm);run('fresh-restored',False,warm)
    for stage,changed in [('clean-edit',True),('clean-restored',False)]:
        st=scratch/(arm+'-'+stage);st.mkdir();carrier.write_bytes(reversed if changed else original);run(stage,changed,st)
assert not subprocess.check_output(['git','--no-optional-locks','-C',repo,'status','--porcelain']);print('finished',len(recs),'commands')
