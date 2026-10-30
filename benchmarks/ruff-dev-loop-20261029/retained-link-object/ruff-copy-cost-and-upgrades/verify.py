"""Verify the published release, header and physical object-copy observations."""
from pathlib import Path
import argparse,copy,hashlib,json
HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/name).read_bytes())
def ok(x,msg):
    if not x:raise ValueError(msg)
def check(r,up,h):
    states=r["phases"];ok(set(states)=={"W","E"} and r["test_inventory_size"]==130,"Ruff census")
    names={"cold-original","historical-edit","unchanged-original","unchanged-edit","independent-empty-edited","invalid","repair","restore-original"}
    for arm in ("W","E"):ok(set(states[arm])==names,"8 native phases")
    for n in names:
        w,e=states["W"][n],states["E"][n]
        for k in ("ELF","status","tests","stock_wild","link_only","count_by_link_direction"):
            ok(w[k]==e[k],(n,k))
        ok(w["copied_files"]==w["actual_publish_renames"]==0 and not w["copied_bytes_by_link_direction"],"parent has no detach copy")
        count=e["count_by_link_direction"]
        want=({"new":256} if n in ("cold-original","independent-empty-edited") else {"new":6,"restored":250} if n in ("historical-edit","restore-original") else {} if n=="invalid" else {"restored":256})
        ok(count==want and e["copied_files"]==e["actual_publish_renames"]==sum(count.values()),(n,"one real copy/rename per real linked object"))
        intended=0 if n=="invalid" else 19484840 if n in ("cold-original","unchanged-original","restore-original") else 19484400
        ok(sum(e["copied_bytes_by_link_direction"].values())==intended,"kernel byte sum")
        if n.startswith("unchanged"):
            ok(e["matched_selected_prestat"]==e["matched_selected_presize"]==256
               and e["preexisting_complete_same_path"]==0 and e["pre"]["nlink1"]==e["post"]["nlink1"]==257
               and e["pre"]["nonce"]!=e["post"]["nonce"],"disjoint physical retained names")
    for a in states.values():
        ok(a["historical-edit"]["ELF"]==a["unchanged-edit"]["ELF"]==a["repair"]["ELF"]==a["independent-empty-edited"]["ELF"],"edited vs independent empty")
        ok(a["cold-original"]["ELF"]==a["unchanged-original"]["ELF"]==a["restore-original"]["ELF"]!=a["historical-edit"]["ELF"],"original vs restore")
        ok(a["cold-original"]["tests"]==[101,0,0] and a["historical-edit"]["tests"]==[0,0,0] and a["invalid"]["status"]==101,"real tests")
    ok(all(x["errno"]==95 for x in r["stock_reflink_probe"]["tests"].values()),"separate ext4 probe")
    ok(len(up)==6,"all original upgrade layouts")
    for arm in ("O","K"):
        x=up[arm+" same-stamp environment-selected build dir"]
        ph=x["phases"]
        ok(ph["W-unchanged-poisoned"]["value"]=="29 11" and ph["W-unchanged-poisoned"]["full"]==0,"retained stale baseline")
        ok(ph["E-first-unchanged-old-poison"]["elf"]==ph["E-independent-empty11"]["elf"] and ph["E-first-unchanged-old-poison"]["value"]=="17 11","environment switch")
        ok(ph["E-first-dirty-dep13"]["elf"]==ph["E-independent-empty13"]["elf"] and ph["E-second-dep13"]["full"]==0,"genuine edit and fresh repeat")
        ok(len(x["malformed_valid_and_rename"])==4 and all(v["dirty_equals_empty"]and v["repeat_equals_empty"]for v in x["malformed_valid_and_rename"].values()),"malformed/valid and in-place/rename")
        x=up[arm+" same-stamp config-selected build dir"]
        ok(x["first"]["value"]=="29 11" and x["first"]["full"]==x["first"]["wild"]==0 and not x["first_equals_empty"],"true fresh wrong incumbent")
        ok(x["dirty"]["value"]==x["second"]["value"]=="17 13" and x["dirty_equals_empty"]and x["second_equals_empty"],"config dirty recovery")
    for mode in ("config","env"):
        x=up["complete signed -19 to E/O "+mode]
        ok(x["old_driver"]!=x["new_driver"] and x["old_cargo"]!=x["new_cargo"] and x["genuine_vV_changed"],"complete release upgrade")
        ok(x["wrong_on_old"]=="29 11" and x["first"]["value"]=="17 11" and x["first"]["full"]==2 and x["first"]["wild"]==1 and x["first_equals_empty"],"signed first unchanged")
        ok(x["dirty"]["value"]==x["second"]["value"]=="17 13" and x["second"]["full"]==x["second"]["wild"]==0 and x["dirty_equals_empty"]and x["second_equals_empty"],"signed next source")
    for k in ("W-E","E-W"):
        s=h[k]["phases"];old,new=(7,8)if k=="W-E"else(8,7)
        ok(len(s)==10 and s["switch-unchanged"]["full"]==s["switch-unchanged"]["stock_wild"]==0,"true fresh first switch")
        z=s["switch-dirty"];ok(z["full"]==z["stock_wild"]==1 and z["value"]=="29" and z["elf"]==s["independent-empty29"]["elf"],"real dirty migration")
        ok(all(v[0]==new for v in z["new_headers"]) and set((x["file"],x["header"])for x in z["opened_old"])>={("work-products.bin",old),("dep-graph.bin",old)},"actual prior header open and new header")
        ok(s["switch-invalid"]["status"]==101 and s["switch-invalid"]["stock_wild"]==0 and s["switch-repaired"]["elf"]==s["independent-empty17"]["elf"],"invalid and first restore")
    return True
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--self-test",action="store_true");args=p.parse_args()
    sums=(HERE/"SHA256SUMS").read_text().splitlines()
    for line in sums:
        sha,n=line.split("  ",1);ok(not Path(n).is_absolute() and ".."not in Path(n).parts,"relative path")
        ok(hashlib.sha256((HERE/n).read_bytes()).hexdigest()==sha,n)
    a,u,h=read("ruff-kernel-copy.json"),read("upgrade-controls.json"),read("direct-format-headers.json")
    check(a,u,h)
    if args.self_test:
        for i in range(6):
            a1,u1,h1=map(copy.deepcopy,(a,u,h))
            if i==0:a1["phases"]["E"]["historical-edit"]["actual_publish_renames"]-=1
            if i==1:a1["phases"]["E"]["unchanged-edit"]["preexisting_complete_same_path"]=1
            if i==2:a1["phases"]["E"]["unchanged-edit"]["copied_bytes_by_link_direction"]["restored"]-=1
            if i==3:u1["O same-stamp config-selected build dir"]["first"]["value"]="17 11"
            if i==4:u1["complete signed -19 to E/O config"]["first"]["full"]=0
            if i==5:h1["W-E"]["phases"]["switch-dirty"]["opened_old"]=[]
            try:check(a1,u1,h1)
            except ValueError:continue
            raise ValueError("corruption passed: "+str(i))
    print("16 Ruff Cargo phases, 6 upgrade controls and 20 format-transition commands verified.")
    if args.self_test:print("Six corrupted evidence controls were rejected.")
if __name__=="__main__":main()
