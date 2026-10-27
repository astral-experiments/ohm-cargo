from pathlib import Path
import hashlib,json,subprocess,sys
d=Path(__file__).resolve().parent
cases=sys.argv[1:];assert cases and all(s in ('build/B','build/C','test/B','test/C') for s in cases)
base="from pathlib import Path\nimport sys\n"
s=base+(d.parent/'ids.py').read_text()+'\n'+(d.parent/'scan.py').read_text().split('def scan(')[0].replace('from ids import sip13_low','')+'\nkey_fn=keys\n'+(d.parent/'metadata-tables.py').read_text()+'\n'+(d.parent/'meta-scan.py').read_text()+"""
root=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/pr233-h5-lexer-graph-witness-v2a')
print(json.dumps({c:run(root,*c.split('/'))for c in sys.argv[1:]}))
"""
x=json.loads(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','nice','-n','19','taskset','-c','31','/usr/bin/python3','-B','-c',s,*cases],timeout=300))
for c,r in x.items():
 p=d/'metadata'/c;p.mkdir(parents=True,exist_ok=True);(p/'declaration-spans.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
 print(c,r['target'],r['available'],[(j['crate'],len(j.get('exact_matches',[])),j.get('nonempty_spans'))for j in r['jobs']if any(c.get('lexer_source_file') for c in j.get('nonempty_spans',{}).values())])
