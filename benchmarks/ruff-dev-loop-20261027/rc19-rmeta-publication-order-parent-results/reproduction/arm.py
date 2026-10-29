from pathlib import Path
import sys, os, subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
import witness_commit as w

arm=sys.argv[1]
image=Path(sys.argv[2]).resolve()
expected=sys.argv[3]
assert w.sha(image)==expected and arm in ("parent","candidate")
# All prior qualification receipts, SDK files, and original seed remain immutable.
# This is the exclusive private symlink for this fixture alone, never a shared SDK.
original=w.cargo_image; w.cargo_image=image
link=w.sdk/"bin/cargo"
assert link.is_symlink() and link.resolve()==original.resolve(),link
candidate=link.parent/"cargo-private-next"
assert not candidate.exists()
candidate.symlink_to(image);os.replace(candidate,link)
try:
    root=w.base
    w.base=root/("binding-"+arm)
    w.base.mkdir();(w.base/"receipts").mkdir()
    assert not w.live.exists();w.fresh()
    # If the private image uses a new Cargo namespace, independently train it at the true
    # canonical source paths; importantly we retain both first warm transition and ready seed.
    if arm=="candidate":
        initial=w.run("prior-complete-state",trace=True); assert initial["status"]==0
        settled=w.run("prior-complete-state-repeat",trace=True);assert settled["status"]==0
    current=w.base/"trained-seed"
    w.live.rename(current);w.seed=current
    for label,order in (("plain","none"),("provider-first","provider-first"),("provider-late","provider-late")):
        w.fresh();w.put("provider/flag","modified\n");w.put("reader/src/lib.rs",w.reader+"// independent source edit\n")
        first=w.run(label,order,True);assert first["status"]==0
        if order!="none":
            assert any(l.startswith("hold-fd") for l in first["order"]) and any(l.startswith("release-fd") for l in first["order"])
            assert not any("timeout" in l for l in first["order"])
        w.run(label+"-first-repeat",trace=True);w.run(label+"-second-repeat",trace=True)
        w.live.rename(w.base/("state-"+label))
    if arm=="candidate":
        w.fresh();w.put("provider/src/lib.rs","pub fn value() -> bool { true }\n")
        assert w.run("api-incompatible",trace=True)["status"]==101
        for n in ("target","shared"):
            p=w.live/n
            if p.exists():p.rename(w.live/(n+"-preserved"))
        assert w.run("api-incompatible-empty",trace=True)["status"]==101
        w.live.rename(w.base/"state-api");w.fresh()
        r=w.relevant();Path(r["reader"]["path"]).unlink()
        assert w.run("missing-existing-output",trace=True)["status"]==0
        w.live.rename(w.base/"state-missing")
finally:
    original_link=link.parent/"cargo-private-original";assert not original_link.exists()
    original_link.symlink_to(original);os.replace(original_link,link);assert link.resolve()==original.resolve()
