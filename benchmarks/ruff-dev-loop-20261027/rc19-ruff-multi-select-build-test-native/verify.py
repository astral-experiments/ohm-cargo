"""Check the 14 commands, harness selection, actual links and externally observed readers."""
from collections import Counter
from pathlib import Path
import copy,gzip,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parent
OLD="716260bf10d7ae1d965ed9b22653e57fbc960582"
NEW="2d6ce561250a464e1fa231ef30e54d0f029f76a4"
CLI="49e54b647a7f6ef8ec50db00432d2e657729b2deb457fffd839f1045e9ac86cf"
E2E="e9e9b00a45107e5c2b6dde7c0dd9ad2f3dc527681171876f120f12225149e0c2"
E2E_EDIT="1d0cd985f072076feb22f197402d18fd7e8f718c93df6e612645657bdf42fdde"
def verify(x):
    assert x["source"]=={"old":OLD,"new":NEW,"lock":"34e5c62a1d7c45679fc0113e8a8814452e67d9969dd1079adb234bd7803ddc6d"}
    assert len(set(x["workspace"]))==47 and x["all_default"]
    assert x["images"]["cargo"]=="6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac"
    assert x["images"]["rustc"]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
    assert x["images"]["stock-wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    assert set(x["commands"])=={"build","test"}
    roots={}
    for mode,series in x["commands"].items():
        assert set(series)=={"unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2","child-edit","child-unchanged-1","child-unchanged-2"}
        for tag,d in series.items():
            parent=tag.startswith("parent");edit=tag.endswith("-edit")
            assert d["source"]==(OLD if parent else NEW) and d["git_admin_unchanged"]
            assert all(re.fullmatch("[0-9a-f]{64}",h) for h in d["original_log_sha256"].values())
            assert len(d["original_log_sha256"])==5 and all(re.fullmatch("[0-9a-f]{64}",a["argv_sha256"]) for a in d["native"])
            if mode=="build":
                full,linkonly,link=(47,4,9) if edit else (2,4,5)
                typed,dirty=475,52 if edit else 12
            else:
                full,linkonly,link=((132,8,98) if parent else (119,8,85)) if edit else ((4,16,19) if parent else (4,15,18))
                typed=571 if parent else 558
                dirty=(140 if parent else 127) if edit else None
            roles=Counter(e["role"] for e in d["native"])
            assert roles["cargo"]==1 and roles["rustc-full"]==full
            assert roles["rustc-link-only"]==linkonly and roles["stock-wild"]==roles["gcc"]==roles["collect2"]==link,(mode,tag,roles)
            assert len(d["typed"])==typed
            assert all(type(a["fresh"]) is bool for a in d["typed"])
            if dirty is not None:assert sum(not a["fresh"] for a in d["typed"])==dirty
            if mode=="build":
                assert d["reader"]["exe_sha"]==CLI
                assert d["reader"]["ruff"]==[["dirty",1,[["F821",{"row":1,"column":7}]]],["valid",0,[]]]
            else:
                reader=d["reader"];ev,=reader["e2e"];names=reader["e2e_names"]
                raw="".join(names).encode()
                assert ev==["e2e",103,"820bd0b922066f4ed910156a81444755d91e56623d4e35d443e3026eacf72942",E2E_EDIT if tag=="child-edit" else E2E]
                assert hashlib.sha256(raw).hexdigest()==ev[2] and sum(line.endswith(": test\n") for line in names)==103
                def key(pkg,target,kind):return (pkg,target,tuple(kind))
                harness={key(Path(p).parent.name,t,k) for p,t,k in reader["test_harnesses"]}
                from_units={key(a["package"],a["target"],a["kind"]) for a in d["typed"] if a["workspace"] and a["profile_test"] and a["executable"]}
                assert harness==from_units and len(harness)==(89 if parent else 76)
                flag="parent" if parent else "child"
                if flag in roots:assert roots[flag]==harness
                roots[flag]=harness
    added=roots["parent"]-roots["child"]
    assert not roots["child"]-roots["parent"] and len(added)==13
    assert all("lib" in kind or "rlib" in kind or "proc-macro" in kind for _,_,kind in added)
    return sorted(p for p,_,_ in added)
if __name__=="__main__":
    x=json.loads(gzip.decompress((ROOT/"observations.json.gz").read_bytes()))
    changes=verify(x)
    if "--mutations" in sys.argv:
        for field in ("wild","native","harness","reader"):
            y=copy.deepcopy(x);d=y["commands"]["test"]["child-edit"]
            if field=="wild": d["native"].remove(next(a for a in d["native"] if a["role"]=="stock-wild"))
            if field=="native": d["reader"]["e2e"][0][3]=E2E
            if field=="harness": d["reader"]["test_harnesses"].pop()
            if field=="reader": d["reader"]["e2e_names"].pop(0)
            try:verify(y)
            except AssertionError:continue
            raise AssertionError("accepted "+field)
    print("Verified all 14 commands, native exec counts and both readers. Extra parent library harnesses: "+", ".join(changes))
