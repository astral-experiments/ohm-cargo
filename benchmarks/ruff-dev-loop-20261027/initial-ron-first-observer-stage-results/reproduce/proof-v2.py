"""Authenticate all input bytes against first-observation and independently forced regular receipts."""
import hashlib,json,re,struct,subprocess,sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');H=P/'first-proof-stage1';Q=H/'proof-check-v2';Q.mkdir(exist_ok=False);sum3=H/'blake3-file'
def sha(x):
 with x.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def b3(x):return subprocess.check_output([sum3,x],text=True).strip()
def true_path(path,state):
 q=Path(path)
 for k,v in [(P/'native-target',state/'target'),(P/'shared',state/'build'),(P/'rustup/toolchains/ohm',H/'sysroot'),(P/'frozen-toolchain',H/'sysroot'),(P/'registry-home',P/'registry-home'),(H/'fixture-root',state/'src')]:
  if q.is_relative_to(k):return v/q.relative_to(k)
 if not q.is_absolute():return state/'src'/q
 raise ValueError(path)
report={}
for arm in ('PP','AP','PA','AA'):
 st=H/'matrix-v2'/('tiny-'+arm);dep,=(st/'target').rglob('out/ron-*.d');encoded,=(st/'target').rglob('dep-lib-ron');raw=encoded.read_bytes();body=Q/(arm+'-covered.bin');body.write_bytes(raw[:-32]);assert b3(body)==raw[-32:].hex() and raw[-41:-37]==b'OBS1' and raw[-33]==1;body.unlink()
 rows=[]
 for s in dep.read_text().splitlines():
  if not s.startswith('# checksum:'):continue
  m=re.fullmatch(r'# checksum:(blake3|sha256)=([0-9a-f]{64}) file_len:(\d+) (.+)',s);assert m,s;actual=true_path(m[4].replace('\\ ',' '),st);assert actual.is_file(),actual;got=sha(actual) if m[1]=='sha256' else b3(actual);assert got==m[2] and actual.stat().st_size==int(m[3]),(actual,m[2],got);row={'file':actual.name,'algorithm':m[1],'digest':got,'bytes':actual.stat().st_size};rows.append(row)
 (Q/(arm+'-input-blake3.json')).write_text(json.dumps(sorted(rows,key=lambda x:(x['file'],x['bytes'],x['digest'])),indent=2)+'\n');report[arm]={'rustc_depinfo_sha256':sha(dep),'cargo_encoded_sha256':sha(encoded),'sealed_bytes':len(raw),'entries':len(rows),'raw_checksum_count':len(rows),'content_verified':True,'input_list':sha(Q/(arm+'-input-blake3.json')),'seal_blake3':raw[-32:].hex(),'rustc_file_bytes':dep.stat().st_size}
assert report['PP']==report['AP'] and report['AA']==report['PA'];print(report['PP']);print(report['AA']);(Q/'receipts.json').write_text(json.dumps(report,indent=2)+'\n')
