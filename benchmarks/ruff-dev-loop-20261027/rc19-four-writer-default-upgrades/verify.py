"""Check each physical upgrade, verdict, diagnostic span and supported no-op."""
import hashlib,json
from pathlib import Path

root=Path(__file__).resolve().parent
def read(s):return json.loads((root/s).read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
subjects=read("subjects.json")
new="8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5"
released="789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1"
wild="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
assert subjects["new_cargo_h4_record"]["commit"]=="8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b"
assert subjects["new_cargo_h4_record"]["binary_sha256"]==new
assert subjects["released_19"]["images"]["cargo"]==released
assert subjects["released_19"]["images"]["wild"]==wild
assert all(x["exit"]==0 and x["disk_stop"] is None and x["minimum_observed_home_free"]>45*2**30 for x in subjects["launches"].values())
assert sha(root/"reproduce/reproduce-generic.py")=="eebd066f852f85b3d7605fb6ae8f1263230b9371b949d4536fc2e83b6cb5a487"
for arm in ("sdk","sdk-on-official19"):
    rec=read(arm+".json")
    sb=subjects["inputs"][arm]
    assert sb["cargo"]==new and sb["wild"]==wild
    ch=rec["dirty_check"]
    build=rec["reverted_build"]
    for hist in [ch["unchanged_during_upgrade"],build["unchanged_during_upgrade"]]:
        assert hist["before"]["cargo"]==released and hist["after"]["cargo"]==new and hist["after"]["rustc"]==sb["rustc"] and hist["state_files"]>8
    phases=ch["phases"]
    assert phases["edited"]["success"] and phases["edited-repeat"]["success"] and len(phases["edited-repeat"]["fresh"])==4
    errnames=["edited-clean","first-after-upgrade","second-after-upgrade","independent-after-upgrade"]
    for k in errnames:
        [err]=phases[k]["errors"]
        [sp]=err["spans"]
        assert err["target"]=="client" and err["error"]=="E0034" and not phases[k]["success"] and sp["is_primary"]
        assert (sp["file_name"],sp["line_start"],sp["line_end"],sp["column_start"],sp["column_end"])==("client/src/main.rs",3,3,30,38)
        assert err==phases["edited-clean"]["errors"][0]
    assert phases["restore"]["success"] and len(phases["restore-repeat"]["fresh"])==4
    assert build["cargo_sha256"]==new and build["rustc_sha256"]==sb["rustc"]
    assert build["phases"]["forced-failure"]["exit"]==101 and build["first_success"]=="reverted" and build["phases"]["reverted"]["exit"]==0
    assert build["eligible_program"]["regular_file"] and build["value"]==1 and build["phases"]["final-program"]["files"]["stdout"]==hashlib.sha256(b"1\n").hexdigest()
    for poison,expected in [("valid",[17,17,17,29,29,101,101,17]),("malformed",[17,17,17,101,101,29,29,17])]:
        data=rec["providers"][poison]
        assert data["old"]["cargo"]["sha256"]==released and data["new"]["cargo"]["sha256"]==new and data["new"]["rustc"]["sha256"]==sb["rustc"]
        assert data["unchanged_target_and_source_snapshot"]["files"]>200 and data["restored_regular_elf"]["regular_file"]
        rows=data["rows"];assert [r["cargo"] or r["value"] for r in rows]==expected
        assert rows[0]["hash"]==rows[1]["hash"]==rows[2]["hash"] and not rows[1]["wild"] and not rows[2]["rustc"]
        for r in rows:
            if r["cargo"]:
                assert r["cargo"]==101 and r["link_error"] and r["failure_selected_earlier_native_archive"] and r["wild"]>0
            else:
                assert r["native_exit"]==0
                if r["phase"] in {"repeat-after-upgrade","repeat-opposite"}:
                    assert not r["rustc"] and not r["wild"] and r["fresh"]
    asm=rec["assembler"]
    a=asm["rows"]
    assert asm["old_cargo"]==released and asm["new_cargo"]==new and asm["new_rustc"]==sb["rustc"] and asm["snapshot"]["files"]>10
    for k,want in {"old-original":"5:17","old-edited":"9:17","old-repeat":"9:17","old-empty":"9:29","new-unchanged-after-upgrade":"9:29","new-repeat":"9:29","new-independent":"9:29","new-missing":101,"new-empty-missing":101,"new-restore":"5:17","new-restore-repeat":"5:17"}.items():
        r=a[k]; assert (r["status"] or r["value"])==want and len(r["observed_cargo_execs"])==1
        if k in ("old-repeat","new-repeat","new-restore-repeat"):
            assert r["target_fresh"] and not r["physical_rustcs"] and not r["physical_wild"]
        if k in ("new-unchanged-after-upgrade","new-independent"):
            assert ["app",False] in r["physical_rustcs"] and r["physical_wild"] and r["current_input"]==[29] and [j[0] for j in r["physical_payload_reads"]]==["present"]
        if k in ("new-missing","new-empty-missing"):
            assert r["current_input"] is None and r["missing"] and not r["physical_wild"] and [j[0] for j in r["physical_payload_reads"]]==["absent"]
    assert a["old-edited"]["sources"]==a["new-unchanged-after-upgrade"]["sources"]==a["new-independent"]["sources"] and not a["old-edited"]["physical_payload_reads"]
opt=read("explicit-optin.json")
assert opt["cargo"]==new and opt["flags"]==["-Zrelink-only=yes"] and opt["rustc"]==subjects["inputs"]["sdk"]["rustc"]
r=opt["rows"]
assert r["updated"]["current_input"]==r["independent"]["current_input"]==[29] and r["updated"]["sources"]==r["independent"]["sources"]
assert r["updated"]["value"]=="9:17" and r["independent"]["value"]=="9:29"
assert ["app",True] in r["updated"]["physical_rustcs"] and r["updated"]["physical_wild"] and not r["updated"]["physical_payload_reads"]
print("2 SDKs; identical E0034 spans; first revert 1; 4 native-provider histories; 2 repaired assembler histories; explicit stale result reproduced")
