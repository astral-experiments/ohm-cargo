"""Independently authenticate every process and recompute all four preregistered gates."""
from pathlib import Path
import hashlib,itertools,json,math,statistics,sys
p=Path(__file__).resolve().parent
def h(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def j(path):return json.loads(path.read_bytes())
m={}
for line in (p/"SHA256SUMS").read_text().splitlines():
    cs,name=line.split("  ",1);assert name not in m and not name.startswith(("./","/","../"))
    m[name]=cs;assert h(p/name)==cs
assert set(m)=={str(f.relative_to(p)) for f in p.rglob("*") if f.is_file() and f.name!="SHA256SUMS"}
source=j(p/"screen-plan.json");grant=j(p/"grant.json");host=j(p/"host-registration.json");plan=j(p/"acquisition.json")
assert grant["release"]=="score-local-12" and grant["host_admission_commit"]==plan["admission_commit"]=="51c1278c3c78411fad79333fca95d29e0028fa0a"
assert grant["source_commit"]==plan["source_commit"]=="32c4f9da05956359fbd8d660c712c846fd8ff01f" and grant["host"]==host["host_sha256"] and grant["native"]==host["native_sha256"]
assert h(p/"screen-plan.json")=="3b1493912337bf911258f7341fd5668a14f6bd157fb517cab14d3bd1c15707d9" and h(p/"worker.py")==host["worker_sha256"]
assert h(p/"analyze.py")==source["analysis_sha256"] and host["performance_observations"]==0
rows=j(p/"rows.json");res=j(p/"result.json");assert len(rows)==24
ordered=[]; ratios=[];saved=[];favorable=[];total_before=[];total_after=[];pids=[]
for i,arms in enumerate(source["orders"]):
    group=rows[2*i:2*i+2];assert [r["arm"] for r in group]==arms
    values=[]
    for slot,(label,row) in enumerate(zip(arms,group)):
        assert (row["pair"],row["slot"])==(i,slot)
        d=p/"records"/f"{i:02d}-{slot}-{label}";args=j(d/"invocation.json");status=j(d/"status.json");pid=status["pid"];pids.append(pid)
        assert status["rc"]==0 and args["affinity"]==[14] and args["environment"]==j(p/"host.json")["environment"]
        assert args["argv"]==[plan["drrun"],"-quiet","-no_follow_children","-c",plan["client"],plan["score_input_dir"]+"/"+d.name+"/pid.count","--",plan["fixture"],label,plan["corpus"],"4"]
        assert (d/"stderr").read_bytes()==b"" and (d/"stdout").read_bytes()==(source["expected_stdout"]+"\n").encode()
        parts=[r.split() for r in (d/"pid.count").read_text().splitlines()]
        assert [v[0] for v in parts]==["B","T","F","P"] and all(int(v[1])==pid and len(v)==4 for v in parts)
        assert parts[0][2:]==parts[3][2:]==["0","0"] and int(parts[1][2])==int(parts[2][2])==pid and parts[1][3]=="0"
        ir=int(parts[2][3]);assert ir==row["ir"]>0 and h(d/"pid.count")==row["count_sha256"] and h(d/"stdout")==row["stdout_sha256"]
        values.append(ir)
    by=dict(zip(arms,values));a,b=by["before"],by["after"];total_before.append(a);total_after.append(b);ratios.append(100*(a-b)/a);saved.append((a-b)/4);favorable.append(a>b);ordered.append(math.log(values[0])-math.log(values[1]))
assert len(set(pids))==24
for arm in ("before","after"):
    d=p/"records"/f"post-native-{arm}";inv=j(d/"invocation.json")
    assert j(d/"status.json")["rc"]==0 and (d/"stdout").read_bytes()==(source["expected_stdout"]+"\n").encode() and (d/"stderr").stat().st_size==0
    assert inv["argv"]==[plan["fixture"],arm,plan["corpus"],"4"] and inv["affinity"]==[14]
obs=sum(math.log(a)-math.log(b) for a,b in zip(total_before,total_after))
assign=list(itertools.combinations(range(12),6))
pval=sum(sum(x if idx in group else -x for idx,x in enumerate(ordered))>=obs-1e-12 for group in assign)/len(assign)
median=statistics.median(ratios);interval=sorted(ratios)[2],sorted(ratios)[9];count=sum(favorable);ir_per_pass=statistics.median(saved)
assert (count,median,list(interval),ir_per_pass,pval)==(res["favorable"],res["paired_percent"],res["median_96_14_percent_interval"],res["per_sweep_instructions_saved"],res["paired_randomization_one_sided"])
assert res["threshold_pass"]==(median>=3 and ir_per_pass>=4000000 and count>=10 and pval<=.01)
print(json.dumps(dict(pairs=12,complete_process_receipts=24,arm_medians_four_pass={"before":statistics.median(total_before),"after":statistics.median(total_after)},paired_reduction_percent=median,median_interval_96_14=interval,instructions_saved_per_sweep=ir_per_pass,favorable=count,p=pval,gate=res["threshold_pass"]),indent=2))
