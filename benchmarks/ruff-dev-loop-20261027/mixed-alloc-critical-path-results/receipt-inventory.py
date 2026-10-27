"""Hash the diagnostic source/seed and execution records; retain path-sensitive command bytes privately."""
import hashlib,json,os,socket
from pathlib import Path
from collections import Counter
assert socket.gethostname()=='charlie-ohm-trait-perf-1024'
x=Path.home()/'.cache/ohm-233-position-qualified-20261027'
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def j(p):return json.loads(p.read_bytes())
def portableids(obj):
    dat=json.dumps(obj,sort_keys=True,separators=(',',':')).encode();return hashlib.sha256(dat).hexdigest()
def one(d):
    common=[p for p in d.iterdir() if p.is_file() and p.name in ('binding.json','complete.json','failure.txt','B-seed-sha.json','C-seed-sha.json','run.out','run.err','run-v3.out','run-v3.err','incremental-move.json')]
    table={'source_files':{p.name:h(p) for p in (d/'code').glob('*.py')},'root_files':{p.name:h(p) for p in common},'complete':j(d/'complete.json') if (d/'complete.json').exists() else None,'armed':j(d/'binding.json') if (d/'binding.json').exists() else None,'seed_counts':{p.name:len(j(p)) for p in common if 'seed-sha' in p.name},'probes':{}}
    for wd in sorted(d.iterdir()):
        if not wd.is_dir() or not (wd/'command.json').is_file():continue
        cmd=j(wd/'command.json');fin=d/'receipts/build'/cmd['arm']/(cmd['probe']+'-'+cmd['direction']+'-fresh')/'receipt.json'
        docs=[p for p in wd.iterdir() if p.is_file() and p.name in ('samples.jsonl.gz','cargo-tasks.jsonl.gz','sampled-processes.json','stdout','stderr','stdout.clock.jsonl','stderr.clock.jsonl','command.json','receipts.json','output-comparison.json','typed.json')]
        row={'files':{p.name:{'bytes':p.stat().st_size,'sha256':h(p)} for p in docs},'status':cmd['rr'],'cargo':cmd['cargo_sha256'],'driver':cmd['driver_sha256'],'reported_units':j(wd/'receipts.json')['units'],'fresh':None,'comparison':j(wd/'output-comparison.json') if (wd/'output-comparison.json').is_file() else None}
        if fin.is_file():
            g=j(fin);prod=g['product']
            row['fresh']={'receipt_sha256':h(fin),'units':g['unit_count'],'fresh':g['fresh_units'],'jobs':len(g['processes']['jobs']),'wild':len(g['processes']['native']['wild']),'structural_roster':prod['structural_roster'],'diagnostics_fingerprint':portableids(prod['diagnostics']),'messages_fingerprint':portableids(prod['messages']),'elf_files':len(prod['elf']),'elf_identity_receipt':portableids(prod['elf']),'reader_count':len(prod.get('readers',[]))}
        table['probes'][wd.name]=row
    return table
dirs=['mixed-critical-path-v2','mixed-critical-light-v1','mixed-critical-workers-v1','mixed-critical-workers-v2']
d={s:one(x/s) for s in dirs if (x/s/'binding.json').exists()}
print(json.dumps(d,sort_keys=True))
