from pathlib import Path
import gzip,sys,json
o=Path.home()/'.cache';b=o/'ohm-ron-fixed-whole-native-h4-20261028-supplement-v2';w=o/'ohm-ron-same-linker-input-width-h4-20261028-extra-v1'
assert (w/'rc').read_text().strip()=='0'
ctx={'__name__':'decoding','__file__':str(b/'worker.py')};t=(b/'worker.py').read_text();exec(compile(t[:t.index('try:main()')],str(b/'worker.py'),'exec'),ctx)
r=json.loads((w/'complete.json').read_bytes())
for n,v in r.items():
    x=v['native'];v['decoded']={sha:ctx['decode'](w/n/'bodies'/sha) for sha in set(x['widths'].values())};v['historical_raw_sha256_parity']=set(v['workspace_outputs'].values())==set(x['widths'].values())
sys.stdout.buffer.write(gzip.compress(json.dumps(r,sort_keys=True,separators=(',',':')).encode(),mtime=0))
