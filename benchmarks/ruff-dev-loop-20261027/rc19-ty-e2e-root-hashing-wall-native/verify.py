"""Independent review of the portable wall and native projections. Requires the registered analysis module."""
import argparse,gzip,hashlib,json,math,statistics,sys
from pathlib import Path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('result',type=Path);parser.add_argument('protocol',type=Path);opts=parser.parse_args();base=opts.result;protocol=opts.protocol;sets=lambda p:json.loads(p.read_bytes())
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 files=set()
 for e in (protocol/'SHA256SUMS').read_text().splitlines():
  h,n=e.split('  ',1);p=Path(n);assert not p.is_absolute() and '..'not in p.parts and n not in files;files.add(n);assert sha(protocol/p)==h
 assert sha(protocol/'SHA256SUMS')=='16c0f700933507b539b532b4c8a8d28a8b5453827383659be439ef53a29f8511'
 source=sets(protocol/'design/requirements.json');gold=sets(protocol/'design/whole-reference.json');order=sets(protocol/'design/orders.json');z=sets(base/'result.json');assert z['plan']==sha(protocol/'SHA256SUMS') and z['order']==sha(protocol/'design/orders.json')
 with gzip.open(base/'native-and-slot-proof.json.gz','rb')as f:rows=json.load(f)
 assert len(rows)==z['count'];index={(x['arm'],x['visit']):x for x in rows};assert len(index)==len(rows)
 complete=not z['stopped'] and not z.get('native_only');successful=0;invalid=0;elapsed=0
 for x in rows:
  if 'exit'not in x:assert z['stopped'];continue
  m=x['source'];missing=(m=='invalid');assert x['exit']==(101 if missing else 0);assert x['units']==(299 if missing else 300) and x['fresh']==(300 if x['expected']=='settled'else 299);successful+=not missing;invalid+=missing
  if missing:
   assert x['errors'] and all(e[0]=='E0308'and any(v[0]==22 for v in e[1]) for e in x['errors']);assert x['launches']['wild_total']==0
  else:
   assert x['elf']==gold['sources'][m]['elf'] and len(x['runtime'])==4 and all(rr['status']==0 for rr in x['runtime'].values()) and len(x['metadata_consumer'])==64
   assert x['source_witness'][m]>=0 and x['source_witness']['edited' if m=='original'else'original']==-1
   if x['expected']!='settled':
    proof=x['recipe'];assert proof['all_histories_wire']==gold['sources'][m]['all_histories_wire'] and proof['body']==x['after']['sha256'] and len(proof['cache_mask'])==139 and len(proof['raw_cfg'])==23 and all(len(rr)==2 for rr in proof['raw_cfg'])
   if 'launches'in x:
    rec=x['launches'];assert rec['cached']==[]
    if x['expected']=='settled':assert rec['full']==[] and rec['wild_total']==0
    else:assert rec['full']==['e2e'] and rec['wild_total']==1 and set(rec['root_native'].values())=={1}
  if 'io'in x:
   io=x['io'];assert io['inputs']==io['opened']==140 and io['executable_stats']>0 and io['read_bytes']==(io['size']if x['arm']=='warm-parent'else 0)
  for w in ('before','after'):assert x[w]['existence'] in ('regular','absent')
 if complete:
  assert len(rows)==220 and invalid==2
  ticks=sets(base/'original-monotonic-clocks.json');data=sets(base/'analysis.json');assert len(ticks)==32 and data['orders']==order['orders']
  times=[]
  for i,pair in enumerate(ticks,1):
   assert (pair['pair'],pair['order'])==(i,order['orders'][i-1]);r={}
   for a in ('parent','child'):
    v=pair[a];assert v['end_ns']>v['start_ns']>0 and v['elapsed_ns']==v['end_ns']-v['start_ns'] and v['status']==0;r[a]=v['elapsed_ns'];elapsed+=1
   first,second=(('parent','child')if pair['order']=='RF'else('child','parent'));assert pair[first]['end_ns']<=pair[second]['start_ns']
   if i>1:assert max(ticks[i-2][a]['end_ns']for a in ('parent','child'))<=min(v['start_ns']for v in (pair['parent'],pair['child']))
   for t in (['edit','reset']if i>1 else['edit']):
    rp=index['warm-parent','pair-%02d-%s'%(i,t)]['recipe'];rc=index['warm-child','pair-%02d-%s'%(i,t)]['recipe'];assert all(rp[k]==rc[k]for k in ('same_history_wire','cache_mask','source_bases','raw_cfg','absolute_current_object_identifiers'))
   times.append(r)
  assert times==data['rows_ns'];sys.path.insert(0,str(protocol/'worker'));from analyze_wall import analyze
  again=analyze(times,order['orders'],order['bootstrap_seed']);assert all(data[k]==v for k,v in again.items());assert data['median_log_ratio']==statistics.median(math.log(v['child']/v['parent']) for v in times)
  for a in ('parent','child'):
   for label in ('post-restore','post-settled','post-edit'):assert index['warm-'+a,label]['flavor']=='native'
 print(json.dumps({'projection_verified':True,'native_records':len(rows),'success':successful,'intentional_E0308':invalid,'validated_wall_slots':elapsed,'stopped':z['stopped'],'native_only':z.get('native_only',False)},sort_keys=True))
if __name__=='__main__':main()
