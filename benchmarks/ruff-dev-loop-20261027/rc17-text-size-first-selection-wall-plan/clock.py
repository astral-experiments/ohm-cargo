"""The only interval includes Cargo's CLI subprocess, from its launch until it exits."""
import json
from pathlib import Path
import subprocess
import sys
import time

out=Path(sys.argv[1]); command=sys.argv[2:]
assert command==['cargo','+ohm','test','-p','ruff_text_size','--no-run','--locked','--offline','-j8']
with (out/'stdout').open('xb') as so, (out/'stderr').open('xb') as se:
    start=time.perf_counter_ns()
    child=subprocess.run(command,stdout=so,stderr=se,stdin=subprocess.DEVNULL)
    stop=time.perf_counter_ns()
with (out/'clock.json').open('x') as f:
    json.dump(dict(command=command,exit=child.returncode,start=start,stop=stop,elapsed_ns=stop-start),f,sort_keys=True)
    f.write('\n')
sys.exit(child.returncode)
