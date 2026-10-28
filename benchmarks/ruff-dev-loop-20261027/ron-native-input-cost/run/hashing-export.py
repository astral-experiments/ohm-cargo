from pathlib import Path
import gzip,hashlib,json,sys
s=Path.home()/'.cache/ohm-ron-native-positive-input-cost-h4-20261028-v1';assert (s/'rc').read_text().strip()=='0'
x=json.loads((s/'complete.json').read_bytes());b=json.loads((s/'build.json').read_bytes());assert hashlib.sha256((s/'hash-inputs').read_bytes()).hexdigest()==b['hasher']
for name,v in x.items():
    p=s/name;k=v['native'];assert hashlib.sha256((p/'actual.d').read_bytes()).hexdigest()==k['raw_depfile_sha256'] and k['hasher']==b['hasher']
    assert v['reproduced_one_exact_native'] and len(k['rows'])==6 and len(k['native_depfile_paths'])>100
    for u in k['native_depfile_paths']:
        if u['class']=='system':
            f=Path(u['resolved']);assert f.is_file() and f.stat().st_size==u['bytes']
sys.stdout.buffer.write(gzip.compress(json.dumps({'tool':b,'data':x},sort_keys=True,separators=(',',':')).encode(),mtime=0))
