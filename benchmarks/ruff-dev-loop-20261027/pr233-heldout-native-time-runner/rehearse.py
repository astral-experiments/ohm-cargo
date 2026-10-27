"""Check the timing runner on preserved, traced native outputs without launching Cargo or rustc."""
from pathlib import Path
import json, os, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import BOUND, FROZEN, SONAME, ORIGIN, QUAL, PLAN, PLAN_SHA, RUFF, SOURCE, expected, load, need
from native_trace import trace_summary
from products import inputs_elf_key, oracle
from h5paths import release_output_roster
from witness import audit_json, as_digest
from novel_state import verify_view
arm,=sys.argv[1:]
need(arm in 'BC' and sorted(os.sched_getaffinity(0))==[29], 'separate operator CPU')
verify_view('original',ORIGIN/'fixture')
need(Path(BOUND['arms'][arm]['driver']).samefile(FROZEN/'lib'/SONAME) and Path(BOUND['arms'][arm]['cargo']).samefile(FROZEN/'bin/cargo'),'subjects')
out={}
for n in ['original-baseline',*[e+'-'+d for e in SOURCE['schedule'] for d in ('edit','restore')]]:
    d=ORIGIN/'receipts/build'/arm/n
    ref=expected('build',arm,n);j=audit_json(d/'stdout','build');rows=[json.loads(x) for x in (d/'stdout').read_bytes().splitlines()]
    rv=release_output_roster(rows,arm);need(rv==ref['release_roster'] and j['roster_sha256']==ref['roster'] and j['dirty']==ref['dirty'] and j['message_sha256']==ref['messages'] and sorted(inputs_elf_key(p) for p in j['elf'])==ref['elf'] and len(j['executables'])==ref['exes'],('roster/diagnostics',arm,n))
    actual=trace_summary(d,j['executables']);need(actual==ref['native'],('parsed concrete processes',arm,n))
    immediate=trace_summary(d.with_name(n+'-fresh'),j['executables']);need(not immediate['jobs'] and not any(immediate['native'].values()),('fresh extra job',arm,n))
    out[n]=dict(reference=ref['original_receipt'],native=actual,immediate=immediate,release_roster=rv,dirty=ref['dirty'])
print(json.dumps({'arm':arm,'checked':out,'plan':PLAN_SHA,'timed_commands':0,'new_cargo_commands':0},sort_keys=True))
