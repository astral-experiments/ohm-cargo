from pathlib import Path
import json,os,sys,subprocess
K=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(K/"ops"))
import enter
from common import *
def outside():
    lane="mount-only"
    st=LANES/lane;st.mkdir(parents=True)
    for sub in ["state-upper","state-work","source-upper","source-work"]:(st/sub).mkdir()
    subprocess.run(["sudo","-n","/usr/bin/unshare","--mount","--propagation","private","--","/usr/bin/python3","-IB",__file__,"mount",os.readlink("/proc/self/ns/mnt")],check=True)

def perform():
    captured=os.execv
    def call(path,args):
        assert args==["/usr/bin/python3","-IB",str(K/"ops/worker.py"),"train","parent","rehearsal","original","native","train"]
        captured(path,["/usr/bin/python3","-IB",__file__,"inside"])
    # Drive exactly the registered private-mount and real uid-drop operations,
    # changing only the final entrypoint to a read-only checker. Its canonical
    # origin remains the previously settled original target and exact selected Cargo.
    enter.os.execv=call
    # The creator's two reversible dry mounts need their own physical upper.
    os.rename(LANES/"mount-only",LANES/"train")
    try:enter.mounted("train","parent","rehearsal","original","native","train",sys.argv[2])
    finally:pass

def inside():
    env=trusted();img=enrolled("parent");proof=mount_evidence(img["cargo"],img["sha256"])
    proof["legacy_ismount"]={str(p):os.path.ismount(p) for p in [LIVE,ROOT,M/"sdk/bin/cargo"]}
    assert proof["legacy_ismount"][str(M/"sdk/bin/cargo")] is False
    prior_rows=[json.loads(l) for l in (F/"donor/H-settled/cargo.stdout").read_bytes().splitlines()]
    closure=artifacts(prior_rows)
    assert len(closure["typed_files"])==553 and len(closure["build_script_outputs"])==30
    proof["prior_closure"]=signature(closure);proof["typed_files"]=len(closure["typed_files"]);proof["build_script_dirs"]=len(closure["build_script_outputs"])
    side=prior.rawfiles(E2E);from names import own_recipe
    recipe=own_recipe(side);assert len(recipe["authentic_object_name_fields"])==139
    proof["existing_root_objects"]=len(side["objects"])
    proof["external_commands"]=0;put(K/"amendment/kernel-probe-private.json",proof)
if __name__=="__main__":
    {"outside":outside,"mount":perform,"inside":inside}[sys.argv[1]]()
