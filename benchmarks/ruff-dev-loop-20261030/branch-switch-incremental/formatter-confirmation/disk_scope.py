"""Describe stored allocation in the original successful ordinary visits, outside the primary inference."""
import gzip
import json
from pathlib import Path
from statistics import median

CAPACITY=12*(1<<30)
PHASES=['empty-A','first-B','return-A','return-B','unchanged-B']

def collect(observations):
    summary={'scope':'private 12-GiB tmpfs, before and after Cargo; inode-deduplicated target/shared incremental blocks after checks',
             'capacity':CAPACITY,'ELFs':observations['elf_cas'],'phases':{}}
    for phase in PHASES:
        metrics={}
        for i in range(1,13):
            for arm in ('P','Q'):
                row=observations['slots'][f'n{i:02d}-{arm}'][phase]
                before=CAPACITY-row['usage_before']['private'];after=CAPACITY-row['usage_after']['private']
                inc=row['incremental_allocated_bytes'];assert 0<=before<CAPACITY and 0<inc<=after<CAPACITY
                for name,value in {'private_fs_used_before':before,'private_fs_used_after':after,'incremental_charged':inc,
                                   'incremental_regular_apparent':row['incremental_apparent_bytes']}.items():
                    point=metrics.setdefault(name,{'P':[],'Q':[]});point[arm].append(value)
        for point in metrics.values():
            p,q=point['P'],point['Q'];point['medians']={arm:median(point[arm]) for arm in ('P','Q')}
            point['median_paired_candidate_minus_parent_bytes']=median(y-x for x,y in zip(p,q))
            point['median_paired_candidate_over_parent']=median(y/x for x,y in zip(p,q))
        summary['phases'][phase]=metrics
    return summary
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('observations',type=Path);args=parser.parse_args()
    raw=args.observations.read_bytes();raw=gzip.decompress(raw) if args.observations.suffix=='.gz' else raw
    print(json.dumps(collect(json.loads(raw)),sort_keys=True,indent=2))
