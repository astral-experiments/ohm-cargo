"""Measure only the ordinary Cargo subprocess, twice, persisting the raw brackets."""
import json,os,subprocess,sys,time
from pathlib import Path
out=Path(sys.argv[1]);assert len(sys.argv)==3 and sys.argv[2] in ('before','after');out.mkdir(exist_ok=True)
args=['cargo','+ohm','check','--locked','--offline','-p','ruff_python_trivia','--message-format=json']
assert not {'CARGO_LOG','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_BUILD_ANALYSIS_ENABLED'}&os.environ.keys()
assert sorted(os.sched_getaffinity(0))==list(range(8,16)) and os.geteuid()==1000
for phase in (('settled',) if sys.argv[2]=='before' else ('edited','repeat')):
 d=out/phase;d.mkdir()
 with (d/'stdout').open('xb')as so,(d/'stderr').open('xb') as se:
  start=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
  result=subprocess.run(args,stdout=so,stderr=se)
  end=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
 (d/'clock.json').write_text(json.dumps({'start_ns':start,'end_ns':end,'exit':result.returncode})+'\n')
 assert result.returncode==0,(phase,result.returncode)
