"""Verify each frozen visit away from both Cargo clocks; leave raw files untouched."""
from pathlib import Path
import json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import *
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_generation import measure_generation, get
N=R/"genoa-supplement-scored"
def show_value(s,k):return re.search(r"^"+k+r": (\S+)$",s,re.M).group(1)
def main():
    mode,case=sys.argv[1:];qa=get(R/"genoa-supplement-admission.json")
    target=R/"genoa-supplement-proof-rehearsal" if mode=="rehearse" else R/"genoa-supplement-proof-objects"
    target.mkdir(exist_ok=True);raw=target/"raw-objects";require_admin_namespace();assert os.statvfs(live).f_flag & os.ST_RDONLY
    if mode=="score":assert ro(live)
    if mode=="rehearse":
        actual=site/case;d=target/case;reported=get(actual/"terminal.json");dr=reported["phase"];rev=reported['source'];f=actual/"repeat2/cargo.stdout"
        row=get(R/"same-donor-actual-products/replicated/receipt.json")["ordered"][case]
        assert show_value(show(live),"UUID")==row["reset_uuid"];assert reported["checks"]["repeat2"]["rows"]["source"]==rev
    else:
        assert mode=="score" and re.fullmatch(r"pair-[0-9]{2}-visit-[01]-[AB]",case)
        actual=N/case;t=get(actual/"terminal.json");m=get(actual/"checkpoint.json")
        assert t["ok"] and not (actual/"failure.json").exists() and m["held_info"]==show(live)
        assert show_value(m["held_info"],"Parent UUID")==show_value(t["subvol"],"UUID")
        d=actual/"post-pair";dr=t["direction"];rev=t["source"];f=actual/"repeat.jsonl"
    try:
        measure_generation(d,dr,qa,rev,raw,f)
    except BaseException as e:
        if d.is_dir() and not (d/'failure.json').exists():save(d/'failure.json',{"error":repr(e),"case":case,"mode":mode})
        raise
if __name__=="__main__":main()
