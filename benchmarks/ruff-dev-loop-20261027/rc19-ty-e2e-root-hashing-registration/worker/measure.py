"""Finish native preflight before running the two separately registered endpoints."""
import fcntl
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from enter import launch
from suite import do

def quiet():
    def cpu():
        result={}
        for line in Path("/proc/stat").read_text().splitlines():
            key,*vals=line.split()
            if key in {"cpu"+str(x) for x in SCHEMA["cpus"]}:
                nums=list(map(int,vals[:8]));result[key]=(sum(nums),nums[3])
        assert len(result)==4
        return result
    until=time.monotonic()+180
    while True:
        before=cpu();time.sleep(1);after=cpu()
        f={k:(v[1]-before[k][1])/(v[0]-before[k][0]) for k,v in after.items()}
        if min(f.values())>=.85:return f
        assert time.monotonic()<until,"four quiet cores unavailable"

def compare_profile(d,ref):
    actual=get(d/"native-descriptor.json");gold=get(ref/"native-descriptor.json")
    assert actual["externs"]==gold["externs"] and actual["full_argv"]==gold["full_argv"]
    assert actual["argv_roles"]==[{k:v for k,v in a.items() if k!="temporary_contents"} for a in gold["argv_roles"]]
    # Live acquisition in the separate control retains the temporary bytes. The profiler's
    # completed exec trace, itself, only binds the genuine path roles and ordered explicit inputs.
    r=get(d/"root-current-recipe.json");g=get(ref/"root-current-recipe.json")
    assert r["objects"]==g["objects"] and r["exact_except_verified_names"]==g["exact_except_verified_names"]
    sig=get(d/"result.json")["e2e"];assert sig==get(ref/"result.json")["e2e"]

def extra(arm):
    core=get(K/"binding/native-core.json")
    lane="warm-"+arm
    do(lane,arm,[("io-edit","edited","io","dirty"),("io-return","original","native","dirty"),
                 ("profile-pre-settled","original","native","settled"),("profile-pre-edit","edited","profile","dirty"),
                 ("profile-return","original","native","dirty"),("profile-ready","original","native","settled")])
    q=REPORTS/lane
    compare_profile(q/"profile-pre-edit",q/"edit")
    assert get(q/"io-edit/result.json")["e2e"]==core["elf"]["edited"] and get(q/"io-edit/result.json")["dependencies"]==get(K/"binding/donor.json")["dependencies"]
    assert (q/"io-edit/cargo-real-input-io.json").is_file()

def admit():
    checks=get(K/"binding/small-source.json")
    assert checks["subjects"]=={k:v["sha256"]for k,v in get(K/"binding/physical.json")["subjects"].items()}
    assert rawsha(checks["manifest_file"])==checks["manifest_sha256"] and checks["accepted"]
    core=get(K/"binding/native-core.json");review={}
    for arm in ["parent","child"]:
        base=REPORTS/("warm-"+arm)
        compare_profile(base/"profile-pre-edit",base/"edit")
        assert get(base/"profile-ready/result.json")["fresh"]==300
        io=get(base/"io-edit/cargo-real-input-io.json")
        assert len(io["inputs"])==140 and len(io["opened"])==140 and io["executable_stat_calls"]>0
        reads=sum(io["read_bytes"].values())
        assert reads==(sum(io["inputs"].values()) if arm=="parent" else 0)
        review[arm]={"io":rawsha(base/"io-edit/cargo-real-input-io.json"),"real_root_rustc":rawsha(base/"edit/native.json"),"profile":rawsha(base/"profile-pre-edit/instructions.json"),"native_empty":rawsha(REPORTS/("cold-"+arm)/"edited-cold/result.json"),"input_bytes":sum(io["inputs"].values())}
    put(K/"binding/native-admission.json",{"elf":core["elf"],"plan":rawsha(K/"registration/SHA256SUMS"),"four_controls":review,
        "cold":rawsha(K/"binding/cold-comparison.json"),"external_same_products":checks["manifest_sha256"],"core":rawsha(K/"binding/native-core.json")})

def run():
    gate=get(K/"binding/score-grant.json")
    assert gate["go"] and gate["plan"]==rawsha(K/"registration/SHA256SUMS") and gate["preflight"]==rawsha(K/"binding/native-admission.json")
    roster=get(K/"registration/roster.json");rows=[];seen=set()
    assert not (K/"binding/clock-start.json").exists()
    put(K/"binding/clock-start.json",{"approved":rawsha(K/"binding/score-grant.json"),"roster":rawsha(K/"registration/roster.json"),"start":time.time_ns()})
    for endpoint in ("primary","wall"):
        for i,order in enumerate(roster[endpoint],1):
            assert order in ("RF","FR")
            for token in order:
                arm={"R":"parent","F":"child"}[token];lane="warm-"+arm
                label=endpoint+"-"+str(i).zfill(2)
                prefix=REPORTS/lane
                # The preceding gate leaves both lanes at original. Subsequent visits restore
                # original from the previous edit in that same lane.
                if arm in seen:
                    do(lane,arm,[(label+"-reset","original","ordinary","dirty")])
                do(lane,arm,[(label+"-settled","original","ordinary","settled")])
                put(K/"logs"/(label+"-"+arm+"-idle.json"),quiet())
                how="profile" if endpoint=="primary" else "ordinary"
                do(lane,arm,[(label+"-edit","edited",how,"dirty")])
                d=prefix/(label+"-edit");b=get(d/"result.json")
                p=K/"binding/native-admission.json";assert b["e2e"]==get(p)["elf"]["edited"] and b["fresh"]==299
                if endpoint=="primary":
                    compare_profile(d,prefix/"edit")
                side=get(d/"root-current-recipe.json");ref=get(prefix/"edit/root-current-recipe.json")
                assert side["objects"]==ref["objects"] and side["exact_except_verified_names"]==ref["exact_except_verified_names"]
                rows.append({"endpoint":endpoint,"arm":arm,"pair":i,"result":rawsha(d/"result.json"),"measure":rawsha(d/("instructions.json" if endpoint=="primary" else "clock.json"))})
                seen.add(arm)
    assert len(rows)==40
    for arm in ["parent","child"]:
        lane="warm-"+arm
        do(lane,arm,[("post-restore","original","ordinary","dirty"),("post-settled","original","native","settled"),("post-edit","edited","native","dirty")])
        a=REPORTS/lane;assert get(a/"post-edit/native-descriptor.json")==get(a/"edit/native-descriptor.json")
    put(K/"binding/clock-terminal.json",{"pairs":{"primary":8,"wall":12},"rows":rows})

def analyze():
    term=get(K/"binding/clock-terminal.json");roster=get(K/"registration/roster.json")
    assert term["pairs"]=={"primary":8,"wall":12}
    reference=prior.module("registered_analysis",K/"registration/reference-analysis.py");reference.self_checks()
    report={}
    for typ, n in term["pairs"].items():
        vals=[{}for _ in range(n)]
        for row in term["rows"]:
            if row["endpoint"]!=typ:continue
            arm=row["arm"]; i=row["pair"];d=REPORTS/("warm-"+arm)/(typ+"-"+str(i).zfill(2)+"-edit")
            metric=d/("instructions.json" if typ=="primary" else "clock.json")
            assert rawsha(metric)==row["measure"] and rawsha(d/"result.json")==row["result"]
            x=get(metric);v=x["ir"] if typ=="primary" else x["elapsed_ns"]
            if typ=="wall":assert x["end_ns"]-x["start_ns"]==v and x["status"]==0
            vals[i-1][{"parent":"R","child":"F"}[arm]]=v
        stat=reference.summarize(vals,roster[typ],roster["bootstrap_seed"],30000)
        assert stat["permutation_count"]=={8:70,12:924}[n]
        summary={k:v for k,v in stat.items() if k not in ("cached_median_seconds","full_median_seconds","paired_delta_seconds")}
        summary.update({"rows":vals,"order":roster[typ],"parent_median":statistics.median(v["R"] for v in vals),"child_median":statistics.median(v["F"] for v in vals),
                        "median_paired_difference":statistics.median(v["F"]-v["R"] for v in vals),"unit":"root Ir" if typ=="primary" else "ns",
                        "qualified":stat["upper95"]<0 and stat["two_sided_balanced_p"]<.05})
        report[typ]=summary
    put(K/"binding/analysis.json",report)

if __name__=="__main__":
    action=sys.argv[1]
    if action.startswith("extra-"):extra(action.split("-")[1])
    else:{"admit":admit,"run":run,"analyze":analyze}[action]()
