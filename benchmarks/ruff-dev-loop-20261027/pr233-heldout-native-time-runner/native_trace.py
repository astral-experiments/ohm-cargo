"""Classify successful native process executions from the frozen independent process trace."""
from pathlib import Path
from config import FROZEN, need
from processes import records

def trace_summary(path,exes):
    jobs=[]; native=dict(cc=0,collect2=0,wild=0); cargo_seen=False
    for _,image,argv in records(path):
        file=Path(image)
        if file.name=='cargo' and file.is_file() and file.samefile(FROZEN/'bin/cargo'):cargo_seen=True
        need(image not in exes,('Cargo executed a test or other target',image))
        if file.name=='rustc':
            crate=argv[argv.index('--crate-name')+1] if '--crate-name' in argv else None
            need(not any('crate-hash' in t or 'crate_hash' in t for t in argv),('standalone hash',argv[:6]))
            if crate and crate not in ('___','__') and '--print=file-names' not in argv:
                need(not any('ohm-checked-mixed-rlink=' in t for t in argv),'private experimental flags')
                jobs.append([crate,'link-only' if any(t in ('-Zlink-only','link-only') for t in argv) else 'full'])
        if file.name=='ld.bfd' and file.parent.name=='wild-ld':native['wild']+=1
        if file.name=='collect2':native['collect2']+=1
        if file.name in ('cc','gcc','x86_64-linux-gnu-gcc','x86_64-linux-gnu-gcc-13','gcc-13'):native['cc']+=1
    need(cargo_seen,'no exec of selected Cargo')
    return {'jobs':sorted(jobs),'native':native}

