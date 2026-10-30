#!/usr/bin/env python3
"""Verify the portable paired branch-return observations; print descriptive per-installation Ir."""
from collections import Counter
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import re
import sys

root=Path(__file__).resolve().parent
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):
    assert re.fullmatch(r'[0-9a-f]{64}',v)
for row in (root/'SHA256SUMS').read_text().splitlines():
    expected,name=row.split('  ',1)
    assert '/' not in name and sha(root/name)==expected
receipt=json.loads((root/'verified.json').read_bytes())
assert receipt['slots']==8 and receipt['counted_cargo']==receipt['trace_flanks']==16 and receipt['profiled_rustcs']==32
assert receipt['real_stock_wild_in_counted_tests']==8 and receipt['real_stock_wild_in_counted_checks']==0
for k in ('raw_sha256','raw_file_manifest_sha256','independent_reader','results_sha256'):
    digest(receipt[k])
assert receipt['results_sha256']==sha(root/'results.json.gz')
assert receipt['complete_raw_files']>500 and receipt['tar_bytes']>0 and receipt['raw_bytes']>=receipt['tar_bytes']
raw=gzip.decompress((root/'results.json.gz').read_bytes())
assert all(s not in raw for s in (b'/home/',b'/mnt/',b'.openai.org',b'/run/user/'))
d=json.loads(raw)
assert d['parent']=='7e71d3150938ff8ed82aca03416439d7e5b87ef3' and d['candidate']=='6b7f424ece4bc978ead5546b73e1b31d5ccb1e70' and d['cargo']=='2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c'
assert d['tools']['native_files_per_sdk']==55 and d['tools']['Wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5' and d['tools']['Cargo']=='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add'
assert d['ops_manifest']=='5d7435377ef3487533b854f17898850c9d89ee683a92dce8c2ecd40caeb38eda' and d['bundle']=='2c0c1b9a55bee99207ee17eed612639ee214fa7a6bfa8a4ba8657e84a9ad79f9'
assert d['amendment']['original_manifest']=='e35c9f55bcbff2a46b2dfd43b5b7bc076d08d5b13524449211fcd7a3907e0a9b' and d['amendment']['pid_specific_startup_logs']['complete_pairs_attached_from_it']==0
cores=('ruff_python_ast','ruff_python_parser')
records=d['records']
assert [x['slot'] for x in records]==['check-1-P','check-1-Q','test-1-Q','test-1-P','test-2-P','test-2-Q','check-2-Q','check-2-P']
assert len({x['driver'] for x in records})==2
pids=set();forks=set();branches={}
for x in records:
    verb,pair,arm=x['verb'],x['pair'],x['arm']
    assert x['driver']=={'Q':'b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c','P':'66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e'}[arm]
    refs=d['references'][verb]
    for tag,b in [('empty-A','A'),('first-B','B'),('return-A','A'),('return-B','B'),('unchanged-B','B'),('native-A','A'),('native-B','B')]:
        y=x['phases'][tag];ref=refs['branch'][b]
        assert [y['typed'],y['typed_roster']]==refs['typed_by_phase'][tag]
        assert y['typed']==(97 if verb=='check' else 151 if tag in ('empty-A','unchanged-B') else 149)
        digest(y['Cargo_stdout']);digest(y['Cargo_stderr'])
        if tag.startswith(('return-','native-')):assert y['dirty']==list(cores)
        if tag=='unchanged-B':assert y['dirty']==[]
        if verb=='test':
            assert y['ELF']==ref['ELF'] and y['inventory']==ref['inventory'] and y['tests']==ref['tests']==245
        else:
            assert y['expected_size']==ref['expected_size']==(64 if b=='A' else 56)
            for k in cores:
                digest(y['root_metadata'][k]);assert re.fullmatch('[0-9a-f]{32}',y['public_hashes'][k])
            if tag.startswith(('return-','native-')): assert y['public_hashes']==x['phases']['empty-A' if b=='A' else 'first-B']['public_hashes']
        if tag.startswith('return-'):
            assert y['wild']==int(verb=='test') and set(y['compilers'])==set(cores)
            assert y['sum']==sum(t['instruction_count'] for t in y['compilers'].values())
            if verb=='test': digest(y['Wild_argv']);assert y['Wild_pid']>0
            for k in cores:
                t=y['compilers'][k];assert t['pid'] not in pids and t['instruction_count']>0;pids.add(t['pid'])
                for fld in ('argv','fds','jobserver','profile','terminal_log'):digest(t[fld])
                if verb=='check':assert 'metadata' in t['emit'] and 'link' not in t['emit']
            for f in y['fork_startup_only']:
                assert f['zero_terminal_count'] and f['pid']!=f['parent']==y['compilers']['ruff_python_parser']['pid'] and f['bytes']>0 and verb=='test'
                digest(f['log_sha256']);forks.add(f['pid'])
            n=x['native_flanks'][b];assert n['compilers']=={k:1 for k in cores} and n['wild']==int(verb=='test')
            for k in cores:assert n['same_literal_argv_as_profile'][k]==(n['original_argv'][k]==y['compilers'][k]['argv'])
            branches[(verb,pair,arm,b)]=y
assert len(pids)==32 and len(branches)==16
buf=io.StringIO();w=csv.writer(buf,delimiter='\t',lineterminator='\n')
w.writerow(['verb','pair','return_branch','compiler','parent_Ir','guarded_Ir','parent_over_guarded'])
for verb in ('check','test'):
    for pair in (1,2):
        for b in ('A','B'):
            p=branches[verb,pair,'P',b];q=branches[verb,pair,'Q',b]
            for n in (*cores,'sum'):
                a,z=(p['sum'],q['sum']) if n=='sum' else (p['compilers'][n]['instruction_count'],q['compilers'][n]['instruction_count'])
                w.writerow([verb,pair,b,n,a,z,f'{a/z:.4f}'])
content=buf.getvalue()
if len(sys.argv)==2 and sys.argv[1]=='--write-table':
    with (root/'instruction-counts.tsv').open('x') as f:f.write(content)
else:
    assert (root/'instruction-counts.tsv').read_text()==content
    print(content,end='')
    print(f"Verified 32 profiled compilers, 16 counted Cargo returns, 16 native flanks, {len(forks)} excluded startup-only fork logs.")
