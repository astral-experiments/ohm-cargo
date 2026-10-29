from pathlib import Path
import subprocess, json, sys, os
import sys; sys.path.insert(0,str(Path(__file__).resolve().parent)); import witness_fd as w
base=w.base
if __name__=="__main__":
    for label,order in (("fd-provider-late","provider-late"),("fd-provider-first","provider-first")):
        w.fresh();w.put("provider/flag","modified\n");w.put("reader/src/lib.rs",w.reader+"// independent source edit\n")
        x=w.run(label,order,True)
        assert x["status"]==0
        w.run(label+"-first-repeat",trace=True);w.run(label+"-second-repeat",trace=True)
        w.live.rename(base/("state-"+label))
