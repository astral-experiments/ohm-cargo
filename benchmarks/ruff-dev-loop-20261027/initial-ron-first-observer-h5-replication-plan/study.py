"""Run the second host's independently registered cold command pairs."""
from pathlib import Path
import csv,fcntl,os,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from validation import audit_receipts,write,sha,here,root,p,plan,workload,verify_hardware,same_subject_oracles,retire_private

def verify_inputs():
    for path,digest in workload.load(here/"input-hashes.json").items():assert sha(root/"inputs"/path)==digest
    assert sha(workload.FROZEN/"bin/rustc")==plan["release"]["rustc_frontend"]
    assert workload.git("rev-parse","HEAD").decode()==plan["ruff"] and workload.git("rev-parse","HEAD^{tree}").decode()==plan["tree"]
    assert not workload.git("status","--porcelain")

def score(grant):
    assert sha(here/"SHA256SUMS")==grant.read_text().strip()
    subprocess.run(["sha256sum","-c","--quiet","SHA256SUMS"],cwd=here,check=True);verify_inputs()
    qual={a:workload.load(root/"results"/("qualify-"+a)/"complete.json") for a in "DC"}
    assert all((root/"results"/("qualify-"+a)/"proof-validation.json").is_file() for a in qual)
    assert all(x["ordinary_native_oracles"]==qual["C"]["ordinary_native_oracles"] for x in qual.values())
    assert len({x["phases"]["cold"]["roster"] for x in qual.values()})==1
    out=root/"native-scores";out.mkdir(exist_ok=False,mode=0o700)
    with (p/"native-measure.lock").open("a") as lock,(out/"times.csv").open("x",newline="") as table:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);hw=verify_hardware();write(out/"host.json",hw)
        csvout=csv.DictWriter(table,fieldnames=["block","slot","arm","cold_ns","first_ns","settled_ns"]);csvout.writeheader();table.flush()
        for i,order in enumerate(plan["schedule"]["orders"],1):
            for j,arm in enumerate(order,1):
                name=f"score-{i:02d}-{j}-{arm}";now=verify_hardware();assert now["boot_id"]==hw["boot_id"]
                workload.setup(name,arm,"native");st,d=workload.dirs(name);v=workload.load(d/"complete.json")
                assert v["ordinary_native_oracles"]==qual[arm]["ordinary_native_oracles"]
                assert all(v["phases"]["cold"][k]==qual[arm]["phases"]["cold"][k] for k in ("messages","roster"))
                parity=same_subject_oracles(d,root/"results"/("qualify-"+arm));write(d/"same-subject-reference.json",parity)
                audit_receipts(st,d,arm);write(d/"host.json",now)
                csvout.writerow({"block":i,"slot":j,"arm":arm,**{k+"_ns":v["phases"][k]["elapsed_ns"] for k in ("cold","first","settled")}})
                table.flush();os.fsync(table.fileno());retire_private(st,d);print("verified block",i,"slot",j,"arm",arm,flush=True)
        verify_inputs()
    write(out/"complete.json",{"plan":sha(here/"plan.json"),"runner":sha(here/"SHA256SUMS"),"slots":24,"commands":72,"observations":sha(out/"times.csv")})
if __name__=="__main__":
    if sys.argv[1]=="qualify":
        verify_inputs()
        assert not (root/"results").exists() and not (root/"states").exists()
        with (p/"native-measure.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);workload.floors(16<<30)
            for arm in "DC":
                workload.setup("qualify-"+arm,arm,"qualify");st,d=workload.dirs("qualify-"+arm);audit_receipts(st,d,arm)
    elif sys.argv[1]=="score" and len(sys.argv)==3:score(Path(sys.argv[2]))
    else:raise SystemExit("Pass qualify or score with the bound grant path")
