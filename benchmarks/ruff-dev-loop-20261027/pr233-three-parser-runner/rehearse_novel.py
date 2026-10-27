"""Rehearse private source swaps only. This command never launches Cargo, rustc, or a linker."""
import argparse, tempfile, shutil
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common, novel_state as k
from common import dump, load, need, sha
p=argparse.ArgumentParser();p.add_argument('real_worktree',type=Path);p.add_argument('receipt',type=Path);a=p.parse_args()
k.RUFF=common.RUFF=a.real_worktree.resolve();k.verify_plan();need(common.git('rev-parse','HEAD')==common.PIN,'Ruff pin')
with tempfile.TemporaryDirectory() as temp:
    out=Path(temp);fixture=k.make_fixtures(out);man=load(fixture/'manifest.json');state=out/'private';state.mkdir();(state/'inputs').mkdir()
    for rel in k.DELETION_DIRS:
        q=state/'inputs'/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(k.RUFF/rel,q)
    visits=[]
    for view in ['original',*sum(([n,'original'] for n in k.PLAN['schedule']),[])]:
        before={s:(state/'inputs'/s).stat().st_mtime_ns for s in k.PATHS if (state/'inputs'/s).is_file()}
        k.set_source(state,fixture,view);k.verify_input(view,state/'inputs',man)
        untouched=[] if not visits else [s for s in before if man[view][s]==man[visits[-1]['label']][s]]
        need(all(before[s]==(state/'inputs'/s).stat().st_mtime_ns for s in untouched),'unrelated mounted source touched')
        visits.append({'label':view,'touched':sorted(s for s in k.PATHS if man[view][s]!=man['original'][s]),'unmodified_mtimes_verified':untouched})
    dump(a.receipt,{'plan_sha256':k.PLAN_SHA,'manifest':man,'visits':visits,'original_pin':common.PIN,'native_compiler_calls':0})
