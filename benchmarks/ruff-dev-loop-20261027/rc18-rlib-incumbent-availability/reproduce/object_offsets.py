import gzip,json,sys
from pathlib import Path
base=Path(sys.argv[1]);other=Path(sys.argv[2])
with gzip.open(base/'all-rosters.json.gz')as f:
    catalog=json.load(f)['archives']
cases=json.loads((other/'archive-ranges.json').read_bytes())['products']
rows=[]
for r in cases:
    native=[m for m in catalog[r['edited_archive']]['members']if m['name'].endswith('.rcgu.o')]
    plain=[{'object':m['name'],'offset':m['offset'],'bytes':m['bytes'],
            'whole_pages_bytes':m['bytes']//4096*4096,'sha256':m['sha256']}for m in native if m['offset']%4096==0]
    rows.append({'crate':r['crate'],'archive':r['edited_archive'],'native_objects':len(native),'aligned':plain})
print(json.dumps({'alignment':4096,'initial_object_file_offset':0,'rows':rows},sort_keys=True,indent=2))
