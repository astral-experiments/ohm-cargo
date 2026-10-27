"""Time one real Cargo process inside its assigned namespace and CPU set."""
from pathlib import Path
import json,os,subprocess,sys,time
path=Path(sys.argv[1]);assert not path.exists() and set(os.sched_getaffinity(0))=={8,9,10,11}
start=time.monotonic_ns();cp=subprocess.run(sys.argv[2:],stdin=subprocess.DEVNULL,capture_output=True);elapsed=time.monotonic_ns()-start
path.write_text(str(elapsed)+'\n');sys.stdout.buffer.write(cp.stdout);sys.stderr.buffer.write(cp.stderr);sys.exit(cp.returncode)
