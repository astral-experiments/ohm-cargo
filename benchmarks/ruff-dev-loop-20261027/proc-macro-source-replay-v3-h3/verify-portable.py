from pathlib import Path
import gzip,hashlib,json,sys
p=Path(__file__).parent
proof=json.loads((p/'portable-registry.json').read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
alias=proof['replacement'].encode()
original=sys.argv[1].encode() if len(sys.argv)>1 else None
if original is not None:assert sha(original)==proof['registry_component_sha256']
for f,r in proof['files'].items():
    b=(p/f).read_bytes();assert sha(b)==r['portable_file_sha256']
    if r['encoding']=='gzip':b=gzip.decompress(b)
    assert sha(b)==r['portable_content_sha256'] and b.count(alias)==r['occurrences']
    if original is not None:assert sha(b.replace(alias,original))==r['original_content_sha256']
argv=json.loads((p/'ruff/records/train/result.json').read_bytes())['dirty_rustc_argv']
rows=proof['affected_cold_argv'];assert len(rows)==433
assert {r['index'] for r in rows}=={i for i,v in enumerate(argv) if any(alias.decode() in s for s in v)}
for r in rows:
    a=argv[r['index']];assert sha(json.dumps(a,separators=(',',':')).encode())==r['portable_argv_sha256']
    if original is not None:
        raw=[s.replace(alias.decode(),original.decode()) for s in a]
        assert sha(json.dumps(raw,separators=(',',':')).encode())==r['original_argv_sha256']
print('Verified six portable receipts and all 433 affected compiler arguments.')
