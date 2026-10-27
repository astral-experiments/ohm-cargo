"""Only def_span and def_ident_span are inspected, to avoid treating arbitrary matching bytes as spans."""
from pathlib import Path
import collections,hashlib,json,os,sys
def check_case(dir,defs,target):
 report=[]
 for j in defs:
  matching=[f for f in j['files']if f['name']=='metadata.rmeta']
  if not matching:continue
  f,=matching;p=dir/j['trace']/f['name'];m=p.read_bytes();assert hashlib.sha256(m).hexdigest()==f['sha256']
  rd=R(m);deps=rd.deps();own=j['crate']=='ruff_python_parser';pid=0 if own else next((e[1] for e in deps if e[0]=='ruff_python_parser'),None)
  if pid is None:report.append({'crate':j['crate'],'stable':j['stable_crate_id'],'metadata_sha256':f['sha256'],'has_parser_dependency':False});continue
  keys,fs=decode(p);row={'crate':j['crate'],'test':j['test'],'stable':j['stable_crate_id'],'metadata_sha256':f['sha256'],'has_parser_dependency':True,'parser_dependency_number':pid,'nonempty_spans':{}}
  hit=[];coverage=[]
  for table,rows in fs.items():
   count=collections.Counter()
   for low,span in rows.items():
    if not span or len(span)!=6:continue
    kind,ctxt,lo,n,source,producer=span
    if kind!=(0 if own else 1) or producer!=pid:continue
    count['producer']+=1
    if source!=target['ordinal']:continue
    count['lexer_source_file']+=1
    if (lo,n) in [(target['def'][0],target['def'][1]),(target['ident'][0],target['ident'][1])]:
     hit.append(dict(table=table,owner=f'{low:016x}',ctxt=ctxt,lo=lo,length=n,ordinal=source))
    if lo<=target['ident'][0] and lo+n>=sum(target['ident']):
     count['contains_lex_identifier']+=1;coverage.append([table,f'{low:016x}',lo,n])
   row['nonempty_spans'][table]=dict(count)
  row['exact_matches']=hit;row['containing_ranges']=coverage[:8];report.append(row)
 return report
def run(root,mode,arm):
 d=root/mode/arm;man=json.loads((d/'manifest.json').read_bytes())
 p=next(j for j in man['jobs']if j['crate']=='ruff_python_parser' and not j['test']);pm=d/p['trace']/'metadata.rmeta';ks,fs=decode(pm)
 # The low definition key derives independently from the matched real Cargo/rustc stable-crate ID.
 _,lex_key,_=key_fn(p['stable_crate_id']);file_low=int(lex_key,16)
 local=fs['def_span'][file_low];ident=fs['def_ident_span'][file_low]
 assert local[0]==ident[0]==0 and local[1]==ident[1]==0 and local[4]==ident[4] and ident[3]==3
 target={'ordinal':local[4],'def':local[2:4],'ident':ident[2:4],'lex_key':lex_key,'stable_crate':p['stable_crate_id']}
 result=check_case(d,man['jobs'],target)
 expected=[f for j in man['jobs']for f in j['files'] if f['name']=='metadata.rmeta'];assert len(result)==len(expected)
 return dict(target=target,available=len(result),jobs=result)
