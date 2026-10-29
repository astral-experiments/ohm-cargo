"""Recheck all eight unscored generations and freeze their receipts."""
import json, hashlib, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_generation import R, HERE, QA_MANIFEST, OLD_PROTOCOL, get, sha, save, EXCEPTION_NAMES
a=R/"genoa-supplement-admission.json";v=get(a);loc=R/"genoa-supplement-proof-rehearsal";state={}
data=get(R/"same-donor-actual-products/replicated/receipt.json")
for label in data["ordered"]:
    d=loc/label;b=get(d/"accepted.json");rd=get(d/"reader.json");files=get(d/"raw-products.json");ex=get(d/"raw-exception-files.json")
    assert set(ex)==EXCEPTION_NAMES and len(files)==597 and b['reader']==sha(d/"reader.json") and b['raw']==sha(d/"raw-products.json") and b['exceptions']==sha(d/"raw-exception-files.json")
    assert get(d/"source-files.json")==v['endpoints'][label.rsplit('-',1)[0]]['source_files'] and b['sources']==sha(d/'source-files.json')
    for path,cols in data['files'][label].items():assert files[path]['sha256']==cols['repeat2']
    assert rd['calls']['valid']['status']==rd['calls']['recovered']['status']==0
    assert rd['calls']['valid']['output']==rd['calls']['recovered']['output'] and rd['calls']['invalid']['codes']==["E0609"]
    assert rd['inputs']['ruff_linter']['credentials'][0]==ex['libruff_linter-b6d3cd0bff22fbfa.rmeta']['check']['private']
    state[label]={"generation_sha256":sha(d/"accepted.json"),"all_raw_outputs":b['raw'],"actual_reader":b['reader'],"sources":b["sources"],"exception_files":b["exceptions"],"private_hash":rd["inputs"]["ruff_linter"]["credentials"][0]}
assert len(state)==8 and len({v['private_hash'] for v in state.values()})==8
out={"eligible":True,"clocks_open":False,"qualified_generations":len(state),"admission_sha256":sha(a),"native_manifest":QA_MANIFEST,"old_protocol":OLD_PROTOCOL,"proof_sources":{n:sha(HERE/n) for n in ("verify_generation.py","proof.py","proof-namespace.sh","admit.py","natural.rs","bad.rs")},"generations":state}
demo=R/"genoa-supplement-custody-demo.json";assert len(get(demo)["two_visits"])==2
out["snapshot_rehearsal"]=sha(demo)
save(R/"genoa-supplement-ready.json",out)
