"""Match each effective Wild -o argument to one Cargo product and compare raw ELF SHA-256s."""
from pathlib import Path
import hashlib
import json

here=Path(__file__).resolve().parent
data=here/"stdlib-link-products.json"
sets=json.loads(data.read_bytes())
report={}
for mode,phases in sets.items():
    pairs=[]
    for idx in (1,2):
        ed=phases[f"edit-{idx}"]
        re=phases[f"restore-{idx}"]
        names={r["linker_output"] for r in ed["wild"]}
        count=7 if mode=="build" else 41
        assert len(names)==len(ed["wild"])==len(re["wild"])==count
        assert names=={r["linker_output"] for r in re["wild"]}
        for records in (ed,re):
            assert all(len(w["sha256"])==64 and w["file"].startswith("exec.") for w in records["wild"])
        prods={r["product"]:r for r in ed["artifacts"]}
        restored={r["product"]:r for r in re["artifacts"]}
        assert len(prods)==len(restored)==(15 if mode=="build" else 110)
        same=[]; changed=[]
        for name in sorted(names):
            pkg,unit,out,base=name.split("/")
            assert out=="out" and len(unit)==16
            hits=[p for p,r in prods.items() if p==name or (
                r["package"]==pkg and Path(p).parent.as_posix()=="ohm-whole-skips-20261027/native-target/debug"
                and Path(p).name==base and not r["test_profile"])]
            assert len(hits)==1,(mode,name,hits)
            p=hits[0];a,b=prods[p],restored[p]
            assert all(a[k]==b[k] for k in ("package","kind","target","test_profile"))
            item={"wild":name,"product":p,"package":a["package"],"target":a["target"],"kind":a["kind"],
                  "test_profile":a["test_profile"],"edited":a["sha256"],"restored":b["sha256"]}
            (same if a["sha256"]==b["sha256"] else changed).append(item)
        assert len(same)==(0 if mode=="build" else 12)
        pairs.append({"same":same,"changed":changed})
    consistent=set(item["product"] for item in pairs[0]["same"]) & set(item["product"] for item in pairs[1]["same"])
    assert len(consistent)==(0 if mode=="build" else 11)
    report[mode]={"pairs":pairs,"consistently_byte_identical":sorted(consistent)}
print(json.dumps(report,indent=2,sort_keys=True))
