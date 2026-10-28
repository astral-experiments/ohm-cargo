import hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
native=json.loads((p/"observations.json").read_bytes());co=json.loads((p/"census.json").read_bytes())
assert set(native)=={"psm","psm-zstd","psm-zstd-jemalloc"}
for k,rows in native.items():
    assert [x["phase"] for x in rows]==["original","new-earlier-input","invalid-earlier-input","restored"]
    assert [x.get("program") for x in rows]==[41,83,None,41]
    assert [x["link"]==0 for x in rows]==[True,True,False,True]
    assert all(x["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5" and x["successful_wild_execs"]==1 and x["baseline_inputs_unchanged"] for x in rows)
    assert rows[0]["elf"]==rows[3]["elf"]!=rows[1]["elf"]
assert set(co["phases"])=={"unchanged-1","unchanged-2","unchanged-3"}
for t in co["phases"].values():
    assert t["links"]==t["first_nontransient_search_is_psm"]==50
    assert t["pure_rust_without_native_search"]==0 and len(t["without_bare_ron"])==15 and t["with_bare_ron"]==35
    assert sorted(t["project_search_families"].values())==[13,16,21]
print(json.dumps(dict(stock_relinks=12,real_Ruff_census=150,eligible_pure_Rust=0,changed_programs=3,rejected_links=3,restorations=3)))
