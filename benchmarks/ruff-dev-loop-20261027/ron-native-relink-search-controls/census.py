"""Read the already published exact three repeated Ruff Wild rosters."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,json
p=argparse.ArgumentParser();p.add_argument("operands",type=Path);a=p.parse_args()
def dig(b):return hashlib.sha256(b).hexdigest()
wire=a.operands.read_bytes();j=json.loads(gzip.decompress(wire));reference=None;summaries={}
for phase,targets in sorted(j["by_phase"].items()):
    assert len(targets)==50
    if reference is None: reference=set(targets)
    assert set(targets)==reference
    groups=Counter(); ron=0; psm_first=0; naked=[]
    for target,row in targets.items():
        names=[(v["mode"],v["name"]) for v in row["libraries_in_order"]]
        assert names==[("dynamic",n) for n in ("gcc_s","util","rt","pthread","m","dl","c")]
        assert row["typed_direct_inputs"]["system/object"]==5
        assert "--as-needed" in row["bare_options_in_order"] and "-pie" in row["bare_options_in_order"]
        assert not row["explicit_scripts"] and not row["response_files"]
        assert any(s.startswith("-dynamic-linker ") for s in row["bound_options_in_order"])
        assert any(s.startswith("-plugin ") for s in row["bound_options_in_order"])
        directories=[v["role"] for v in row["search_directories_in_order"]]
        assert directories[:2]==["target/unit-compiler-temp/raw-dylibs","target/unit/psm/out"]
        psm_first+=1
        project=tuple(x for x in directories if x.startswith("target/unit/"))
        groups[project]+=1
        present=row["typed_direct_inputs"].get("target/ron-rlib",0);assert present in (0,1);ron+=present
        if not present:naked.append(target)
    assert ron==35 and sorted(groups.values())==[13,16,21] and psm_first==50
    summaries[phase]=dict(links=len(targets),without_bare_ron=sorted(naked),with_bare_ron=ron,first_nontransient_search_is_psm=psm_first,project_search_families={",".join(k):v for k,v in sorted(groups.items())},pure_rust_without_native_search=0)
print(json.dumps({"raw_prior_public_operands_sha256":dig(wire),"phases":summaries},indent=2))
