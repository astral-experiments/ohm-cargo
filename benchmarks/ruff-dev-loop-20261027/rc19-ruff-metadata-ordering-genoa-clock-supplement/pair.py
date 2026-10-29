"""Close two off-clock reader checks before accepting or removing their snapshots."""
import os, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from clock import inputs, save, sha, R, volume, live, floors, show, ro
from proof import show_value
n=int(sys.argv[1]);assert 0<=n<32
mode=sys.argv[2];assert mode in ("validate","seal")
seq,admit,grant=inputs();spec=seq[n];assert spec['pair']==n
where=R/'genoa-supplement-scored';visits={};held=[]
if mode=="seal":
    valid=where/f"pair-{n:02d}.validated.json";row=json.loads(valid.read_bytes());assert len(row["owned"])==2
    assert all(not (volume/v).exists() for v in row["owned"])
    save(where/f"pair-{n:02d}.accepted.json",{"pair":n,"visits":row["visits"],"validated":sha(valid),"removed":row["owned"],"floor":floors()})
    sys.exit(0)
for pos,k in enumerate(spec["order"]):
    name=f"pair-{n:02d}-visit-{pos}-{k}";d=where/name
    t=json.loads((d/'terminal.json').read_bytes());c=json.loads((d/'checkpoint.json').read_bytes());b=json.loads((d/'post-pair/accepted.json').read_bytes())
    assert t['ok'] and t['arm']==k and t['direction']==spec['direction'] and t['executions_sha']==sha(d/'executions.json')
    assert b['source']==t['source'] and b['mode']=='ordinary-current' and b['reader']==sha(d/'post-pair/reader.json') and b['raw']==sha(d/'post-pair/raw-products.json') and b['exceptions']==sha(d/'post-pair/raw-exception-files.json') and b['sources']==sha(d/'post-pair/source-files.json')
    p=volume/("supplement-held-"+name);assert p.parent==volume and p!=live and ro(p) and show(p)==c['held_info']
    assert show_value(c['held_info'],"Parent UUID")==show_value(t['subvol'],"UUID") and c['terminal']==sha(d/'terminal.json')
    held.append((p,show_value(c['held_info'],"Subvolume ID")))
    visits[name]={"terminal":sha(d/'terminal.json'),"checkpoint":sha(d/'checkpoint.json'),"reader_and_products":sha(d/'post-pair/accepted.json'),"all_raw":b["raw"],"source_files":b["sources"],"full_hash_exceptions":b["exceptions"]}
assert len(visits)==2 and not (where/f"pair-{n:02d}.accepted.json").exists()
save(where/f"pair-{n:02d}.validated.json",{"pair":n,"visits":visits,"owned":{p.name:show(p) for p,i in held},"uid":os.getuid()})
