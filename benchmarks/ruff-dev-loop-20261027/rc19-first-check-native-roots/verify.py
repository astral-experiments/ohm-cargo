"""Check all ten unchanged native rosters, reported dirty roots and both real edits."""
from collections import Counter
from pathlib import Path
import json


def targets(case):
    return set(x["output"] for x in case["wild_outputs"])


def jobs(case):
    return {(x["crate"],x["mode"],x["stem"],x["test"]) for x in case["rustcs"]}


def main():
    data=json.loads((Path(__file__).resolve().parent/"native.json").read_bytes())
    native_builds={"ty","ty_completion_bench","ty_completion_eval","ruff_dev","libty_wasm.so"}
    for mode in ("build","test"):
        study=data[mode]
        assert set(study)=={"unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2","child-edit","child-unchanged-1","child-unchanged-2"}
        for direction in ("parent","child"):
            edit=study[direction+"-edit"];first=study[direction+"-unchanged-1"];nextone=study[direction+"-unchanged-2"]
            assert jobs(first)==jobs(nextone) and targets(first)==targets(nextone)
            assert all(x["all_physical_processes_succeeded"] for x in (first,nextone,edit))
            assert len(first["wild_outputs"])==len(targets(first))
            edited_count={"build":47,"test":132 if direction=="parent" else 119}[mode]
            assert edit["cargo_roles"]["rustc-full"]==edited_count
            for case in (first,nextone,study["unchanged-before"]):
                verify_case(mode,case,native_builds)
            if mode=="build":
                assert targets(first)==native_builds and jobs(study["unchanged-before"])==jobs(first)
            elif direction=="parent":
                assert targets(first)-targets(study["child-unchanged-1"])=={"ty_wasm-6100218063986ea3"}
                assert targets(study["child-unchanged-1"])<targets(first)
            else:
                assert targets(first)==targets(study["unchanged-before"])
    print("14 command records checked. All ten unchanged native states have only the ty_python_semantic foreign-span sentinel(s) and dependent dirty reasons. 5 build and 18/19 test linker outputs, with unchanged first/second rosters.")


def verify_case(mode,case,native_builds):
    assert case["all_physical_processes_succeeded"] and case["newer_dependency_log_mentions"]==0
    typed=case["typed_known_units"]
    assert all(typed[n] and all(typed[n]) for n in ("ruff_python_ast","ruff_python_index"))
    assert typed["ron"]==([] if mode=="build" else [True])
    cats=case["dirty_categories"]
    assert set(cats)=={"MissingForeignSpanSentinel","StaleDepFingerprint"}
    assert sum(cats.values())==case["typed"]["total"]-case["typed"]["fresh"]
    roots=[r for r in case["dirty_rows"] if r["kind"]=="MissingForeignSpanSentinel"]
    assert all(r["package"]==r["target"]=="ty_python_semantic" for r in roots)
    stems=({"f0838d7cb39b023c"} if mode=="build" else {"4987c8ded2339593","105e97d570d35e4b"})
    assert {r["sentinel"] for r in roots}=={"ty_python_semantic-"+s+".d/ohm-foreign-span-bytes" for s in stems}
    full=[x for x in case["rustcs"] if x["mode"]=="rustc-full"]
    if mode=="build":
        assert {r["crate"] for r in full}=={"ty_python_semantic","ty_wasm"}
        assert targets(case)==native_builds
    else:
        assert Counter(r["crate"] for r in full)=={"ty_python_semantic":2,"ty_wasm":1,"api":1}
        assert next(r["src"] for r in full if r["crate"]=="api")=="crates/ty_wasm/tests/api.rs"
    assert next(x["types"] for x in full if x["crate"]=="ty_wasm")==["cdylib","rlib"]
    roles=case["cargo_roles"]
    assert roles["stock-wild"]==roles["gcc"]==roles["collect2"]==len(full)-1+roles["rustc-link-only"]
    assert not any(x["crate"] in {"ruff_python_ast","ruff_python_index","ron"} for x in case["rustcs"])


if __name__=="__main__":
    main()
