import json,statistics,sys
from pathlib import Path
p=Path(sys.argv[1])
for f in sorted((p/'cargo-grind-v1').glob('rows/*/edit/supervisor.json')):
    v=json.loads(f.read_bytes());print(f.parent.parent.name,v['ir'],v['totals'])
r=json.loads((p/'buildscript-elf.json').read_bytes());print('build script raw',r['B']['elf']['raw']==r['C']['elf']['raw']);print('matching sections',[(k,r['B']['elf']['sections'][k]==r['C']['elf']['sections'][k]) for k in r['B']['elf']['sections']])
