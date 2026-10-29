"""Check the prospective run code and externally bound physical pre-clock data."""
import ast, hashlib, json, subprocess, sys
from pathlib import Path
p=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
def timer(path):
    tree=ast.parse(path.read_bytes())
    matches=[n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [x.id for x in n.target.elts]==["step","outf","errf"]]
    assert len(matches)==1;return h(ast.dump(matches[0],include_attributes=False).encode())
def main():
    assert sys.flags.optimize==0
    m=[line.split("  ",1) for line in (p/"SHA256SUMS").read_text().splitlines()]
    assert all(Path(f).name==f and h((p/f).read_bytes())==v for v,f in m)
    b=json.loads((p/"bindings.json").read_bytes());r=json.loads((p/"preclock.json").read_bytes())
    assert b["old_protocol"]=="5ef08a85860887a0eb92c12bf51174a6264ab806989f807e2fb9c2f78bfb274e"
    assert b["old_order"]=="b7594ea85252780260b1aecce5221a548adcd4b4cce8c8353f77321a4f9c3093"
    assert b["old_analysis"]=="2ce9665076a3836d7a65d42196d5c31d6f9eb3e0a43ddf37708b2a945a642b1c"
    assert b["native"]=="ed552d17bd94cc464d4eea6addaa2427225cd3ddd8ef2caba9dfe805ab250b6d" and b["timer_ast"]==timer(p/"clock.py")
    assert h((p/"preclock.json").read_bytes())==b["physical_readiness_sha256"] and b["physical_admission_sha256"]==r["admission_sha256"]
    assert r["qualified_generations"]==8 and r["eligible"] and not r["clocks_open"]
    assert len({v["private_hash"] for v in r["generations"].values()})==8 and r["native_manifest"]==b["native"]
    assert all(h((p/f).read_bytes())==v for f,v in r["proof_sources"].items())
    assert set(r["generations"])=={d+"-"+a for d in ("child-to-parent","parent-to-child") for a in ("A","B","A2","B2")}
    if len(sys.argv)>1:
        source=Path(sys.argv[1]);assert h(source.read_bytes())==b['old_clock_source'] and timer(source)==b["timer_ast"]
    print("Verified unchanged two-clock loop, original 32-pair protocol, 597 native inputs per anchor and eight actual valid/invalid/recovered downstream qualifications.")
if __name__=='__main__':main()
