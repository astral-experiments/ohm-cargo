"""Describe timing variation after closing every literal cohort, retaining every original observation."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics
import zipfile


def ranks(values):
    positions = collections.defaultdict(list)
    for i,x in enumerate(sorted(values)):
        positions[x].append(i+1)
    return [statistics.mean(positions[value]) for value in values]


def analyze(root):
    output = {}
    for ep in ('check','build','test'):
        normalized = collections.defaultdict(list)
        all_rows = []
        for cohort in ('initial','replica'):
            directory = root/cohort/ep
            assert (directory/'done.json').is_file()
            per_arm = collections.defaultdict(list)
            with (directory/'timings.csv').open() as stream:
                for row in csv.DictReader(stream):
                    obs=directory/f"m{int(row['block']):02}-{row['rank']}-{row['arm']}"/'receipt.json'
                    r=json.loads(obs.read_bytes())
                    assert int(row['elapsed_ns'])==r['elapsed_ns']
                    delta=[y-x for x,y in zip(r['before']['cpu'],r['after']['cpu'])]
                    start=r['before']
                    v=dict(wall=r['elapsed_ns']/1e9,before_dirty_mib=start['dirty_kib']/1024,
                           before_writeback_mib=start['writeback_kib']/1024,before_load1=start['load'][0],
                           steal=delta[7]/sum(delta),iowait=delta[4]/sum(delta),user=r['seconds_user'],
                           system=r['seconds_system'],input_blocks=r['input_blocks'],out_blocks=r['output_blocks'],
                           involuntary_switches=r['involuntary_switches'],minor_faults=r['minor_faults'],
                           rank=int(row['rank']),sequence=int(row['block']))
                    per_arm[row['arm']].append(v)
                    all_rows.append(v)
            for arm,samples in per_arm.items():
                assert len(samples)==24
                for key in samples[0]:
                    normalized[key].extend(ranks([v[key] for v in samples]))
        assert len(all_rows)==192
        correlations={k:round(statistics.correlation(normalized['wall'],v),4)
                      for k,v in normalized.items() if k!='wall' and len(set(v))>1}
        ranges={}
        for key in ('before_dirty_mib','before_writeback_mib','steal','iowait','wall','user','system','input_blocks','out_blocks'):
            values=sorted(x[key] for x in all_rows)
            ranges[key]=dict(median=statistics.median(values),min=values[0],max=values[-1])
        output[ep]=dict(commands=len(all_rows),before_dirty_gt64mib=sum(v['before_dirty_mib']>64 for v in all_rows),
                        before_dirty_gt1024mib=sum(v['before_dirty_mib']>1024 for v in all_rows),
                        zero_reads=sum(v['input_blocks']==0 for v in all_rows),ranges=ranges,
                        rank_correlations_with_elapsed_within_cohort_and_arm=correlations)
    return output


def main():
    home=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path,nargs='?',default=home/'observations.zip')
    parser.add_argument('--output',type=Path,default=home/'starting-host-variance.json')
    args=parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        output=analyze(zipfile.Path(archive)/'evidence')
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    for ep,r in output.items():
        print(ep,'>64MiB dirty',r['before_dirty_gt64mib'],'>1GiB',r['before_dirty_gt1024mib'],'zero reads',r['zero_reads'],'/192')
        print('starting load/dirty/writeback rho',
              {k:v for k,v in r['rank_correlations_with_elapsed_within_cohort_and_arm'].items() if 'before' in k})
        print('within-command rho',
              {k:r['rank_correlations_with_elapsed_within_cohort_and_arm'].get(k) for k in ('steal','iowait','user','system','input_blocks','minor_faults')})


if __name__=='__main__':
    main()
