"""Check the complete final-Cargo regression projection and its raw file commitments."""
from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parent
m={n:h for h,n in (r.split('  ',1) for r in (p/'SHA256SUMS').read_text().splitlines())}; assert set(m)=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'} and all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in m.items())
x=json.loads((p/'outcomes.json').read_bytes()); s=x['subjects'];assert s['cargo_source']=='34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31' and s['cargo_tree']=='bda3469e08fbde973f4d4df6ac6b6d29851ef82b' and s['compiler_tree']=='e560860a8cf3f3c527e4d40fd74f1e828d1f4360' and len(s['target_files'])==53 and s['rust'] in {'eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53','5e3de497d41f4d4fa98fce3082ea43076779de5d'}; assert s['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
for d in x['e0034'].values():
 assert d['verdict']=='correct' and d['rc']==0 and all(d['physical_checks'].values()) and [s[0] for s in d['ordering'] if s[0].startswith(('hold','release','timeout','error'))]==['hold-fd','release-fd'];rows={row['phase']:row for row in d['cargo']}; assert len(rows)==7
 failures=[rows[k]['errors'][0] for k in ('edited','edited-repeat','edited-clean')];assert len({row['rendered_sha256'] for row in failures})==1 and all((e['crate'],e['code'],e['span'])==('client','E0034',3) for e in failures);assert all(rows[k]['finished']['success'] and not rows[k]['errors'] for k in ('original','original-repeat','restore','restore-repeat')) and len(rows['restore-repeat']['fresh'])==4
 hashes=d['existing_state'];assert hashes['restored']['provider']['value']!=hashes['independent-empty-edited']['provider']['value'] and hashes['restored']['reader']['value']==hashes['independent-empty-edited']['reader']['value']; assert all(h['new_rust_header'] for rr in hashes.values() for h in rr.values())
r=x['wrapped_recovery']['detail'];assert r['first_success']=='reverted' and r['value']==1 and r['phases']['reverted']['errors']==[] and r['phases']['reverted']['rustcs']==[['dep','lib'],['app','lib'],['app','bin']];assert len(x['conditional']['results'])==3 and all(v=='ok' for v in x['conditional']['results'].values())
a=x['genuine_interruption'];assert a['phases']['interrupted-provider']['rc']==101 and a['signal']=='SIGKILL' and a['actual_compiler']==s['frontend']; assert all(a['phases'][k]['program_stdout']=='17\n' for k in ('seed','unchanged','revert','revert-again','clean-revert')) and a['phases']['independent-valid-change']['program_stdout']=='29\n'
for row in x['fifo'].values():
 f=row['physical']; assert f['rc']==101 and not f['deadline'] and f['parent_eisdir'] and f['writer_processes']==0 and len(row['open_flags'])==f['fifo_open_calls']==1 and 'O_NONBLOCK' in row['open_flags'][0]
if 'unreached_alt_interrupt' in x:assert x['unreached_alt_interrupt']['rc']==0 and not x['unreached_alt_interrupt']['events']
print('Verified both E0034 orders, first E0460 revert, three conditional pipeline cases, the real compiler interruption and both writerless FIFO precedence controls.')
