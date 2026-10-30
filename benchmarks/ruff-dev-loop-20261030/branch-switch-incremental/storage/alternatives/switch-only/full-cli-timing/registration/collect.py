#!/usr/bin/env python3
"""Reopen a completed chronological stage from original Cargo messages and process records."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
def module(n):
    s=importlib.util.spec_from_file_location(n,HERE/(n+".py"));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=module("analyze");worker=module("run_slot");require=a.require
def read(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def put(p,v):
    with p.open("x") as f:json.dump(v,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())

def collect(study,stage):
    conf=read(study/"private/config.json")
    plan=read(HERE/"plan.json");ref=read(study/"native-reference.json");native=Path(conf["native_custody"])
    require(sha(native/"independent-terminal.json")==ref["public"]["native_independent_terminal"],"original native receipts")
    if stage=="confirmation":
        p=read(study/"pilot/result.json");proof=read(study/"pilot/verified.json")
        require(p["go"] and p["pairs"]==2 and sha(study/"pilot/result.json")==proof["analysis_sha256"],"terminal independent pilot qualification")
    scopes=read(study/"route.json");display={**ref["public"],"selected_resource_route":scopes["name"],"slots":[]}
    for s in a.schedule(plan):
        if s["stage"]!=stage:continue
        tag=s["slot"];arm=s["arm"];base=study/"runs"/tag;log=study/"logs"/tag;closed=read(log/"closed.json");complete=read(base/"completed.json")
        require(closed["exit"]==0 and closed["completed"]==sha(base/"completed.json") and len(complete["visits"])==5,"complete unaltered installation")
        require(closed["route_sha256"]==sha(study/"route.json") and closed["maximum_scratch_receipt_bytes"]<=384*2**20,"same bounded route")
        require(read(log/"sdk.json")["physical"]==ref["physical_files"] and sha(log/"front.json")==complete["front_sha256"],"all 57 original SDK files")
        bounds=read(log/"closed.json")["minima"];require(bounds[0]>140*2**30 and bounds[1]>140*2**30 and bounds[2]>52*2**30,"host minima")
        inside=read(log/"worker-resources.json");require(inside["minimum_source_free"]>2**30 and inside["minimum_output_free"]>2*2**30 and inside["pulses"]>1,"new working volumes")
        for piece in ("before","after"):
            v=read(log/("real-mounts-"+piece+".json"))
            require(v["all_visible_HOME_aliases_read_only"] and v["all_other_scratch_aliases_read_only"] and v["writable_HOME_budget"]==0 and v["effective_capabilities"]==0 and v["no_new_privs"]==1,"actual zero HOME-write admissions")
        for phase,row in zip(a.PHASES,complete["visits"]):
            ph=base/phase;process=read(ph/"cargo.process.json");observed=read(ph/"result.json")
            require(row=={**observed,"result_sha256":sha(ph/"result.json")},"actual raw result")
            require(process["argv"]==plan["cargo_argv"] and process["blocking_wait"]=="wait4" and process["input_setting"]==(plan["on_flag"] if arm=="on" else None),"physical Cargo")
            require([process[k] for k in ("wall_ns","user_cpu_us","system_cpu_us")]==[row[k] for k in ("elapsed_ns","user_cpu_us","system_cpu_us")],"actual elapsed and CPU")
            require([v["stream"] for v in process["stdout_and_stderr"]]==["stdout","stderr"],"both original complete streams")
            for rec in process["stdout_and_stderr"]:
                f=ph/("cargo."+rec["stream"]);require(f.stat().st_size==rec["size"] and sha(f)==rec["sha256"],"whole original streams")
            msgs=[json.loads(x) for x in (ph/"cargo.stdout").read_bytes().splitlines()]
            require(msgs[-1]=={"reason":"build-finished","success":True},"final Cargo success")
            arts=[m for m in msgs if m.get("reason")=="compiler-artifact"];rows,graph,dirty=worker.typed_roster(arts)
            rr=read(native/"runs"/(arm+"-storage")/phase/"result.json")
            require(rows==read(ph/"typed.json") and graph==row["graph_sha256"] and dirty==rr["dirty"] and worker.commit(dirty)==row["dirty_set_sha256"],"independent exact Cargo roster")
            require(sha(ph/"cargo.process.json")==row["process_sha256"] and row["storage"]==read(ph/"storage.json"),"storage and Cargo raw hashes")
            st=read(ph/"settled.json")
            require(st["all"]["allocated_bytes"]==row["storage"]["whole"] and st["all_incremental"]["allocated_bytes"]==row["storage"]["incremental"] and st["name_plus_inode_ledger_sha256"]==row["storage"]["ledger_sha256"],"whole retained census")
            for field,tag_name in [("version","ruff-version"),("source","ruff-version-json"),("clean","ruff-clean"),("warning","ruff-warning"),("fixed","ruff-fix"),("recheck","ruff-recheck"),("invalid","ruff-invalid")]:
                for sink in ("stdout","stderr"):
                    require(sha(ph/(tag_name+"."+sink))==rr["outcomes"][field][sink+"_sha256"],"retained native behavior")
            require((ph/"reader-run.stdout").read_text().strip()==rr["observed"] and read(ph/"reader-run.process.json")["exit"]==0,"actual independent caller")
            require(json.loads((ph/"ruff-version-json.stdout").read_bytes())["commit_info"]["commit_hash"]==row["source"],"actual CLI selected")
            for obj in (row["cli"],row["reader"]):
                file=native/"elf"/obj["sha256"];require(file.stat().st_size==obj["bytes"] and sha(file)==obj["sha256"],"independently reopened reference binary")
        display["slots"].append({**complete,"completion_sha256":sha(base/"completed.json")})
    result=a.compute(plan,display,stage);out=study/stage;out.mkdir()
    put(out/"observations.json",display);put(out/"result.json",result)
    put(out/"verified.json",{"stage":stage,"analysis_sha256":sha(out/"result.json"),"observations_sha256":sha(out/"observations.json"),
                            "route_sha256":sha(study/"route.json"),"registration_sha256":sha(HERE/"SHA256SUMS"),"slots":len(display["slots"]),"go":result["go"]})
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("study",type=Path);ap.add_argument("--stage",choices=("pilot","confirmation"),required=True)
    x=ap.parse_args();v=collect(x.study.resolve(),x.stage)
    print(json.dumps({"study":x.stage,"go":v["go"],"pairs":v["pairs"]}))
if __name__=="__main__":main()
