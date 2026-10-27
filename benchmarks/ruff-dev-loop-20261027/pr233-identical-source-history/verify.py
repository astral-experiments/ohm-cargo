"""Verify both released compilers and every successful and failing metadata lookup."""
from pathlib import Path
import collections, hashlib, json
here=Path(__file__).resolve().parent
def read(n):return json.loads((here/n).read_bytes())
d=read('actual-parser-lookup.json'); hashes=read('released-parser-hashes.json')['samples']['build']
for arm in 'BC':
    ins=d['native_parser_inputs'][arm]
    assert ins['cold']['source_inputs']==ins['restored']['source_inputs']
    observations=d['verified_lookup'][arm]
    assert len(observations)==6
    counts=collections.Counter()
    for r in observations:
        a,b=r['producer'],r['loaded_parser'];source=ins[b]
        meta=hashes[arm][source['history']]
        assert meta['record_sha256']==source['record_sha256'] and meta['parser_rmeta_sha256']==r['parser_rmeta']==source['metadata']
        assert r['compiler']==source['actual_driver'] and r['compiler_argv'][:2]==['rustc','+ohm']
        opens=set(r['actual_successful_parser_opens'])
        assert opens and opens<={source['physical'],source['logical']} and len(r['successful_open_lines'])>=len(opens)
        assert all(any('"'+p+'"' in line for p in opens) and ' = ' in line for line in r['successful_open_lines'])
        assert hashlib.sha256(r['stderr_jsonl'].encode()).hexdigest()==r['raw_diagnostics_sha256']
        ds=[t['code']['code'] for t in (json.loads(l) for l in r['stderr_jsonl'].splitlines() if l) if t.get('code')]
        assert ds==r['diagnostic_codes']
        if a==b:assert r['status']==0 and r['output_sha256'] and not ds
        else:assert r['action']=='consume' and r['status']==1 and r['output_sha256'] is None and ds==['E0463']
        counts[r['action'],r['status']]+=1
    assert counts=={('produce',0):2,('consume',0):2,('consume',1):2}
    a,b=(hashes[arm][ins[k]['history']]['parsed_hashes'] for k in ['cold','restored'])
    assert a[1]==b[1] and a[0]!=b[0] and a[2]!=b[2]
print('Verified both released Rust drivers, four ordinary producers, four same-history readers and four cross-history failures with exact parser file opens.')
