"""Time only the ordinary member's Cargo process inside its canonical mount namespace."""
from pathlib import Path
import json,subprocess,sys,time
out=Path(sys.argv[1]);argv=['cargo','+ohm','build','--locked','--offline','-j4']
with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
    start=time.monotonic_ns();result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=so,stderr=se);stop=time.monotonic_ns()
(out/'clock.json').write_text(json.dumps(dict(argv=argv,code=result.returncode,start=start,stop=stop,ns=stop-start))+'\n')
sys.exit(result.returncode)
