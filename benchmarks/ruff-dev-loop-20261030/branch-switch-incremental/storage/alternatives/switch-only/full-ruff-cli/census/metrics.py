"""Compare physical storage and classify every charged byte within the two observed histories."""
from pathlib import Path
import json
PHASES=('empty-A','first-B','return-A','return-B','unchanged-B')
def pair(off,on):
    return {'off':off,'on':on,'change_bytes':on-off,'percent_from_off':(on/off-1)*100 if off else None}
def compute(obs):
    slots=obs['slots']
    report={'phases':{},'empty_B':{},'complete_own_mode_elf_and_reader':{},'category_failures':{}}
    for phase in PHASES:
        a,b=(slots[m+'-storage']['phase'][phase] for m in ('off','on'))
        desc={k:pair(a['settled'][k],b['settled'][k]) for k in ('all','all_incremental','incremental_only','incremental_also_named_outside','products','shared','both_roots_same_inode')}
        desc['maximum_observed']=pair(a['sampler']['max_observed'],b['sampler']['max_observed'])
        for key in ('raw','packed'):
            desc[key+'_tables']=pair(a['tables'][key]['allocated'],b['tables'][key]['allocated'])
        desc['table_change']=desc['raw_tables']['change_bytes']+desc['packed_tables']['change_bytes']
        desc['other_change']=desc['all']['change_bytes']-desc['table_change']
        if all('category' in v for v in (a,b)):
            ca,cb=(v['category']['classes'] for v in (a,b))
            categories={k:pair(ca.get(k,{}).get('bytes',0),cb.get(k,{}).get('bytes',0)) for k in sorted(ca.keys()|cb.keys())}
            for key,charge in categories.items():
                charge['number_of_inodes']={mode:cl.get(key,{}).get('unique_inodes',0) for mode,cl in [('off',ca),('on',cb)]}
                charge['number_of_names']={mode:cl.get(key,{}).get('names',0) for mode,cl in [('off',ca),('on',cb)]}
                charge['bytes_exclusively_in_incremental_directories']=pair(ca.get(key,{}).get('incremental_only',0),cb.get(key,{}).get('incremental_only',0))
                charge['bytes_in_incremental_and_other_directories']=pair(ca.get(key,{}).get('incremental_and_outside',0),cb.get(key,{}).get('incremental_and_outside',0))
            assert sum(q['change_bytes'] for q in categories.values())==desc['all']['change_bytes']
            desc['all_physical_classes']=categories
            desc['largest_absolute_class_changes']=sorted(categories,key=lambda k:(-abs(categories[k]['change_bytes']),k))
            desc['cross_class_aliases']=pair(a['category']['slices'].get('cross_category',0),b['category']['slices'].get('cross_category',0))
        report['phases'][phase]=desc
    for mode in ('off','on'):
        d=slots[mode+'-clean-B']['phase']['empty-B']
        report['empty_B'][mode]={'whole':d['settled']['all'],'incremental':d['settled']['all_incremental'],'sampled_max':d['sampler']['max_observed'],'size_and_sha':d['cli'],'physical':d['physical']}
        for rev,src in [('A','empty-A'),('B','empty-B')]:
            controls=slots[mode+('-storage' if rev=='A' else '-clean-B')]['phase'][src]
            actual=slots[mode+'-storage']['phase']['return-'+rev]
            assert all(actual[k]==controls[k] for k in ('cli','reader','cli_verdicts','reader_observed','source'))
            report['complete_own_mode_elf_and_reader'][mode+'-'+rev]={'cli':actual['cli'],'reader':actual['reader'],'equals_separately_built_8ea':actual['cli']==actual['prior_actual_hashes']['cli'],'matches_empty':True,'consumer':actual['reader_observed']}
    maxima={m:max(slots[m+'-storage']['phase'][t]['sampler']['max_observed'] for t in PHASES) for m in ('off','on')}
    report['largest_allocation_during_history']=pair(**maxima)
    rows=[(s,n,v) for s,slot in slots.items() for n,v in slot['phase'].items()]
    report['sampler']={'nominal_interval_ns':10_000_000,'range_of_command_median_gaps_ns':[min(r[2]['sampler']['gaps_ns']['median'] for r in rows),max(r[2]['sampler']['gaps_ns']['median'] for r in rows)],'maximum_gap_ns':max(r[2]['sampler']['gaps_ns']['max'] for r in rows),'total_samples':sum(r[2]['sampler']['count'] for r in rows)}
    report['ledger']={'visits':len(rows),'paths_per_visit':[min(r[2]['paths'] for r in rows),max(r[2]['paths'] for r in rows)],'all_phase_weak_or_unknown':sum(1 for r in rows if 'category' not in r[2]),'maximum_unique_inodes':max((r[2]['category']['unique_inodes'] for r in rows if 'category' in r[2]),default=0),'mixed_class_unique_inodes_by_visit':{s+'/'+n:sum(g['unique_inodes'] for k,g in v['category']['classes'].items() if '+' in k) for s,n,v in rows if 'category' in v},'all_reported_regular_nlink_outside_visible_roots':{s+'/'+n:v['category']['regular_with_unseen_nlink'] for s,n,v in rows if 'category' in v}}
    report['category_failures']={s+'/'+n:v['category_error'] for s,n,v in rows if 'category_error' in v}
    report['kit_roles_matching_previous_bytes']={k:sum(v['same_sha'] for v in s['compared_previous_57'].values()) for k,s in slots.items()}
    return report
if __name__=='__main__':
    parent=Path(__file__).resolve().parent;print(json.dumps(compute(json.loads((parent/'observations.json').read_bytes())),indent=2,sort_keys=True))
