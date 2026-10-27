"""Read focused wire keys from a retained dep-graph with the exact writer discriminants."""
import argparse,json,subprocess
from pathlib import Path
from scan import keys,scan
d=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('graph',type=Path);p.add_argument('parser_stable_crate_id');p.add_argument('--writer',choices=['B','C'],required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--incoming-binary',type=Path)
a=p.parse_args();ns=json.loads((d/('writer-kinds-'+a.writer+'.json')).read_bytes())['kinds']
o=scan(a.binary.resolve(),a.graph,a.parser_stable_crate_id,ns)
if a.incoming_binary:
 proc=subprocess.run([a.incoming_binary.resolve(),a.graph,*keys(a.parser_stable_crate_id),str(ns.index('module_children'))],text=True,capture_output=True,check=True)
 o['module_query_readers']=[{'reader_query':ns[int(n)],'reader_key':[h,l],'result_fingerprint':v}for t,n,h,l,v in (r.split()for r in proc.stdout.splitlines()if r.startswith('input_to '))]
print(json.dumps(o,sort_keys=True,indent=2))
