"""Read raw input snapshots and preserved native/output/reader gates before timing."""
from pathlib import Path
import gzip, os, subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import *
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_generation import QA_MANIFEST, OLD_PROTOCOL, EXCEPTION_NAMES, get, hash_bytes
HERE=Path(__file__).resolve().parent;TARGET=R/"genoa-supplement-admission.json"
public=R/"genoa-native-public-v1"
def main():
    assert not TARGET.exists() and not (R/"admin-pgo-admitted.json").exists() and not (R/"genoa-supplement-scored").exists()
    assert sha(public/"SHA256SUMS")==QA_MANIFEST and sha(R/"protocol-v1/SHA256SUMS")==OLD_PROTOCOL
    subprocess.run([sys.executable,"-IB",public/"verify.py"],check=True)
    q=get(public/"qualification.json");assert q["scored_visits"]==0 and q["strict_output_identity"]=="failed" and q["cohort_failure_sha"]==sha(R/"admin-pgo-admit.err")
    assert q["stock_rust"]==sha(stock/"bin/rustc") and q["stock_driver"]==sha(stock/"lib/librustc_driver-b03bf00bec23bb9a.so")
    assert q["release_cargo"]=={k:sha(v[0]) for k,v in prog_arms.items()} and all(sha(R/f)==s for f,s in get(R/"admin-pgo-materials.json").items())
    rc=R/"same-donor-actual-products/replicated/receipt.json";data=get(rc)
    obs=json.loads(gzip.decompress((public/"objects.json.gz").read_bytes()))
    assert sha(rc)==obs["acquisition"] and sha(R/"real-linter-readers-v1/geometry.json")==obs["geometry"]
    u=json.loads(gzip.decompress((public/"readers.json.gz").read_bytes()))
    for label,r in u.items():assert sha(R/"real-linter-readers-v1"/label/"terminal.json")==r["receipt"]
    for arm in "AB":
        routed=site/("admin-route-"+arm)/"terminal.json";rr=get(routed)
        assert sha(routed)==q["matched_route_receipts"][arm] and rr['image']==prog_arms[arm][1] and rr['physical_exe']==str(R/"one-cargo-path/bin/cargo") and rr['full']==["ty_python_semantic"] and rr['typed']==510
    ledger={};refs={};ends={};newauth={x:{} for x in "AB"};bases={}
    for tag,fr in (("child",new),("parent",old)):
        name="admin-closed-"+tag;anchor=volume/name
        assert ro(anchor) and show(anchor)==q["read_only_anchors"][tag]
        v=get(site/("prime-"+tag)/"terminal.json");assert len(v['checks'])>=4
        before=get(site/("prime-"+tag)/"A-open-1/files.json")
        assert len(before)==597
        for k in "AB":
            for n in (1,2):
                d=site/("prime-"+tag)/f"{k}-open-{n}"
                assert v['checks'][f"{k}-open-{n}"]['rows']['physical']['full']==["ty_python_semantic"] and get(d/"files.json")==before
        for rel,fileinfo in before.items():
            path=anchor/rel;assert path.stat().st_size==fileinfo['bytes'] and sha(path)==fileinfo['sha256']
        bases[name]=show(anchor);refs[name]={"ledger":body(before),"all_files":597,"immutable":True}
    for dr,fr,to in (("child-to-parent",new,old),("parent-to-child",old,new)):
        per={}
        for label in ("A","A2","B","B2"):
            self=site/(dr+"-"+label);term=get(self/"terminal.json")
            assert sha(self/"terminal.json")==q['native'][self.name]['terminal_sha256'] and term['source']==to
            t=term['checks'];assert closed(t['baseline']) and closed(t['repeat2'])
            for lab in ("baseline","edit","repeat1","repeat2"):
                d=self/("before" if lab=="baseline" else lab);nr=t[lab];f=d/"files.json"
                assert sha(f)==nr['ledger_file'] and sha(d/"native.json")==nr['rows']['physical']['native_record_sha256']
                assert nr['rows']['typed_units']==510 and nr['rows']['physical']['exit']==0
                gr=get(d/"git-admin.json");assert gr["equal"] and gr["before"]==gr["after"] and not gr["training"]
            assert t['baseline']['ledger_digest']==refs["admin-closed-"+("child" if fr==new else "parent")]['ledger']
            full=t['repeat2']['rows'];vals={str(Path(f).relative_to(live)):{"bytes":v["len"],"sha256":v["sha256"]} for f,v in full['selected_files'].items()};assert len(vals)==2
            per[label]={"roster":full['typed_complete_roster'],"outputs":full['output_roster'],"metadata":vals}
            assert all(t[p]['rows']['typed_complete_roster']==per[label]['roster'] and t[p]['rows']['output_roster']==per[label]['outputs'] for p in ('edit','repeat1'))
        assert all(v==per['A'] for v in per.values())
        for k in "AB":newauth[k]["parent" if to==old else "child"]=per[k]
        reference=site/(dr+"-A")/"repeat2/files.json"
        ends[dr]={"reference":str(reference.relative_to(R)),"reference_sha256":sha(reference),"source_files":{p:hash_bytes(s) for p,s in cohort()[to].items()}}
    checks={"materials":sha(R/"admin-pgo-materials.json"),"public":QA_MANIFEST,"protocol":OLD_PROTOCOL,"native_receipt":sha(rc),"geometry":obs["geometry"],"prior_strict_failure":q['cohort_failure_sha'],"exclusions":sorted(EXCEPTION_NAMES),"initial_cold_exclusion":q["initial_cold_nondeterminism"],"anchors":bases,"anchor_inputs":refs,"endpoints":ends,"admission":newauth,"cargo_pair":q["release_cargo"],"external_readers":40,"still_closed":True}
    save(TARGET,checks)
if __name__=="__main__":main()
