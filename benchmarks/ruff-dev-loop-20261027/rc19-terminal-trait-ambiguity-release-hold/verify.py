"""Verify traced terminal checks, schedule ordering, matched binaries and fixture bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

here=Path(__file__).resolve().parent
ALL=["api","provider","reader","client"]
IMAGES={
    "A":"3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7",
    "B":"51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9",
    "official-18":"02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573",
    "official-17":"4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3",
}
def digest(b):
    return hashlib.sha256(b).hexdigest()

def check_arm(d,role):
    assert d["images"]["cargo"] == IMAGES[role]
    compiler,driver = ("7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c",
                       "618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7") if role=="official-17" else (
                       "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60",
                       "a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de")
    assert d["images"]["rustc"]==compiler and d["images"]["driver"]==driver
    src={n:(here/"fixture"/n/"src"/("main.rs" if n=="client" else "lib.rs")).read_bytes() for n in ALL}
    changed=src|{"reader":src["reader"].replace(b"{ 11 }",b"{ 12 }"),
                 "provider":src["provider"]+b"impl api::Second for Token { fn priority(&self) -> u8 { 29 } }\n"}
    original={n:digest(b) for n,b in src.items()}
    edited={n:digest(b) for n,b in changed.items()}
    assert original["reader"]!=edited["reader"]
    cases=d["cases"]
    assert len(cases)==22 and len(d["terminal"])==4
    def case(name,code,crates,source):
        r=cases[name]
        assert r["exit"]==code and r["sources"]==source, (role,name,"result")
        assert [i["crate"] for i in r["compilers"]]==crates,(role,name,"real compiler")
        for i in r["compilers"]:
            assert i["end"]>=i["start"] and re.fullmatch("[0-9a-f]{64}",i["literal_syscall_sha256"])
            assert re.fullmatch("[0-9a-f]{64}",i["argv_sha256"])
        assert all(re.fullmatch("[0-9a-f]{64}",v) for v in r["original_files"].values())
        assert {"native.trace","cargo.stdout","cargo.stderr","result.json"} <= r["original_files"].keys()
        if code:
            error,=r["errors"]
            assert (error["crate"],error["code"],error["message"],error["primary"])==(
                "client","E0034","multiple applicable items in scope",[["client/src/main.rs",3,30]])
            notes=[b for kind,b in error["children"] if kind=="note"]
            assert any("`First`" in t and "`Token`" in t for t in notes)
            assert any("`Second`" in t and "`Token`" in t for t in notes)
        else:
            assert not r["errors"]
        return r
    case("base",0,ALL,original)
    assert case("base-repeat",0,[],original)["artifacts"]==dict.fromkeys(ALL,True)
    seen=[]
    for group, terminal in d["terminal"].items():
        order=group[2:]
        seen.append(order)
        late=order=="provider-late"
        # Released images and the parent admit the forbidden unchanged middle.
        stale=late and role!="B"
        err=0 if stale else 101
        assert terminal==dict(warm=err,on_repeat=err,empty=101,restore=0,restore_repeat=0)
        warm=case(group+"-edit",err,["provider","reader"]+([] if stale else ["client"]),edited)
        assert warm["order"]==order
        assert warm["before"]["provider"]["hash"]["value"]!=warm["after"]["provider"]["hash"]["value"]
        assert warm["before"]["provider"]["rmeta"]["sha256"]!=warm["after"]["provider"]["rmeta"]["sha256"]
        assert warm["before"]["reader"]["hash"]["value"]==warm["after"]["reader"]["hash"]["value"]
        assert warm["before"]["reader"]["rmeta"]["sha256"]!=warm["after"]["reader"]["rmeta"]["sha256"]
        event=warm["ordering"]
        def point(k,v):
            events=[x for x in event if x["event"]==k and x["value"]==v]
            assert len(events)==1,(role,group,k,v)
            return events[0]["start"]
        def fp(crate):
            return point("fingerprint-committed",crate+"/"+warm["after"][crate]["fingerprint"]["value"])
        hold_crate="provider" if late else "reader"
        hold=point("hold-fd",hold_crate)
        release=point("release-fd",hold_crate)
        p=point("rustc-published","provider")
        r=point("rustc-published","reader")
        origin=point("origin-published-state","changed")
        middle=point("reader-published-state","unchanged" if stale else "changed")
        decision=point("client-decision","skip" if stale else "run")
        assert p<r and r<middle<fp("reader") and p<origin<fp("provider")
        assert hold<release and middle<decision
        if late:
            assert p<hold<fp("reader")<release<origin
        else:
            assert fp("provider")<release<middle
        entries=warm["interposer"]
        assert [x["action"] for x in entries if x["action"] not in ("before-fd","after-fd")]==["hold-fd","release-fd"]
        assert all(x["crate"]==hold_crate and x["restore"]==0 for x in entries if x["action"] in ("hold-fd","release-fd"))
        assert all(x["seen_ns"]==x["requested_ns"] for x in entries if x["action"]=="after-fd")
        repeat=case(group+"-repeat",err,[] if stale else ["client"],edited)
        if stale:
            assert repeat["artifacts"]==dict.fromkeys(ALL,True)
        clean=case(group+"-clean",101,ALL,edited)
        assert all(not fields for fields in clean["before"].values())
        if not stale:
            assert warm["errors"]==repeat["errors"]==clean["errors"]
        case(group+"-restore",0,["provider","reader","client"],original)
        assert case(group+"-restore-repeat",0,[],original)["artifacts"]==dict.fromkeys(ALL,True)
    assert sorted(seen)==["provider-first"]*2+["provider-late"]*2
    return sum(c["exit"]==0 for c in cases.values())

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add-17",type=Path)
    options=parser.parse_args()
    assert digest((here/"commit-order.c").read_bytes())=="3f7d541eb5bafe4482b394cf54e79ba1b66958ba82cfbb9efef788975ea3ce1c"
    parts={r:here/(r+".json") for r in ["A","B","official-18"]}
    if options.add_17:
        parts["official-17"]=options.add_17
    for role,path in parts.items():
        passed=check_arm(json.loads(path.read_bytes()),role)
        print(f"{role}: 22 complete checks, {passed} success and {22-passed} E0034, both orders twice")
    for name,data in json.loads((here/"standalone.json").read_bytes()).items():
        assert name in ("late","first")
        rows=data["phases"]
        assert set(rows)=={"original","original-repeat","edited","edited-repeat","edited-clean","restore","restore-repeat"}
        for phase,x in rows.items():
            fail=phase=="edited-clean" or (name=="first" and phase in ("edited","edited-repeat"))
            assert x["success"] is (not fail)
            assert x["errors"]==([["client","E0034"]] if fail else [])
            if phase in ("original-repeat","restore-repeat") or (phase=="edited-repeat" and not fail):
                assert x["fresh"]==sorted(ALL)
            assert all(re.fullmatch("[0-9a-f]{64}",x[k]) for k in ["stderr_sha256","stdout_sha256"])
    print("Standalone official -18: 14 further commands without strace or Cargo debug logging.")
