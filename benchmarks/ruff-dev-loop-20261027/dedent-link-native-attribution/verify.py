"""Check retained release fingerprints, native layouts, real ELF/body digests and phase rows."""
import argparse,hashlib,json,re,statistics
from pathlib import Path
from runpy import run_path
p=Path(__file__).resolve().parent
rd=lambda rel:json.loads((p/rel).read_bytes())
digest=lambda b:hashlib.sha256(b).hexdigest()
api=run_path(str(p/'audit.py'));norm=api['stable'];decode=api['decode_layout']
checks=(p/'SHA256SUMS').read_text().splitlines()
for line in checks:
 h,n=line.split('  ',1);f=p/n;assert f.is_file() and digest(f.read_bytes())==h,n
assert {l.split('  ',1)[1] for l in checks}=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
arc=rd('archive-member-receipts.json');d=rd('section-receipts.json');r=rd('native-rows.json')
ch,=d['summary']['changed_objects'];maps={s:{x['stable']:x for x in k['members']} for s,k in arc.items()}
assert all(len(m)==43 for m in maps.values())
assert len(arc['seed']['ordered_gnu_symbols'])==221 and arc['seed']['ordered_gnu_symbols']==arc['reversed']['ordered_gnu_symbols']==arc['restored']['ordered_gnu_symbols']
assert maps['seed'].keys()==maps['reversed'].keys()==maps['restored'].keys()
objs=[n for n in maps['seed'] if n.endswith('.o')];assert len(objs)==41
assert all(maps['seed'][n]['sha256']==maps['restored'][n]['sha256'] for n in objs)
assert [n for n in objs if maps['reversed'][n]['sha256']!=maps['restored'][n]['sha256']]==[ch]
for s in ['reversed','restored']:
 for f in sorted((p/'layouts'/s).glob('*.layout')):
  files,_=decode(f.read_bytes());key=f.stem;selected={}
  for path,obj,ranges,_ in files:
   if not Path(path).name.startswith('libruff_python_trivia-'):continue
   lo,hi,n=obj;k=norm(n);m=maps[s][k];assert (lo,hi,n)==(m['begin'],m['end'],m['raw'])
   selected[k]={tuple(rr) for rr in ranges if rr is not None}
  assert len(selected)==30 and ch not in selected
  assert selected=={n:{tuple(x) for x in vals.values()} for n,vals in d['selected'][s][key].items()}
  assert sum(map(len,selected.values()))==(111 if key.startswith('fixtures') else 108)
 assert r[s]['total']==148 and r[s]['fresh']==142 and r[s]['elf']==r['seed']['elf']
 assert sorted(r[s]['processes']['jobs'])==sorted([['ruff_python_trivia','full'],['ruff_python_parser','link-only'],['fixtures','link-only']])
 assert len(r[s]['processes']['wild'])==2
 assert len(r[s]['artifact_digests'])==266
 sd=d['objects'][ch]['sections_changed'];k,=[n for n in sd if n.startswith('.text.') and 'dedent_to' in n]
 body=(p/('native-body-'+s+'.bin')).read_bytes();assert digest(body)==sd[k][s][-1]
 assert len(sd)==17 and len(body)==(1715 if s=='reversed' else 1712)
 assert len(rd('destination-'+s+'.json'))==2 and all(int(x['errno'])==0 for x in rd('destination-'+s+'.json'))
 assert all(x['stat'][0].split()[3]=='1' for x in rd('destination-'+s+'.json'))
assert d['selected']['reversed']==d['selected']['restored']
for tag in ['0-reversed','1-restored','2-reversed']:
 allfiles,_=decode((p/'ordinary'/tag/'caller.layout').read_bytes());inp=[(e,rng) for path,e,rng,_ in allfiles if path.endswith('/libruff_python_trivia-control.rlib') and e and norm(e[-1])==ch];assert len(inp)==1
 st=tag.split('-',1)[1];known=rd('ordinary/'+('0-reversed' if st=='reversed' else '1-restored')+'/receipt.json');no=known['dedent_text']['object_section'][0]
 assert list(inp[0][1][no])==known['dedent_text']['range'] and known['full_exe']==r[tag]['raw_sha256'] and known['stdout']==r[tag]['stdout']
assert r['0-reversed']==r['2-reversed'] and r['0-reversed']['stdout']!=r['1-restored']['stdout']
x,y=(decode((p/'ordinary'/s/'caller.layout').read_bytes())[0] for s in ['0-reversed','2-reversed'])
changed=[(a,b) for a,b in zip(x,y) if a!=b];assert len(x)==len(y)==45 and len(changed)==1 and changed[0][0][1:]==changed[0][1][1:] and all(Path(v[0]).name=='symbols.o' for v in changed[0])
a=[k for k,v in r['closure-restored']['elf'].items() if v!=r['closure-reversed']['elf'][k]];assert len(a)==1 and Path(a[0]).name.startswith('ruff_python_parser')
assert r['closure-restored']['elf'][a[0]].startswith('ff1cdc736d8e') and r['closure-reversed']['elf'][a[0]].startswith('2ca7bf551f8f')
rows=rd('native-phases/stage.json');assert len(rows)==48
for name in sorted({rr['name'] for rr in rows}):
 summary={row['width']:row for row in rd('summary.json')[name]}
 for width in range(1,9):
  q=[rr for rr in rows if rr['name']==name and rr['width']==width];assert len(q)==3
  assert len({rr['elf'] for rr in q})==len({rr['rodata_entsize'] for rr in q})==1
  assert all(rr['elf']==summary[width]['elf'] for rr in q)
  if name.startswith('ruff_python_parser'):
   assert q[0]['rodata_entsize']==(0 if width==1 else 8);expected=r['closure-restored' if width==1 else 'closure-reversed']['elf'][a[0]]
  else:expected=next(v for k,v in r['seed']['elf'].items() if Path(k).name==name)
  assert q[0]['elf']==expected;records=[]
  for rr in q:
   terms={m[2]:float(m[1]) for line in (p/'native-phases'/rr['phase']).read_text().splitlines() if (m:=re.search(r'([0-9.]+) (.+)$',line))}
   records.append(sum(terms[k] for k in ['Section resolution','Layout','Write output file']))
  assert statistics.median(records)==summary[width]['postselection_three_ms']
 cost=rd('proof-cost/'+name+'.json');assert len(cost)==56
 for width in [1,2,4,8]:
  q=[row for row in cost if row['kind']=='selected' and row['t']==width];assert len(q)==7 and len({rr['key'] for rr in q})==1
  assert statistics.median(rr['combined_ms'] for rr in q)==summary[width]['selected_proof_ms']
print('PASS. Three archive generations, 221 symbol associations, four release layouts, three ordinary native callers, 48 exact raw linker replays and 112 checksum/publication rows.')
