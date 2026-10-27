"""Build each complete historical reversal independently, at the pinned real Ruff worktree path."""
from pathlib import Path
import os, shutil, subprocess
from common import RUFF, PIN, P, FROZEN, CARGO_HOME, git, dump, load, need, sha
from state import source_clean
H = Path(__file__).resolve().parent
PLAN_SHA = 'a55a3d97d1f4880a3c516b930b77ca49e337927a1404a4e0dafa23222244d7e4'
PLAN = load(H/'novel-plan.json')
PLAN_URL = 'https://github.com/astral-sh/ohm-cargo/tree/d8d5011852778f8babeb4e5c3cb0613c6793ca6c/benchmarks/ruff-dev-loop-20261027/pr233-three-parser-edits-plan'
BASE = Path.home()/'.cache/ohm-233-position-qualified-20261027'
OUT = BASE/'first-occurrence-classic-pr233-h5'
EDITS = PLAN['edits']
PATHS = sorted({p for e in EDITS.values() for p in e['historical_changed_paths']})
MODIFIED = sorted({p for e in EDITS.values() for p, action in e['historical_changed_paths'].items() if action=='M'})
DELETION_DIRS = sorted({str(Path(p).parent) for e in EDITS.values() for p,action in e['historical_changed_paths'].items() if action=='A'})
def verify_plan():
    need(sha(H/'novel-plan.json')==PLAN_SHA and PLAN['ruff']==PIN and list(EDITS)==PLAN['schedule'], 'registered plan/hash/order')
    for label,e in EDITS.items():
        need(sha(H/'fixtures'/(label+'.patch'))==e['patch_sha256'],('patch hash',label))
def verify_input(label, source, manifests):
    for p,digest in manifests[label].items():
        dest=source/p
        need((sha(dest) if dest.is_file() else None)==digest,('wrong source view',label,p))
def make_fixtures(out):
    fixture=out/'fixture';original=fixture/'original';original.mkdir(parents=True)
    for rel in PATHS:
        p=original/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(RUFF/rel,p)
        oid=git('rev-parse',PIN+':'+rel);actual=git('hash-object',str(p));need(actual==oid,('dirty original',rel,oid,actual))
    # The pinned H2 worktree is shallow. Use an independent bare object database to
    # verify each original parent/child diff and its exact full set of touched paths.
    history=fixture/'historical.git'
    subprocess.run(['git','init','--quiet','--bare',str(history)],check=True)
    with (H/'historical-trees.pack').open('rb') as pack:
        subprocess.run(['git','--git-dir',str(history),'index-pack','--stdin'],stdin=pack,stdout=subprocess.DEVNULL,check=True)
    def historical(*args):
        return subprocess.check_output(['git','--no-optional-locks','--git-dir',str(history),*args],text=True).strip()
    manifest={'original':{p:sha(original/p) for p in PATHS}}
    for label,e in EDITS.items():
        actual={p:k for k,p in (line.split('\t',1) for line in historical('diff-tree','--no-commit-id','-r','--no-renames','--name-status',e['commit']).splitlines())}
        need(actual==e['historical_changed_paths'] and historical('rev-parse',e['commit']+'^')==e['parent'],('historical paths/parent',label,actual))
        changed=fixture/label;shutil.copytree(original,changed)
        patch=H/'fixtures'/(label+'.patch')
        for args in (['--check'],['--whitespace=nowarn']):
            subprocess.run(['git','apply','--no-index','--reverse',*args,str(patch)],cwd=changed,check=True)
        after={p:sha(changed/p) if (changed/p).is_file() else None for p in PATHS}
        need({p for p in PATHS if after[p]!=manifest['original'][p]}==set(actual),('omitted files',label,actual,after))
        need(all((after[p] is None)==(k=='A') for p,k in actual.items()),('historical deletion',label))
        manifest[label]=after
    dump(fixture/'manifest.json',manifest)
    return fixture
def set_source(st,fixture,label):
    need(label=='original' or label in EDITS,label)
    tag=st/'source-state'
    if tag.exists() and tag.read_text()==label:return
    if label!='original':need(tag.is_file() and tag.read_text()=='original','edit must start at original')
    manifest=load(fixture/'manifest.json')[label]
    for rel,ref in manifest.items():
        dest=st/'inputs'/rel;source=fixture/label/rel
        if ref is None:
            if dest.is_file():dest.unlink()
            continue
        if not dest.is_file() or sha(dest)!=ref:
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes());os.chmod(dest,source.stat().st_mode&0o777)
    tag.write_text(label)
def seed(st,fixture):
    need(not st.exists(),('arm already exists',st));st.mkdir(parents=True)
    for part in ('target','shared','registry-home','inputs'):(st/part).mkdir(mode=0o700)
    shutil.copytree(P/'rustup',st/'rustup',symlinks=True)
    need((st/'rustup/toolchains/ohm').is_symlink() and (st/'rustup/toolchains/ohm').resolve()==FROZEN,'independent selector')
    for rel in ('config','config.toml','registry','git'):
        src=CARGO_HOME/rel
        if src.exists():subprocess.run(['cp','-a','--reflink=auto','--',str(src.resolve()),str(st/'registry-home'/rel)],check=True)
    need((st/'registry-home/registry').is_dir() and not (st/'registry-home/registry').samefile((CARGO_HOME/'registry').resolve()),'distinct offline registry')
    need(not (st/'registry-home/.ohm-registry-json-v1').exists(),'no warm registry proof')
    for rel in DELETION_DIRS:
        dest=st/'inputs'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(RUFF/rel,dest)
    set_source(st,fixture,'original')
    need(not any((st/'target').iterdir()) and not any((st/'shared').iterdir()),'warm target or build')
def source_binds(st):
    args=[]
    for rel in MODIFIED+DELETION_DIRS:args.extend(['--ro-bind',str(st/'inputs'/rel),str(RUFF/rel)])
    return args
def verify_view(label,fixture):
    need(git('rev-parse','HEAD')==PIN,'worktree HEAD')
    verify_input(label,RUFF,load(fixture/'manifest.json'))
    expected=[] if label=='original' else sorted(('D' if a=='A' else a)+'\t'+p for p,a in EDITS[label]['historical_changed_paths'].items())
    # Limit to mounted paths. The host worktree index and overall status are separately checked.
    need(sorted(git('diff','--name-status','--no-ext-diff','--',*PATHS).splitlines())==expected,('unmatched mounted edit',label,expected))
