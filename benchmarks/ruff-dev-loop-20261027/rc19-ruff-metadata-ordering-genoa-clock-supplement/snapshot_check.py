"""Unscored custody rehearsal using narrowly named, disposable snapshots."""
import json, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import R, volume, live, floors, ro, show, snapshot, save
def val(s,k):return re.search(r"^"+k+r": (\S+)$",s,re.M).group(1)
def main():
    mode=sys.argv[1]; assert mode in ("freeze","after")
    refs={};saved=volume/"admin-closed-child";orig=show(saved);assert ro(saved)
    if mode=="after":
        v=json.loads((R/"genoa-supplement-custody-demo-pre.json").read_bytes())
        assert show(saved)==v["source"] and all(not (volume/n).exists() for n in v["owned"])
        save(R/"genoa-supplement-custody-demo.json",{"source":orig,"two_visits":v["two_visits"],"free":floors(),"qualified_root_gc":True})
        return
    for arm in "AB":
        tmp=volume/("supplement-demo-v2-live-"+arm);hold=volume/("supplement-demo-v2-held-"+arm)
        assert not tmp.exists() and not hold.exists();snapshot(saved,tmp);snapshot(tmp,hold,True)
        a,b=show(tmp),show(hold);assert ro(hold) and not ro(tmp)
        assert val(a,"Parent UUID")==val(orig,"UUID") and val(b,"Parent UUID")==val(a,"UUID")
        refs[arm]={"parent":orig,"live":a,"held":b}
        subprocess.run(["btrfs","subvolume","delete","--commit-after",tmp],check=True)
        assert not tmp.exists() and ro(hold) and show(hold)==b
    assert show(saved)==orig and ro(saved)
    save(R/"genoa-supplement-custody-demo-pre.json",{"source":orig,"two_visits":refs,"owned":{"supplement-demo-v2-held-"+k:v["held"] for k,v in refs.items()},"uid":os.getuid()})
if __name__=="__main__":main()
