from pathlib import Path
import json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from archive import *
def run(rows):
    a,b,c=[p.read_bytes() for p in rows]
    cases={"same":compare(a,a),"same-parent-two-original-edits":compare(a,b),"independent-cold-with-real-metadata":compare(a,c)}
    assert cases["same-parent-two-original-edits"]["equivalent_exact_names"] and len(cases["same-parent-two-original-edits"]["edits"])==144
    assert not cases["independent-cold-with-real-metadata"]["equivalent_exact_names"]
    cr=census(b)
    for name,idx in [(b"/",2),(b"lib.rmeta",24),(b"lib.rmeta-link",6),(cr[-1][0],18)]:
        altered=bytearray(b);o=next(t for t in cr if t[0]==name)[2];altered[o+idx]^=1
        result=compare(a,bytes(altered));assert not result["equivalent_exact_names"]
        cases["one-byte-"+(name.decode() if name!=b"/" else "symbol-index")]=result
    return {key:{x:y for x,y in z.items() if x not in ("channels","edits","examples")}|{"individually_proven_offsets":len(z.get("edits",[]))} for key,z in cases.items()}
if __name__=="__main__":
    print(json.dumps(run([Path(k) for k in sys.argv[1:]]),sort_keys=True,indent=2))
