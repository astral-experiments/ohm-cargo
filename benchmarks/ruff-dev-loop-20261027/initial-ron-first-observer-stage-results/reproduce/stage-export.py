"""Export physical, native and proof commitments from the unmodified scoped and whole H4 stores."""
from pathlib import Path
import hashlib,json
p=Path("/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027");q=p/"first-proof-stage1";out=q/"controls-v2/stage-selected";out.mkdir()
def read(f):return json.loads(f.read_bytes())
def digest(f):
    with f.open("rb") as s:return hashlib.file_digest(s,"sha256").hexdigest()
def write(n,data):(out/(n+".json")).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def rel(n):
    s=str(n)
    return s.replace(str(p)+"/","$RUN/").replace(str(Path.home())+"/","$HOME/")
cases={}
for arm in ("PP","PA","AP","AA"):
    cases[arm]={t:read(q/"matrix-v2"/(t+"-"+arm)/"matrix.json") for t in ("tiny","held")}
write("four-arms",cases)
for n in ("receipts","PP-input-blake3","PA-input-blake3","AP-input-blake3","AA-input-blake3"):
    write(n,read(q/"proof-check-v2"/(n+".json")))
f=p/"ron-binary-observer-v1"
write("binary-inputs",{k:read(f/k/"summary.json") for k in ("stage-PP","stage-AA","stage-v2-PP","release-default-v2")})
def hot(f):
    rows=read(f/"summary.json")
    for name,row in rows.items():
        d=f/name;msgs=[v["message"]["message"] for s in (d/"stdout").read_bytes().splitlines() if (v:=json.loads(s)).get("reason")=="compiler-message"]
        row["unknown_observer_option"]=any("unknown unstable option" in s and "ohm-observer-dep-info" in s for s in msgs)
        row["diagnostics"]=msgs;row["raw_stdout_sha256"]=digest(d/"stdout");row["raw_stderr_sha256"]=digest(d/"stderr")
    return rows
write("rejected-persistent-probe",hot(q/"controls-v2/hot-swap-v2"))
whole={}
for phase in ("cold","unchanged-1","unchanged-2"):
    d=p/"results/cold-ron-stage-v2/whole-default"/phase;s=read(d/"summary.json");procs=read(d/"processes.json")
    archives={v.name:digest(v) for v in (d/"ron").iterdir() if v.is_file()}
    n=read(d/"raw-native.json");native={rel(k):v for k,v in n.items()}
    jobs=[[pid,crate,m] for pid,crate,m,*rest in procs["rustc"]]
    links=[[row[0],rel(row[1]),bool(row[2])] for row in procs["native_links"]]
    args=read(d/"ron-argv.json")
    whole[phase]={"native":native,"units":s["units"],"fresh":s["fresh"],"executables":s["executables"],"dirty":s["dirty"],"rustc":jobs,"linker_outputs":links,"wild":sum(v[-1] for v in links),"system_links":sum(not v[-1] for v in links),"ron_argv_count":len(args),"ron_flags":[[v for v in rec["args"] if any(v.startswith(p) for p in ("-Zohm-observer-dep-info","-Zbinary-dep-depinfo","-Zchecksum-hash-algorithm"))] for rec in args],"markers":s["depinfo_markers"],"checksum_count":s["depinfo_checksum_count"],"cargo_output_sha256":digest(d/"stdout"),"cargo_log_sha256":digest(d/"stderr"),"raw_roster_sha256":digest(d/"processes.json"),"ron_files":archives,"native_snapshot_sha256":digest(d/"raw-native.json"),"diagnostics_sha256":s["messages"],"elapsed_traced_ns":s["elapsed_ns"]}
write("whole-default",whole)
write("stage-permanent",read(q/"controls-v2/permanent-stage-v2/case.json"))
write("release-permanent",read(q/"controls-v2/permanent-pgo-v2/case.json"))
write("bound-v2",read(q/"controls-v2/binding.json"))
