"""Project the verified conventional metadata lookup from both released compiler histories."""
from pathlib import Path
import hashlib, json, os, socket
x=Path.home()/'.cache/ohm-233-position-qualified-20261027'
out=x/'pr233-h5-ordinary-readers-build-v4';state=x/'first-occurrence-classic-pr233-h5-v2'
snap=x/'pr233-h5-private-parser-witness-v2';prev=x/'pr233-h5-ordinary-readers-build-v1'
assert socket.gethostname()=='charlie-ohm-loader-perf-1024'
os.sched_setaffinity(0,{29})
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_bytes())
complete=load(out/'complete.json');assert complete['observations']==sha(out/'observations.json')
data={'verified_lookup':{},'legacy_unrestricted_lookup':{},'complete':complete,'native_parser_inputs':{},'source_scripts':{n:(out/n).read_text() for n in ['bridge.rs','caller.rs']}}
for arm,rows in load(out/'observations.json').items():
    results=[];data['verified_lookup'][arm]=results
    inputs={}
    for tag,phase in [('cold','original-baseline'),('restored','lexer-pending-indentation-restore')]:
        f=snap/'build'/arm/phase/'record.json';r=load(f);m=f.parent/r['parser_rmeta_file'];assert sha(m)==r['rmeta_sha256']
        inputs[tag]=dict(history=phase,record_sha256=sha(f),source_inputs=r['source_inputs'],metadata=r['rmeta_sha256'],logical=r['logical_reported_path'],physical=str(m),actual_driver=r['actual_driver'])
    assert inputs['cold']['source_inputs']==inputs['restored']['source_inputs'] and inputs['cold']['metadata']!=inputs['restored']['metadata']
    data['native_parser_inputs'][arm]=inputs
    for row in rows:
        action,a,b=(row[k] for k in ['action','producer','loaded_parser']);leaf=out/arm/(action+'-'+a+'-'+b)
        assert row==load(leaf/'receipt.json')
        assert sha(leaf/'opens')==row['lookup_open_trace_sha256'] and sha(leaf/'stderr.jsonl')==row['raw_diagnostics_sha256']
        obs={k:v for k,v in row.items() if k!='compiler_argv'}
        obs.update(compiler_argv=row['compiler_argv'],successful_open_lines=[v for v in (leaf/'opens').read_text().splitlines() if any('"'+name+'"' in v for name in row['actual_successful_parser_opens'])],stderr_jsonl=(leaf/'stderr.jsonl').read_text())
        assert set(row['actual_successful_parser_opens']) <= {inputs[b]['logical'],inputs[b]['physical']} and row['parser_rmeta']==inputs[b]['metadata']
        results.append(obs)
    data['legacy_unrestricted_lookup'][arm]=[{k:r[k] for k in ('action','producer','loaded_parser','status','diagnostic_codes','output_sha256')} for r in load(prev/'observations.json')[arm]]
print(json.dumps(data,sort_keys=True))
