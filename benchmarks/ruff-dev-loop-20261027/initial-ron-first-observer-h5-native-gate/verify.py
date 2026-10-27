"""Check the retained native preflight commitments without starting a compiler."""
from collections import Counter
from pathlib import Path
import gzip, hashlib, json
root=Path(__file__).resolve().parent
read=lambda path:json.loads(path.read_bytes())
raw=json.loads(gzip.decompress((root/"native.json.gz").read_bytes()))
params=read(root/"input-hashes.json")
arms=raw["arms"]; assert set(arms)=={"C","D"}; sums={}
for arm, item in arms.items():
    value=item["commitments"]; assert value["arm"]==arm
    assert value["cargo"]==params["candidate-cargo-v3" if arm=="C" else "A"]
    assert value["rust"]==params["controls-v2/release/candidate-driver.so" if arm=="C" else "rustc-driver"]
    assert value["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    sums[arm]={}
    for i,phase in enumerate(("cold","first","settled")):
        row=value["phases"][phase]; phy=item["phases"][phase]; proc=row["processes"]; proof=item["proof"][phase]
        assert len(phy["native"])==110 and phy["native_file_sha256"]==row["native"]
        assert proc["full"]==phy["full_compilers"] and proc["relink"]==phy["relink_compilers"]
        assert Counter(z[1] for z in phy["native_linkers"])==Counter({True:proc["wild"],False:proc["system"]})
        assert row["fresh"]==((0,619,619) if arm=="C" else (0,563,619))[i]
        assert (len(proc["full"]),len(proc["relink"]),proc["wild"],proc["system"],len(proc["probe"]))==(
            ((636,0,201,62,1),(0,0,0,0,0),(0,0,0,0,0)) if arm=="C" else
            ((636,0,200,62,0),(1,50,50,0,0),(0,0,0,0,0)))[i]
        assert arm=="C" or phase!="first" or proc["full"]==["ron"]
        assert row["ron_complete"]==(arm=="C" or phase!="cold")
        assert len(proof["physical_inputs"])==row["checksums"]==(45 if row["ron_complete"] else 0)
        assert all(x[1]=="blake3" and len(x[2])==64 and x[3]>=0 for x in proof["physical_inputs"])
        assert proof["depinfo_sha256"]==row["ron_depinfo"] and proof["encoded_sha256"]==row["ron_fingerprint"]
        assert all(z["bytes"]>0 and len(z["raw"])==len(z["except_registered_wild_fields"])==64 for z in phy["native"].values())
        sums[arm][phase]=[row["fresh"],len(proc["full"]),len(proc["relink"]),proc["wild"],row["checksums"]]
    assert value["ordinary_native_oracles"]["passed"] and value["ordinary_native_oracles"]["stdlib_test_count"]==4
    cold,first,settled=[item["phases"][n]["native"] for n in ("cold","first","settled")]
    assert first==settled and (arm!="C" or cold==first)
    for k in cold:
        x,y=cold[k],first[k]
        if x!=y:
            assert arm=="D" and x["bytes"]==y["bytes"] and x["except_registered_wild_fields"]==y["except_registered_wild_fields"] and {x["rodata_entsize"],y["rodata_entsize"]}<={0,8}
assert arms["C"]["commitments"]["ordinary_native_oracles"]==arms["D"]["commitments"]["ordinary_native_oracles"]
oldp=arms["D"]["proof"]["first"]["physical_inputs"]; newp=arms["C"]["proof"]["cold"]["physical_inputs"]
assert len(oldp)==45 and len(newp)==45
diags=raw["settled_cross_compiler_diagnosis"];assert len(diags)==4
for key,v in diags.items():
    assert json.loads(key)[1] in {"ruff","ty"} and v["same_bytes_outside_debug_sections_and_two_fields"]
    assert len(set(v["raw_except_debug_sections_and_two_fields"]))==1 and set(v["changed_section_payloads"])=={".note.gnu.build-id",".debug_info",".debug_macro",".debug_str"}
    assert all(len(v[k])==1 and "/tikv-jemalloc-sys/" in v[k][0] for k in ("only_old_debug_strings","only_new_debug_strings"))
assert read(root/"independent-driver.json")["equal"]
print(json.dumps(sums,sort_keys=True))
