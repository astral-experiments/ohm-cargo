"""Time only the ordinary cargo +ohm process inside its fixed namespace."""
from pathlib import Path
import os,subprocess,sys,time
dest=Path(sys.argv[1]);assert not dest.exists() and os.sched_getaffinity(0)==set(range(16))
start=time.monotonic_ns();ret=subprocess.run(sys.argv[2:],stdin=subprocess.DEVNULL).returncode;ns=time.monotonic_ns()-start
dest.write_text(str(ns)+'\n');raise SystemExit(ret)
