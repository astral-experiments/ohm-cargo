"""Scoped private Ruff inputs plus fixed host, state and protocol checks for the mixed comparison."""
from pathlib import Path
import hashlib, os, shutil, subprocess, sys
from common import P, PIN, RUFF, TARGET, SHARED, CARGO_HOME, FROZEN, SONAME, dump, git, load, need, sha
H = Path(__file__).resolve().parent
PLAN_SHA = '1679c7c5549858ee287943e29ae7c6963079a0e75926df6ac59db9ce3551e36d'
PLAN = load(H / 'plan.json')
BASE = Path.home()/'.cache/ohm-233-position-qualified-20261027'
WASM = ('ruff_wasm', 'ty_wasm')
RSL = Path('crates/ruff_python_parser/src/parser/expression.rs')
DELETED = (Path('crates/ruff_python_parser/resources/inline/err/mixed_tstring_and_bytes_literals.py'),
           Path('crates/ruff_python_parser/tests/snapshots/invalid_syntax@mixed_tstring_and_bytes_literals.py.snap'))
FILES = (RSL, *DELETED)
EDITED = 'Bytes literal cannot be mixed with non-bytes literals'
ORIGINAL = 'Cannot mix t-string literals with string or bytes literals'
BUDGET = 25 * 2**30

def gate_free(path, extra=0):
    amount = shutil.disk_usage(path).free
    need(amount > BUDGET + extra, ('25 GiB ext4 reserve', str(path), amount, extra))
    return amount

def verify_plan():
    need(sha(H/'plan.json') == PLAN_SHA and sha(H/'analyze.py') == PLAN['analyzer_sha256'], 'plan/analyzer')
    need(sha(H/'parser.patch') == PLAN['reversed_patch_sha256'] and PLAN['ruff'] == PIN, 'registered edit')
    need(not sys.flags.optimize and sorted(os.sched_getaffinity(0)) == list(range(24)), 'lane, assertions')
    banned = set('RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER RUSTC_BOOTSTRAP RUSTC_LOG RUSTUP_TOOLCHAIN RUSTFLAGS CARGO_ENCODED_RUSTFLAGS CARGO_INCREMENTAL CARGO_BUILD_RUSTFLAGS CARGO_BUILD_RUSTC CARGO_BUILD_RUSTC_WRAPPER CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER CARGO_BUILD_TARGET CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER MAKEFLAGS MFLAGS CARGO_MAKEFLAGS'.split())
    need(not [k for k in os.environ if k in banned or k.startswith(('CARGO_PROFILE_', 'WILD_'))], 'environment override')

def source_clean():
    need(git('rev-parse','HEAD')==PIN and not git('status','--porcelain'), 'underlying Ruff source')
    index=Path(git('rev-parse','--path-format=absolute','--git-path','index'))
    return sha(index)

def inputs(out):
    base=out/'fixture'; orig=base/'original'; changed=base/'edited'
    orig.mkdir(parents=True)
    need(git('diff-tree','--no-commit-id','-r','--name-only',PLAN['edit_commit']).splitlines()==sorted(map(str,FILES)), 'complete original historical commit')
    for rel in FILES:
        p=orig/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUFF/rel,p)
    shutil.copytree(orig,changed)
    subprocess.run(['git','apply','--no-index','--reverse','--check',str(H/'parser.patch')],cwd=changed,check=True)
    subprocess.run(['git','apply','--no-index','--reverse','--whitespace=nowarn',str(H/'parser.patch')],cwd=changed,check=True)
    need(all(not (changed/p).exists() for p in DELETED) and sha(changed/RSL)!=sha(orig/RSL),'complete reversed patch')
    manifest={label:{str(p):sha(root/p) if (root/p).is_file() else None for p in FILES} for label,root in [('original',orig),('edited',changed)]}
    dump(base/'manifest.json',manifest)
    return base

def seed(state, fixture, source_home):
    need(not state.exists(), ('state already present',state));state.mkdir(parents=True)
    for n in ('target','shared','registry-home','inputs'):
        (state/n).mkdir(mode=0o700)
    shutil.copytree(P/'rustup',state/'rustup',symlinks=True)
    need((state/'rustup/toolchains/ohm').is_symlink() and (state/'rustup/toolchains/ohm').resolve()==FROZEN,'private rustup selector')
    for rel in ('config','config.toml','registry','git'):
        src=source_home/rel
        if src.exists():
            subprocess.run(['cp','-a','--reflink=auto','--',str(src.resolve()),str(state/'registry-home'/rel)],check=True)
    need((state/'registry-home/registry').is_dir(),'registry source inputs')
    for rel in DELETED:
        dest=state/'inputs'/rel.parent;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(RUFF/rel.parent,dest)
    (state/'inputs'/RSL).parent.mkdir(parents=True,exist_ok=True)
    set_source(state,fixture,False)
    need(not any((state/'target').iterdir()) and not any((state/'shared').iterdir()), 'empty target / shared')
    return state

def set_source(state,fixture,edited):
    label='edited' if edited else 'original'; tag=state/'source-state'
    if tag.exists() and tag.read_text()==label:return
    for rel in FILES:
        dest=state/'inputs'/rel; reference=fixture/label/rel
        if reference.is_file():
            dest.write_bytes(reference.read_bytes());os.chmod(dest,reference.stat().st_mode&0o777)
        elif dest.exists():
            dest.unlink()
    tag.write_text(label)

def source_binds(state):
    out=[]
    for rel in [RSL,*[p.parent for p in DELETED]]:out+=['--ro-bind',str(state/'inputs'/rel),str(RUFF/rel)]
    return out

def verify_view(edited, manifest):
    need(git('rev-parse','HEAD')==PIN,'mount HEAD')
    for p,v in manifest['edited' if edited else 'original'].items():
        target=RUFF/p;need((sha(target) if target.is_file() else None)==v,('mounted historical bytes',target))
    changes=git('diff','--name-status','--no-ext-diff','--',*map(str,FILES)).splitlines()
    expect=sorted(['M\t'+str(RSL),*['D\t'+str(p) for p in DELETED]]) if edited else []
    need(sorted(changes)==expect,('worktree view',changes,expect))

def recipes(known=None):
    out={}
    paths=map(Path,known) if known is not None else (p for base in (TARGET,SHARED) for p in base.rglob('*.rlink') if p.stem.split('-')[0] in WASM)
    for p in paths:
        need(p.is_relative_to(TARGET) or p.is_relative_to(SHARED),('unrecognized recipe',p))
        if p.is_file():
            st=p.stat();out[str(p)]=[sha(p),st.st_mtime_ns,st.st_size]
    return out

