"""Verify the compact projection and summarize exact first-edit/restoration comparisons."""
from pathlib import Path
from collections import Counter
import hashlib,json,sys
d=Path(__file__).resolve().parent; r=d/'h5'
load=lambda p:json.loads(p.read_bytes())
summary={}; caps={};meta={};outer={}
for mode in ('build','test'):
 for arm in 'BC':
  case=mode+'/'+arm; casep=r/'projected'/case
  if not (casep/'restore.json').is_file():continue
  begin=load(casep/'edit.json');end=load(casep/'restore.json');capt=load(r/'captured'/case/'manifest.json');prev={v['stable_crate_id']:v for v in end['jobs']};assert len(prev)==len(begin['jobs'])==capt['job_count']
  assert capt['source_before']['expected'] and capt['source_after_copy']['expected'] and capt['fresh_units']==capt['units'] and capt['command_receipt_sha256']==begin['command_receipt']
  table=Counter();coarse=Counter();labels=[];vs={};expected=len(begin['jobs']);file_count=Counter();byt=Counter()
  for b in capt['jobs']:
   assert len(b['candidate_sessions'])==1 and sum(f['name']=='dep-graph.bin' for f in b['files'])==1 and not b.get('misses') and not b.get('miss')
   t=b['session_start_us'];l,h=capt['command_bounds_us'];assert l<=t<=h
   assert int(b['candidate_sessions'][0].split('-')[1],36)==t
   for f in b['files']:file_count[f['name']]+=1;byt[f['name']]+=f['bytes'];assert len(f['sha256'])==64
  caps[case]=dict(files=dict(file_count),bytes=dict(byt),saved_full_job_graphs=expected)
  for j in begin['jobs']:
   k=j['stable_crate_id'];f=j['result'];g=prev[k]['result'];assert 'failure'not in f and 'failure'not in g
   if j['crate']=='ruff_python_parser':slot='producer';table[(slot,'jobs')]+=1;continue
   slot='explicit' if j['explicit_parser'] else 'without_explicit';table[(slot,'jobs')]+=1
   for nm,selected in [('any_parser_key',f['parser_keys']>0),('crate_public_api_hash','public_api_hash'in f['named'].get('root',{})),('any_exact_lex',bool(f['named'].get('lex'))),('module_children_lexer','module_children'in f['named'].get('lexer',{})),('root_public_directly_in_Metadata',['root','public_api_hash']in f['direct_metadata_inputs']),('lex_or_module_directly_in_Metadata',any(x[0]in ('lex','lexer')for x in f['direct_metadata_inputs']))]:
    if selected:table[(slot,nm)]+=1
   for entry,z in f['named'].items():
    for kind,v in z.items():
     if v!=g['named'].get(entry,{}).get(kind):coarse[(entry,kind)]+=1
   if 'module_children'in f['named'].get('lexer',{}):
    e=f['named']['lexer']['module_children'];z=g['named']['lexer']['module_children'];assert e!=z and j['explicit_parser'];labels.append({'crate':j['crate'],'test':j['test'],'stable_crate_id':k,'edit':e,'restore':z})
  summary[case]=dict(arm=arm,mode=mode,full_jobs=expected,census={a:{b:n for (grp,b),n in table.items()if grp==a} for a in ['producer','explicit','without_explicit']},changed_result_keys={a:{b:n for (grp,b),n in coarse.items()if grp==a}for a in ['root','lexer','lex']},module_queries=labels)
  pp=r/'metadata'/case/'declaration-spans.json'
  if pp.exists():
   v=load(pp);assert v['available']==file_count['metadata.rmeta'] and sum(j['crate']=='ruff_python_parser' for j in v['jobs'])==1
   meta[case]=dict(available=v['available'],external=sum(j['crate']!='ruff_python_parser'for j in v['jobs']),external_file_positions=sum(sum(t.get('lexer_source_file',0)for t in j.get('nonempty_spans',{}).values())for j in v['jobs'] if j['crate']!='ruff_python_parser'),exact_source_producer_span_matches=sum(len(j.get('exact_matches',[]))for j in v['jobs']if j['crate']=='ruff_python_parser'))
  po=r/'captured/typed-queries/immediate-readers'/case
  if (po/'restore.json').exists():
   ee={j['stable_crate_id']:j for j in load(po/'edit.json')['rows']};zz={j['stable_crate_id']:j for j in load(po/'restore.json')['rows']}; assert set(ee)==set(zz)=={x['stable_crate_id']for x in labels}
   for k,z in ee.items():
    assert len(z['incoming'])==1 and z['incoming'][0]['kind']=='visible_parent_map'
    if not zz[k].get('miss'):assert z['incoming']==zz[k]['incoming']
   outer[case]={'only_reader':'visible_parent_map','edit_results':{k:t['incoming'][0]['value']for k,t in ee.items()},'confirmed_equal_restore':sorted(k for k,t in zz.items()if 'incoming'in t),'missing_restore':sorted(k for k,t in zz.items()if 'miss'in t)}
for case,s in summary.items():
 print(case,'graphs',s['full_jobs'],'members',[(j['crate'],j['test'])for j in s['module_queries']],'outer',len(outer.get(case,{}).get('confirmed_equal_restore',[])),meta.get(case))
for p,x in [('aggregate.json',summary),('capture-summary.json',caps),('metadata-summary.json',meta),('immediate-reader-summary.json',outer)]:
 (d/p).write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
