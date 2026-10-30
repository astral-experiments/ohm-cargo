from pathlib import Path
from statistics import mean
def analyze(j):
 per={}; aggregate={}; obs=j['observations']
 for h in (1,2):
  R=obs[f'pair-{h}-R']; K=obs[f'pair-{h}-K']; block={}
  for ph,x in R.items():
   y=K[ph]; fields={'raw_allocated':x['storage']['bytes'],'switch_allocated':y['storage']['bytes'],'raw_older':x['storage']['alternate_exclusive'],'switch_older':y['storage']['alternate_exclusive'],'switch_packed_files':y['storage']['packed_counts']}
   if x['kernel'] is None:
    sec=[z['cargo_elapsed_ns']/1e9 for z in (x,y)];fields.update(raw_s=sec[0],switch_s=sec[1],delta_s=sec[1]-sec[0],raw_over_switch=sec[0]/sec[1])
   else:
    fields.update(raw_full=x['kernel']['full'],switch_full=y['kernel']['full'],wild=[x['kernel']['wild'],y['kernel']['wild']],switch_table_io=y['kernel']['events'])
   block[ph]=fields
  for name,phases in {'first_feature_then_A':['first-B','first-return-A'],'first_B_local_edit':['edit-B'],'later_B_local_edits':['restore-B','edit-B-2','restore-B-2'],'all_B_local_edits':['edit-B','restore-B','edit-B-2','restore-B-2']}.items():
   a=mean(block[n]['raw_s'] for n in phases);b=mean(block[n]['switch_s']for n in phases);block[name]={'calls':len(phases),'raw_s_per_call':a,'switch_s_per_call':b,'delta_s_per_call':b-a,'delta_s_sum':(b-a)*len(phases)}
  per[str(h)]=block
 for ph in per['1']:
  z=per['1'][ph];z2=per['2'][ph]
  aggregate[ph]={k:(z[k]+z2[k])/2 for k in z if k in ('raw_s','switch_s','delta_s','raw_allocated','switch_allocated','raw_older','switch_older','raw_s_per_call','switch_s_per_call','delta_s_per_call','delta_s_sum')}
 result={'per_block':per,'means':aggregate,'filesystem':j['filesystem'],'native':{},'oracles':{}}
 allrows=[(s,n,r)for s,v in obs.items()for n,r in v.items()];native=[(s,n,r)for s,n,r in allrows if r['kernel']];result['native']['flanks']=len(native);result['native']['physical_wild']=sum(r['kernel']['wild']for s,n,r in native);result['native']['physical_full']=sum(len(r['kernel']['full']) for s,n,r in native)
 result['oracles']['matching_final_ELFs']=sum(r['elf']==j['refs'][(s.split('-')[1] if s.startswith('ref-') else s[-1])+'/'+r['source']]['elf'] for s,n,r in allrows)
 dirty=[z for s,n,r in allrows if s.startswith('pair-') and len(r['dirty'])in (1,2) for z in r['rlibs'].values()]
 result['oracles'].update(dirty_library_comparisons=len(dirty),matching_object_multisets=sum(v['native_objects_match_empty']for v in dirty),matching_raw_archives=sum(v['archive_matches_empty']for v in dirty),matching_metadata=sum(v['metadata_matches_empty']for v in dirty))
 return result
