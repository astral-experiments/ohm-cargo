"""Reopen the immutable first-edit copies after capture and verify SHA256 and declared sizes."""
from pathlib import Path
import hashlib,json,subprocess,sys
d=Path(__file__).resolve().parent
r="""from pathlib import Path
import hashlib,json,sys
root=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/pr233-h5-lexer-graph-witness-v2a');out={}
for case in sys.argv[1:]:
 p=root/case;m=json.loads((p/'manifest.json').read_bytes());rs=[]
 for j in m['jobs']:
  for f in j['files']:
   file=p/j['trace']/f['name']
   with file.open('rb')as h:got=hashlib.file_digest(h,'sha256').hexdigest()
   assert got==f['sha256'] and file.stat().st_size==f['bytes']
   rs.append([j['trace'],f['name'],f['bytes'],got])
 payload=json.dumps(sorted(rs),sort_keys=True,separators=(',',':')).encode()
 out[case]=dict(file_count=len(rs),total_bytes=sum(x[2]for x in rs),sha256_of_sorted_json_rows=hashlib.sha256(payload).hexdigest(),capture_manifest_sha256=hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest())
print(json.dumps(out))
"""
out=json.loads(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','nice','-n','19','taskset','-c','31','/usr/bin/python3','-B','-c',r,*sys.argv[1:]],timeout=400))
for case,v in out.items():
 p=d/'readback'/case;p.mkdir(parents=True,exist_ok=True);(p/'receipt.json').write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');print(case,v)
