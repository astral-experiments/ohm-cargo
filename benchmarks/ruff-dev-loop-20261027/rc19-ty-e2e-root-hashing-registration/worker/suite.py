"""Run independent original, changed, error, restored, and two types of clean controls without scoring."""
import argparse
import gzip
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from cold import escrow
from enter import launch

def do(lane,arm,phases):
    for phase,mode,method,kind in phases:
        launch(lane,arm,phase,mode,method,kind)
        print("terminal",lane,phase,flush=True)
def receipt(lane,visit):return get(REPORTS/lane/visit/"result.json")
def bind_donor():
    result=receipt("train","settled")
    assert result["units"]==result["fresh"]==300 and result["e2e"]["sha256"]==get(REF)["product"]["sha256"]
    assert get(REPORTS/"train/settled/launches.json")=={"full":[],"cached":[],"wild_total":0,"root_native":{"stock-wild":0,"gcc":0,"collect2":0}}
    put(K/"binding/donor.json",{"source":"original","units":300,"dependencies":result["dependencies"],"typed":result["typed"],"result":rawsha(REPORTS/"train/settled/result.json"),
        "prior_parent_overlay":rawsha(F/"donor/terminal.json"),"prior_parent_lower_dev_ino":[(M/"states/parent-warm/target").stat().st_dev,(M/"states/parent-warm/target").stat().st_ino]})
def aggregate():
    source=get(K/"binding/donor.json");result={};cold={}
    diag={}
    for lane,phase in [("train","settled"),("cold-parent","edited-cold"),("cold-child","edited-cold")]:
        p=REPORTS/lane/phase
        with gzip.open(p/"whole-dependency-diagnostics.json.gz") as f:diag[lane]=json.load(f)
        cold[lane]=get(p/"dependencies.json")
    diffs={}
    for l,r in [("train","cold-parent"),("train","cold-child"),("cold-parent","cold-child")]:
        a=cold[l];b=cold[r];assert a["typed_files"].keys()==b["typed_files"].keys()
        unequal={k:[v,b["typed_files"][k]] for k,v in a["typed_files"].items() if v!=b["typed_files"][k]}
        ardiff={}
        for k in (q for q in unequal if q.endswith(".rlib")):
            ac=diag[l]["archives"][k];bc=diag[r]["archives"][k]
            ardiff[k]={"left_raw":ac["literal"],"right_raw":bc["literal"],"proven_only_name_fields":ac["only_observed_names_masked"]==bc["only_observed_names_masked"],
                       "fields":[ac["accepted_name_field_count"],bc["accepted_name_field_count"]]}
        crdiff={k:[v,diag[r]["metadata"][k]]for k,v in diag[l]["metadata"].items() if v!=diag[r]["metadata"][k]}
        scripts={k:[v,b["build_script_outputs"].get(k)] for k,v in a["build_script_outputs"].items() if v!=b["build_script_outputs"].get(k)}
        assert a["build_script_outputs"].keys()==b["build_script_outputs"].keys()
        diffs[l+"__"+r]={"different_typed":unequal,"ar":ardiff,"credentials":crdiff,"different_build_scripts":scripts}
    put(K/"binding/cold-comparison.json",diffs)
    same=diffs["cold-parent__cold-child"]
    unknown=[x for x in same["different_typed"] if not x.endswith(".rlib") or not same["ar"][x]["proven_only_name_fields"]]
    # Registered cold symmetry rule does not infer harmlessness from a final executable alone.
    assert not unknown and not same["different_build_scripts"],("independent-cold difference requires attribution",unknown,list(same["different_build_scripts"]))
    for who in ["parent","child"]:
        dd=REPORTS/("warm-"+who)
        for mode,label in [("original","restore"),("edited","edit")]:
            obs=get(dd/label/"result.json");leaf=REPORTS/("leaf-"+who+"-"+mode)/"root-empty"
            selected=get(leaf/"result.json");target=obs["e2e"]
            assert selected["e2e"]==target and selected["dependencies"]==source["dependencies"]==obs["dependencies"]
            if mode=="edited":assert receipt("cold-"+who,"edited-cold")["e2e"]==target
            assert result.setdefault(mode,target)==target
            assert get(dd/label/"native-descriptor.json")==get(leaf/"native-descriptor.json"),(who,mode,"root-empty native debug")
            recipe=get(dd/label/"root-current-recipe.json");empty=get(leaf/"root-current-recipe.json")
            assert (recipe["objects"],recipe["exact_except_verified_names"])==(empty["objects"],empty["exact_except_verified_names"]),(who,mode,"root-empty raw recipe beyond name proof")
    assert result["original"]!=result["edited"]
    for phase in ["edit","restore","recovery"]:
        a=REPORTS/"warm-parent"/phase;b=REPORTS/"warm-child"/phase
        assert get(a/"native-descriptor.json")==get(b/"native-descriptor.json"),phase
        x=get(a/"root-current-recipe.json");y=get(b/"root-current-recipe.json")
        assert x["exact_except_verified_names"]==y["exact_except_verified_names"] and x["objects"]==y["objects"],phase
    put(K/"binding/native-core.json",{"elf":result,"cold_difference":rawsha(K/"binding/cold-comparison.json"),"donor":rawsha(K/"binding/donor.json"),"cross_generation_mixed":False})

def stage(which):
    assert get(K/"binding/native-go.json")["plan"]==rawsha(K/"registration/SHA256SUMS")
    if which=="train":
        do("train","parent",[("train","original","native","train"),("settled","original","native","settled")]);bind_donor();return
    for role in ["parent","child"]:
        if which=="cold-"+role:
            do(which,role,[("edited-cold","edited","native","cold")]);escrow(which);return
        if which=="warm-"+role:
            do(which,role,[("incoming","original","native","settled"),("edit","edited","native","dirty"),("repeat","edited","native","settled"),
                           ("invalid","invalid","native","dirty"),("recovery","edited","native","dirty"),("restore","original","native","dirty"),("restored-repeat","original","native","settled")])
            return
        if which=="leaf-"+role:
            for mode in ["original","edited"]:
                do(which+"-"+mode,role,[("root-empty",mode,"native","leaf")])
            return
    assert which=="core"
    aggregate()

if __name__=="__main__":
    stage(sys.argv[1])
