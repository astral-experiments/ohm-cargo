from pathlib import Path
import hashlib,json
s=Path(__file__).resolve().parent
for line in (s/'SHA256SUMS').read_text().splitlines():
 d,n=line.split('  ',1);assert hashlib.sha256((s/n).read_bytes()).hexdigest()==d
a=json.loads((s/'two-physical-runs.json').read_bytes());b=json.loads((s/'independent-cold.json').read_bytes())
r=a['actual_compilers'];w=a['actual_linkers'];assert len(r)==len(w)==2 and len({x['pid'] for x in r+w})==4 and a['unit_artifact_rows']==1 and a['cargo_exit']==0
assert len({x['argv_raw_expression_sha256'] for x in r})==1 and len({x['argv_raw_expression_sha256'] for x in w})==2 and len({x['output_name'] for x in w})==1 and a['changed_literal_argv_fields']['named object inputs']==42
assert not a['first_owned_elf_retained'] and b['counts']=={'fixtures':1,'generate_inline_tests':1}
for name,rows in b['jobs'].items():
 (x,)=rows;assert x['exit']==0 and x['before_gcc_and_linker'] and x['events']==['rustc-exec','unused JSON write returned','cc-exec','collect2-exec','ld.bfd-exec','rustc exited']
 assert x['own_unused']==('ruff_python_parser' in x['proof']['unused'])==(name=='generate_inline_tests') and x['listed']==(1 if x['own_unused'] else 557)
print('Verified two identical ordinary fixtures compiler argv, two same-output actual Wild invocations, and separately both early compiler reports and held-FD ELF inventories.')
