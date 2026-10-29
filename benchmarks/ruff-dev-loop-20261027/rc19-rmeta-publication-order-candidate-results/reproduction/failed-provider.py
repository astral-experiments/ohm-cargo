from pathlib import Path
import os,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import witness_commit as w
root=w.base;arm=sys.argv[1];image=Path(sys.argv[2]).resolve();assert w.sha(image)==sys.argv[3]
original=w.cargo_image;w.cargo_image=image
link=w.sdk/"bin/cargo";assert link.resolve()==original.resolve();temp=link.parent/"cargo-failure-only"
temp.symlink_to(image);temp.replace(link)
try:
    w.base=root/("provider-failure-"+arm)
    w.base.mkdir();(w.base/"receipts").mkdir()
    w.seed=root/("binding-"+arm)/"trained-seed"
    w.fresh()
    w.put("provider/src/lib.rs",'pub fn value() -> u8 { "invalid provider" }\n')
    for n in ('broken','broken-repeat','broken-empty'):
        if n=='broken-empty':
            for k in ('target','shared'):
                p=w.live/k
                if p.exists():p.rename(w.live/(k+'-before-empty'))
        rec=w.run(n,trace=True);assert rec['status']==101
        assert any(x[0]=='provider' and x[1] and x[1]['code']=='E0308' for x in rec['diagnostics'])
    for k in ('target','shared'):
        p=w.live/k
        if p.exists():p.rename(w.live/(k+'-fresh-oracle'))
        old=w.live/(k+'-before-empty')
        if old.exists():old.rename(p)
    w.put("provider/src/lib.rs",w.provider)
    for n in ('repaired','repaired-repeat','repaired-empty'):
        if n=='repaired-empty':
            for k in ('target','shared'):
                p=w.live/k
                if p.exists():p.rename(w.live/(k+'-before-clean-repair'))
        rec=w.run(n,trace=True);assert rec['status']==0
    w.live.rename(w.base/'preserved-state')
finally:
    temp.symlink_to(original);temp.replace(link)
