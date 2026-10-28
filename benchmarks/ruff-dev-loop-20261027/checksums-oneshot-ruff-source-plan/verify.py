"""Verify fixture source, corrected and rejected native receipts, and zero-score binding."""
from pathlib import Path
from hashlib import sha256
import collections,gzip,json,tomllib
p=Path(__file__).resolve().parent
h=lambda q:sha256(q.read_bytes()).hexdigest()
load=lambda n:json.loads((p/n).read_bytes())
ss={}
for line in (p/'SHA256SUMS').read_text().splitlines():
 x,n=line.split('  ',1);assert n not in ss;ss[n]=x;assert h(p/n)==x
assert set(ss)=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
s=load('sources.json');q=load('screen-plan.json');o=load('oracle.json');n=load('native-control.json')
assert s['parent']==q['source']==n['applies_git_commit']=='105fe8286bef83e1ad1b62b3a2c015a6ace57ee7'
assert h(p/'candidate.patch')==s['candidate_patch']==q['patch']==n['candidate_patch']
assert q['analysis_sha256']==h(p/'analyze.py') and q['recreator_sha256']==h(p/'recreate-corpus.py')
assert n['performance_observations']==0 and n['rustfmt_entire_patched_module']
for name,d in s['isolated_source'].items():assert h(p/'fixture/src'/name)==d
a=load('fixture-binary.json');assert a['binary']==q['harness']==n['parent_elf']==n['candidate_elf']
cargo=tomllib.loads((p/'fixture/Cargo.lock').read_text())['package']
assert all(s['packages'][r['name']+'@'+r['version']]==r['checksum'] for r in cargo if 'checksum' in r)
assert s['harness']==h(p/'fixture/src/main.rs')
v=gzip.decompress((p/'corpus.json.gz').read_bytes());assert sha256(v).hexdigest()==q['corpus']==s['corpus'];corpus=json.loads(v)
A=corpus['actual_inputs'];assert len(A)==len(set(x['path'] for x in A))==q['files_per_sweep']==o['files']==n['native_cases']['corpus']==1238
assert [r['file'] for r in A]==list(range(len(A))) and sum(r['size'] for r in A)==o['bytes']==q['bytes_per_sweep']==12381544
assert len({x['git'] for x in A})<=len(A) and corpus['excluded_generated_paths']==3
assert sum(r['size']<65536 for r in A)==1215 and sum(1024<r['size']<65536 for r in A)==1090
sha=sha256(b''.join(bytes.fromhex(row['sha256']) for row in A)).hexdigest();assert sha==o['sha256_python_reference']
native=(p/'correctness.stdout').read_text().strip()
assert 'synthetic=5200 physical=96 corpus=1238' in native and 'blake3='+o['blake3_c_reference'] in native
assert bytes(int(x,16) for x in native.split('sha256=[',1)[1][:-1].split(', ')).hex()==sha
assert h(p/'correctness.stdout')==n['corrected_output_sha256'] and (p/'correctness.stderr').read_bytes()==b''
reports=[{k:v for k,v in (pair.split('=') for pair in (p/name).read_text().strip().split())} for name in ('rejected-first-slice/packet-v1.stdout','packet-v2.stdout')]
assert reports[0]['candidate']!=reports[0]['expected']==reports[0]['parent']==reports[1]['expected']==reports[1]['candidate']==reports[1]['parent']
assert n['initial_packet_sketch_rejected']==h(p/'rejected-first-slice/candidate.patch') and len(q['orders'])==12 and collections.Counter(tuple(pair) for pair in q['orders'])=={('before','after'):6,('after','before'):6}
print('Exact #262 source, both native width/packet histories, 5200 scripted cases, 96 physical mutations, and 1238 captured source digests verified. No performance observations.')
