#!/usr/bin/env python3
"""Exercise the blocking timer independently of Cargo and all scored observations."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

p=Path(__file__).with_name("measure.py")
s=importlib.util.spec_from_file_location("measure",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
CHILD="""import resource,subprocess,sys,time
begin=time.monotonic_ns()
subprocess.run([sys.executable,'-IB','-c','import time;t=time.process_time()+0.035\\nwhile time.process_time()<t:pass'],check=True)
time.sleep(float(sys.argv[1]))
end=time.monotonic_ns();u=resource.getrusage(resource.RUSAGE_CHILDREN);print(end-begin,round((u.ru_utime+u.ru_stime)*1e6));print('actual standard error',file=sys.stderr)
"""
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("working_filesystem",type=Path);ap.add_argument("receipt_filesystem",type=Path)
    args=ap.parse_args();results=[]
    if args.working_filesystem.stat().st_dev==args.receipt_filesystem.stat().st_dev:raise ValueError("two distinct devices are required")
    if min(shutil.disk_usage(p).free for p in (args.working_filesystem,args.receipt_filesystem))<2**20:raise ValueError("timer calibration needs one free MiB on each actual physical device")
    with tempfile.TemporaryDirectory(dir=args.working_filesystem) as w,tempfile.TemporaryDirectory(dir=args.receipt_filesystem) as r:
        work=Path(w);rec=Path(r);original=m.CARGO
        try:
            for i,delay in enumerate((0.013,0.037,0.071,0.013,0.037,0.071)):
                out=rec/str(i);out.mkdir();m.CARGO=[sys.executable,"-IB","-c",CHILD,str(delay)]
                got=m.ordinary_cargo(work,dict(os.environ),work,out)
                nested_ns,nested_cpu_us=map(int,(out/"cargo.stdout").read_text().split())
                assert (out/"cargo.stderr").read_text()=="actual standard error\n"
                cpu=got["user_cpu_us"]+got["system_cpu_us"]
                assert got["exit"]==0 and got["blocking_wait"]=="wait4" and got["wall_ns"]>=nested_ns>=delay*1e9 and cpu>=nested_cpu_us>=35000
                assert got["stdout_and_stderr"][0]["size"]==(out/"cargo.stdout").stat().st_size
                results.append(dict(requested_sleep_ns=round(delay*1e9),wall_ns=got["wall_ns"],child_internal_ns=nested_ns,
                                    cpu_us=cpu,known_grandchild_cpu_us=nested_cpu_us))
        finally:m.CARGO=original
    assert len({v["wall_ns"]//1000000 for v in results})>=3
    print(json.dumps({"six_independent_timer_probes":results,"contributes_scored_samples":0},sort_keys=True))
if __name__=="__main__":main()
