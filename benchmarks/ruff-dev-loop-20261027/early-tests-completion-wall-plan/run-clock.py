"""Time the complete ordinary Cargo subprocess inside its prepared canonical namespace."""
from pathlib import Path
import json
import subprocess
import sys
import time

out=Path(sys.argv[1]);cmd=sys.argv[2:]
assert cmd==['cargo','+ohm','test','--no-run','--workspace','--locked','--offline','-j8']
with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
    start=time.monotonic_ns()
    proc=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
    stop=time.monotonic_ns()
(out/'clock.json').write_text(json.dumps(dict(argv=cmd,returncode=proc.returncode,start=start,stop=stop,elapsed_ns=stop-start))+'\n')
sys.exit(proc.returncode)
