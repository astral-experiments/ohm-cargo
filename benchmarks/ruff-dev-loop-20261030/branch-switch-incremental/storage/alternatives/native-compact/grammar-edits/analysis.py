from pathlib import Path
import collections,json,statistics,sys
p=Path(__file__).resolve().parent
def stats(data,old):
 obs=data['observations']; report={'pairs':{},'phase':{},'prior_sources':old,'scope':'One four-core Linux host, two mirrored independent installations per compiler. The four edit/restoration commands within one installation share a target and are descriptive, not extra replicates.'}
 for idx in (1,2):
  rr=obs['pair-'+str(idx)+'-R'];kk=obs['pair-'+str(idx)+'-K']; ph={}
  for phase in rr:
   if rr[phase]['kernel']:continue
   s=[z[phase]['cargo_elapsed_ns']/1e9 for z in (rr,kk)]
   ph[phase]={'raw_seconds':s[0],'compact_seconds':s[1],'extra_seconds':s[1]-s[0],'raw_over_compact':s[0]/s[1],'raw_allocated':rr[phase]['storage']['bytes'],'compact_allocated':kk[phase]['storage']['bytes'],'raw_older':rr[phase]['storage']['alternate_exclusive'],'compact_older':kk[phase]['storage']['alternate_exclusive']}
  for label,group in {'first_feature_and_return':['first-B','first-return-A'],'same_branch_dirty':['edit-B','restore-B','edit-B-2','restore-B-2'],'same_branch_edit':['edit-B','edit-B-2'],'same_branch_restore':['restore-B','restore-B-2'],'later_returns':['post-edit-return-A','post-edit-return-B'],'repeats':['unchanged-B','unchanged-final']}.items():
   a=sum(ph[g]['raw_seconds'] for g in group);b=sum(ph[g]['compact_seconds'] for g in group);ph[label]={'calls':len(group),'raw_seconds':a,'compact_seconds':b,'extra_seconds':b-a,'extra_per_call':(b-a)/len(group),'raw_over_compact':a/b}
  report['pairs'][str(idx)]=ph
 for phase in report['pairs']['1']:
  values=[op[phase]for op in report['pairs'].values()];out={}
  for field in ('raw_seconds','compact_seconds','extra_seconds','extra_per_call','raw_allocated','compact_allocated','raw_older','compact_older'):
   if field in values[0]:out[field]=statistics.mean(z[field]for z in values)
  report['phase'][phase]=out
 extra=report['phase']['same_branch_dirty']['extra_per_call']
 gains={k:(old['summary'][k]['parent_seconds']-old['summary'][k]['candidate_seconds'])for k in ('return-A','return-B')}
 report['qualitative_amortization']={'previous_separate_same_compiler_retention_on_vs_default_return_savings_seconds':gains,'this_same_branch_codec_extra_seconds_per_edit':extra,'edits_covering_one_separate_return_saving_by_direction':{k:v/extra if extra>0 else None for k,v in gains.items()},'per_block_costs_seconds_per_edit':[v['same_branch_dirty']['extra_per_call']for v in report['pairs'].values()],'same_study_first_B_vs_trained_return_B_savings_seconds':{role:[obs['pair-'+str(i)+'-'+role]['first-B']['cargo_elapsed_ns']/1e9-obs['pair-'+str(i)+'-'+role]['trained-return-B']['cargo_elapsed_ns']/1e9 for i in (1,2)]for role in ('R','K')}}
 return report
