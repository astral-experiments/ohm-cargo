"""Check frozen arms, ordinary commands, collected streams, qualification, raw ELF and decision."""
import ast
from collections import Counter,defaultdict
import gzip,hashlib,io,json,struct,subprocess,sys,tarfile,tempfile
from pathlib import Path
base=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def manifest(b):
    return {v.split('  ',1)[1]:v.split('  ',1)[0] for v in b.decode().splitlines()}
for name,h in manifest((base/'SHA256SUMS').read_bytes()).items():
    assert sha((base/name).read_bytes())==h,name
with tarfile.open(base/'experiment-records.tar.gz') as f:
    rows={e.name:f.extractfile(e).read() for e in f if e.isfile()}
assert {p:sha(b) for p,b in rows.items()}==manifest((base/'archive-members.sha256').read_bytes())
get=lambda n:json.loads(rows[n])
for name in ['v2-registration.json','v21-registration.json']:
    for file,h in json.loads((base/name).read_bytes())['components'].items():
        assert sha((base/file).read_bytes())==h,file
assert rows['qualification/whole-qualification.rc']==rows['qualification/qualification-v2.rc']==b'1\n'
assert rows['qualification/whole-qualification-v21.rc']==rows['timing/whole-score-v21.rc']==b'0\n'
native=get('qualification/qualification-v21/complete.json')
assert len(native)==64 and all(r['actual']==r['expected'] for r in native)
assert set(r['rustc_native_width'] for r in native)==set(range(1,9))
widths={(r['name'],r['rustc_native_width']):r['actual'] for r in native}
assert len(widths)==16
for r in get('qualification/seed-audit/result.json'):
    assert r['matched_live']==(r['tag']=='both')
trace=get('qualification/whole-pilot-v21/qualify/complete.json')
assert len(trace)==4 and all((r['fresh'],r['total'])==(142,148) for r in trace)
for r in trace:
    assert set(map(tuple,r['roster']['jobs']))=={('fixtures','link-only'),('ruff_python_parser','link-only'),('ruff_python_trivia','full')}
stdout=json.loads(gzip.decompress((base/'cargo-stdout-stderr.json.gz').read_bytes()))
dic=stdout['line_dictionary'];assert all(sha(line.encode())==key for key,line in dic.items())
original=get('timing/all-score-originals.json')
counts=Counter()
for key,rec in stdout['commands'].items():
    phase,tag=key.split('/'); tag=tag.split('-')[0]
    counts[phase,tag]+=1; stream=''.join(dic[h] for h in rec['ordered']).encode()
    assert sha(stream)==rec['portable_stdout_sha']
    if phase=='score':
        name='whole-pilot-v21/'+key
        for f,field in [('stdout','raw_stdout_sha'),('stderr','raw_stderr_sha')]:
            assert original[name+'/'+f][1]==rec[field]
        assert sha(rec['stderr'].encode())==rec['raw_stderr_sha']
    if tag in ('slot','reset'):
        assert stream==b'' and 'Running ' not in rec['stderr'] and 'Executable' in rec['stderr']
    else:
        docs=[json.loads(row) for row in stream.splitlines()]
        art=[r for r in docs if r['reason']=='compiler-artifact']
        assert docs[-1]==dict(reason='build-finished',success=True)
        assert len(art)==148 and sum(r['fresh'] for r in art)==(142 if tag=='trace' else 148)
assert counts==Counter({('score','slot'):36,('score','reset'):24,('score','pre'):36,('score','after'):36,('score','initial'):1,('qualify','trace'):4,('qualify','initial'):1,('qualify','fresh'):4})
roster=defaultdict(Counter)
for event in json.loads(gzip.decompress((base/'qualification-exec.json.gz').read_bytes())):
    for call in event['calls']:
        roster[event['phase']][Path(call['exe']).name]+=1
assert len(roster)==4 and all(count==Counter(cargo=2,rustc=3,cc=2,collect2=2,wild=2,**{'ld.bfd':2}) for count in roster.values())
s='timing/whole-pilot-v21/score/'
timed=get(s+'complete.json')
for r in timed:
    sub=s+'slot-%02d-%d/'%(r['block'],r['slot'])
    assert get(sub+'process.json')['ns']==r['ns'] and get(sub+'process.json')['rc']==0
    assert get(sub+'receipt.json')=={k:v for k,v in r.items() if k not in ('block','slot')}
    assert len(r['elf'])==3 and len(r['links'])==2
    for name,mark in r['links'].items():
        assert r['elf'][name]==widths[name,mark['width']]
        assert mark['admitted']==(r['mode']!='full')
    for file,b in rows.items():
        if file.startswith(sub+'logs/'):
            _,name=Path(file).name.split('-',1)
            m=b.split();assert int(m[0])==r['links'][name]['width'] and m[1].decode()==r['mode']
neg=[get('qualification/whole-pilot-v21/qualify/negative-%d/receipt.json'%i) for i in (0,1)]
assert neg[0]['stdout']!=neg[1]['stdout'] and all(not v['admitted'] for n in neg for v in n['links'].values())
with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp);(t/'complete.json').write_bytes(rows[s+'complete.json'])
    result=json.loads(subprocess.check_output([sys.executable,'-B',base/'analyze-pilot.py',t]))
assert result==json.loads((base/'pilot-result.json').read_bytes())
assert result['stats']['selected']['favorable']==7 and result['stats']['oracle']['favorable']==9 and not result['gate_for_more_engineering']
# Recompute independently exactly which field ranges explain the raw ELF differences.
def normal(b):
    shoff=struct.unpack_from('<Q',b,40)[0];step,n,si=struct.unpack_from('<HHH',b,58)
    table=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+step*i) for i in range(n)];off=table[si][4]
    sec={b[off+h[0]:b.index(0,off+h[0])].decode():(i,h) for i,h in enumerate(table)}
    i,h=sec['.rodata'];_,note=sec['.note.gnu.build-id']; start=note[4]+16;sz=struct.unpack_from('<I',b,note[4]+4)[0]
    x=bytearray(b);x[start:start+sz]=bytes(sz);x[shoff+i*step+56:shoff+i*step+64]=bytes(8)
    return sha(x),h[9],b[start:start+sz].hex()
neg=get('dormant/result.json')
for name,x in neg.items():
    assert x['selected']==['main.o','one.o','two.o'] and x['index']==[['dormant','unused.o']] and x['program_exit']==42
    for tool in ('stock','diagnostic'):
        file=rows[f'dormant/{name}/{tool}.elf'];r=x[tool]
        assert sha(file)==r['raw'] and len(file)==r['bytes']
        assert normal(file)==(r['normalized'],r['rodata_entsize'],r['build_id'])
assert neg['small']['stock']==neg['restored']['stock']==neg['large']['diagnostic']
assert neg['small']['stock']['raw']!=neg['large']['stock']['raw'] and neg['small']['stock']['normalized']==neg['large']['stock']['normalized']
assert (neg['small']['stock']['rodata_entsize'],neg['large']['stock']['rodata_entsize'])==(8,0)
print('Verified 36 timed Cargo commands, 24 resets, 73 fresh gates, 64 native qualifications, four Cargo traces, two ordinary callers, and six counterexample ELFs.')
