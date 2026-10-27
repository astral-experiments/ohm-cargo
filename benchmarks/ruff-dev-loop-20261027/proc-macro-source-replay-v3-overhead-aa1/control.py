"""An identical-release calibration for a balanced four-launch design. No product comparisons."""
from pathlib import Path
import copy, hashlib, random, statistics, sys

script=Path(__file__).resolve().parent/"overhead-v3-r2/parser-overhead-v3.py"
assert hashlib.sha256(script.read_bytes()).hexdigest()==sys.argv[1]
sys.argv=[str(script),"qualify"]
scope={"__name__":"__main__","__file__":str(script)}
exec(compile(script.read_text().split('with (P/"native-measure.lock")')[0],str(script),"exec"),scope)
globals().update({k:v for k,v in scope.items() if not k.startswith("__")})
from itertools import groupby
initial=O;O=J/"scoped-parser-overhead-calibration-aa1"
seed="h3-identical-release-empty-iteration-1";rng=random.Random(int(hashlib.sha256(seed.encode()).hexdigest(),16))
order=[["parent","candidate","candidate","parent"]]*4+[["candidate","parent","parent","candidate"]]*4;rng.shuffle(order)
assert len(order)==8
def read(path):
    try:return Path(path).read_text().strip()
    except OSError:return None
def host():
    return {name:read(path) for name,path in {"cpu_pressure":"/proc/pressure/cpu","io_pressure":"/proc/pressure/io","memory_pressure":"/proc/pressure/memory","scheduler":"/proc/stat","cgroup_cpu_stat":"/sys/fs/cgroup/cpu.stat","scaling_governor":"/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor","scaling_frequency":"/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"}.items()}
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);gate_free(J,2*2**30);O.mkdir(mode=0o700);skeleton_base=skeleton(O)
    q=O/"qualification";q.mkdir()
    for arm in ("parent","candidate"):
        d=q/arm;d.mkdir();(d/"training").symlink_to(initial/"qualification/parent/training",target_is_directory=True)
    src=subjects["parent"];cp=O/"same-parent-copy.so";shutil.copyfile(src,cp);image_sha=sha(src);assert image_sha==sha(cp) and not src.samefile(cp)
    subjects={"parent":src,"candidate":cp};plan=copy.deepcopy(plan);plan['arms']['candidate']=plan['arms']['parent']
    inner=inner.replace('"affinity":sorted','"faults_minor":u.ru_minflt,"faults_major":u.ru_majflt,"voluntary_switches":u.ru_nvcsw,"involuntary_switches":u.ru_nivcsw,"input_blocks":u.ru_inblock,"output_blocks":u.ru_oublock,"rss_kib":u.ru_maxrss,"affinity":sorted')
    (O/"inner.py").write_text(inner)
    for k in ("O","skeleton_base","subjects","plan"):
        scope[k]=globals()[k]
    gold=load(initial/"qualification/complete.json")['oracles']['parent']
    dump(O/"plan.json",{"seed":seed,"blocks":order,"prime":"one untimed true retained parent, then four native empty builds","sha256":image_sha,"physical_files":[str(src),str(cp)],"identical_inode":src.samefile(cp),"plan_sha256":sha(script.parent/"parser-overhead-v3-plan.json"),"exclusions":0,"product_comparisons":0})
    rows=[]
    for n,arms in enumerate(order):
        d=O/f"block-{n:02d}";d.mkdir()
        with tempfile.TemporaryDirectory(dir=O) as t:
            w=Path(t)/"run";z=run(w,arms[0],"retained");assert roots(z)==roots(gold["retained"]);clean_to_ledger(d/"unclocked-prime",w)
        for pos,arm in enumerate(arms):
            with tempfile.TemporaryDirectory(dir=O) as t:
                w=Path(t)/"run";before=host();z=run(w,arm,"empty",clock=True);after=host();assert roots(z)==roots(gold["empty"])
                r=d/f"{pos}-{arm}";clean_to_ledger(r,w);dump(r/"system-snapshots.json",{"before":before,"after":after})
            rows.append({"block":n,"position":pos,"label":arm,"actual_sha":image_sha,"child":z['child'],"rmeta_sha256":z['rmeta_sha256']});dump(O/"observations.json",rows)
    stats=[];posns={i:[] for i in range(4)}
    import math
    for k,g in groupby(rows,key=lambda x:x['block']):
        rr=list(g);mean={a:statistics.mean(math.log(z['child']['wall_ns']) for z in rr if z['label']==a) for a in ('parent','candidate')}
        stats.append(100*math.expm1(mean['candidate']-mean['parent']))
        for z in rr:posns[z['position']].append(z['child']['wall_ns'])
    out={"blocks":8,"true_empty_compiles":32,"signed_geometric_batch_pct":stats,"median_pct":statistics.median(stats),"abs_below_5pct":sum(abs(x)<5 for x in stats),"position_median_ms":{k:statistics.median(v)/1e6 for k,v in posns.items()},"replay_matches":32,"sha256_observations":sha(O/"observations.json"),"fresh_product_scores":0}
    assert image_sha==sha(src)==sha(cp);dump(O/"complete.json",out);print(out,flush=True)
