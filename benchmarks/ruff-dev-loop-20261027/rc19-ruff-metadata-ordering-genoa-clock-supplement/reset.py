from pathlib import Path
import re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from clock import *
n,pos=map(int,sys.argv[1:]);k,to,fr,anchor,po,qa=slot(n,pos)
clockroot=R/"genoa-supplement-scored";clockroot.mkdir(exist_ok=True)
label=f"pair-{n:02d}-visit-{pos}-{k}"
assert not (clockroot/label).exists() and not (clockroot/(label+".reset.json")).exists()
assert ro(volume/anchor)
if n==0 and pos==0:
    assert not list(clockroot.iterdir()) and live.exists()
    saved=volume/"pre-supplement-genuine-terminal";assert not saved.exists()
    live.rename(saved)
else:
    pn,pp=(n,0) if pos==1 else (n-1,1)
    pk=slot(pn,pp)[0];prev=clockroot/f"pair-{pn:02d}-visit-{pp}-{pk}"
    terminal=json.loads((prev/"terminal.json").read_bytes())
    current=show(live)
    assert (prev/"checkpoint.json").is_file()
    if pos==0:assert (clockroot/f"pair-{pn:02d}.accepted.json").is_file()
    assert terminal["ok"] and not (prev/"failure.json").exists() and not ro(live) and live.name=="stable-pgo-live" and live.parent==volume
    # A subvolume's generation changes upon remount. Compare its immutable
    # UUID and actual owning filesystem rather than its current transaction id.
    def field(s,t):return re.search(r"^\s*"+t+r":\s*(\S+)\s*$",s,re.M).group(1)
    assert field(terminal["subvol"],"UUID")==field(current,"UUID")
    uid=field(current,"Subvolume ID")
    subprocess.run(["btrfs","subvolume","delete","--commit-after",live],check=True)
    (clockroot/(label+".deleted-id")).write_text(uid+"\n")
snapshot(volume/anchor,live)
assert not ro(live) and re.search(r"^Parent UUID: (\S+)$",show(live),re.M)[1]==re.search(r"^UUID: (\S+)$",show(volume/anchor),re.M)[1]
assert show(volume/anchor)==qa["anchors"][anchor]
save(clockroot/(label+".reset.json"),{"source":anchor,"source_show":show(volume/anchor),"started":show(live),"floor":floors()})
