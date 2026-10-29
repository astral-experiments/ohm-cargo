from pathlib import Path
import re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import *
def file_status(p):return dict(bytes=p.stat().st_size,sha256=sha(p))
def observed(k,q):
    rows,units=typed(q)
    assert rows[-1]=={"reason":"build-finished","success":True} and len(units)==510
    assert not any(z["reason"]=="compiler-message" and z["message"].get("level")=="error" for z in rows)
    return {"rows":len(units),"dirty":sum(not u["fresh"] for u in units),"roster":body(full_roster(q)),"outputs":body(output_keys(q)),"stdout":file_status(q)}
def inputs():
    from verify_generation import get, OLD_PROTOCOL, QA_MANIFEST
    source=Path(__file__).resolve().parent
    pr=R/"protocol-v1"
    assert sha(pr/"SHA256SUMS")==OLD_PROTOCOL
    assert sha(pr/"genoa.json")=="b7594ea85252780260b1aecce5221a548adcd4b4cce8c8353f77321a4f9c3093"
    assert sha(pr/"paired.py")=="2ce9665076a3836d7a65d42196d5c31d6f9eb3e0a43ddf37708b2a945a642b1c"
    a=R/"genoa-supplement-admission.json";ready=R/"genoa-supplement-ready.json"
    v=get(a);rd=get(ready);grant=get(R/"genoa-supplement-clock-release.json")
    assert grant["go"] is True and grant["host"]=="genoa" and grant["pairs"]==32 and grant["replacements"]==0
    assert rd["eligible"] and rd["qualified_generations"]==8 and rd["clocks_open"] is False
    assert grant["admission"]==rd["admission_sha256"]==sha(a)
    assert grant["preflight"]==sha(ready) and grant["supplement_manifest"]==sha(source/"SHA256SUMS")
    assert grant["qualification_manifest"]==v["public"]==QA_MANIFEST and grant["original_protocol"]==v["protocol"]==OLD_PROTOCOL
    assert all(re.fullmatch(r"[0-9a-f]{40}",grant[k]) for k in ("qualification_ref","supplement_ref"))
    assert sha(R/"admin-pgo-materials.json")==v["materials"]
    for f,h in get(R/"admin-pgo-materials.json").items():assert sha(R/f)==h
    for ln in (source/"SHA256SUMS").read_text().splitlines():
        dg,name=ln.split("  ",1);assert Path(name).name==name and sha(source/name)==dg
    assert not (R/"admin-pgo-admitted.json").exists() and not (R/"admin-pgo-scored").exists()
    return get(pr/"genoa.json"),v,grant
def slot(n,orderpos):
    ordered,verification,enabling=inputs();pair=ordered[n];k=pair["order"][orderpos]
    to,fr=(old,new) if pair["direction"]=="child-to-parent" else (new,old)
    return k,to,fr,("admin-closed-child" if fr==new else "admin-closed-parent"),pair,verification
def execute(n,pos):
    k,to,fr,anchor,pair,qa=slot(n,pos)
    assert 0<=n<32 and pos in (0,1)
    require_admin_namespace();set_arm(k);require_source(fr)
    d=R/"genoa-supplement-scored"/f"pair-{n:02d}-visit-{pos}-{k}";d.mkdir()
    canon=qa["admission"][k]["parent" if to==old else "child"]
    mountrow=json.loads((R/"genoa-supplement-scored"/(d.name+".reset.json")).read_bytes())
    assert mountrow["source"]==anchor and mountrow["started"]==show(live) and mountrow["source_show"]==qa["anchors"][anchor]
    e=env();assert all(not t.startswith(("RUSTFLAGS","RUSTC","CARGO_LOG","CARGO_UNSTABLE")) for t in e)
    assert e["CARGO_NET_OFFLINE"]=="true" and e["CARGO_TARGET_DIR"]==str(live/"target") and e["CARGO_BUILD_BUILD_DIR"]==str(live/"shared")
    cref=[str(c) for c in cmd]
    save(d/"command.json",{"source_before":fr,"source_edit":to,"cargo":prog_arms[k][1],"argv":cref,
         "env":e,"cwd":str(work),"cpus":sorted(os.sched_getaffinity(0)),"pair":pair,"order_position":pos,
         "mount_sha":sha(R/"genoa-supplement-scored"/(d.name+".reset.json")),"floor":floors()})
    direct_edit(fr,to);ra=[];started=False
    pre=admin_state();fds={}
    for n,row in pre.items():
        pth=gitadmin/n;fd=os.open(pth,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        fds[n]=fd
    def descriptor_stats():
        result={}
        for n,fd in fds.items():
            v=os.fstat(fd);result[n]={k:getattr(v,k) for k in pre[n] if k!="sha256"}
        return result
    stable={n:{k:v for k,v in row.items() if k!="sha256"} for n,row in pre.items()}
    gc=[];assert stable==descriptor_stats()
    try:
        with (d/"edit.jsonl").open("xb") as a,(d/"edit.stderr").open("xb") as b,(d/"repeat.jsonl").open("xb") as c,(d/"repeat.stderr").open("xb") as f:
            # Only normal launch-through-wait occurs inside the two clocks.
            # Only fstat on already-open Git-admin descriptors runs after a clock.
            # File bytes, source, Cargo reports and timings are postchecked outside both.
            started=True
            for step,outf,errf in (("edit",a,b),("repeat",c,f)):
                begin=time.monotonic_ns()
                p=subprocess.run(cref,cwd=work,env=e,stdout=outf,stderr=errf)
                end=time.monotonic_ns()
                ra.append({"step":step,"from":begin,"to":end,"ns":end-begin,"exit":p.returncode})
                if p.returncode:break
                now=descriptor_stats();gc.append(body(now));assert now==stable,(step,"linked-worktree admin changed")
        save(d/"executions.json",ra)
        assert len(ra)==2 and all(a["exit"]==0 and a["ns"]>0 for a in ra)
        typedrows={}
        for phase in ("edit","repeat"):
            v=observed(k,d/(phase+".jsonl"))
            assert v["roster"]==canon["roster"] and v["outputs"]==canon["outputs"],(phase,v,canon)
            v["stderr"]=file_status(d/(phase+".stderr"));typedrows[phase]=v
        actual_metadata=selected_files(typed(d/"repeat.jsonl")[1])
        meta={str(Path(path).relative_to(live)):{"bytes":val["len"],"sha256":val["sha256"]} for path,val in actual_metadata.items()}
        assert len(meta)==2 and meta==canon["metadata"],(n,pos,k,meta)
        require_source(to);assert admin_state()==pre and len(gc)==2
        save(d/"git-admin.json",{"state":pre,"before":body(stable),"after_each":gc})
        save(d/"terminal.json",{"ok":True,"pair":pair["pair"],"phase_index":pos,"arm":k,"direction":pair["direction"],"products":typedrows,"metadata":meta,"executions_sha":sha(d/"executions.json"),"source":to,"subvol":show(live),"postfloor":floors()})
        # Keep the actual products away from the next ordinary arm until both
        # visits can be checked at their original paths outside the pair.
        held=volume/("supplement-held-"+d.name);assert not held.exists()
        snapshot(live,held,True);assert ro(held)
        save(d/"checkpoint.json",{"held_info":show(held),"source_info":show(live),"terminal":sha(d/"terminal.json")})
    except BaseException as err:
        save(d/"failure.json",{"began":started,"completed_native":ra,"error":repr(err),"source":to,"arm":k})
        raise
    finally:
        for fd in fds.values():os.close(fd)
if __name__=="__main__":
    execute(int(sys.argv[1]),int(sys.argv[2]))
