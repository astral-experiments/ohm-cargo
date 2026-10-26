"""Audit the unscored before/after and same-compiler oracles from their stored raw maps."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path


def main():
    here=Path(__file__).resolve().parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',nargs='?',type=Path,default=here);a=p.parse_args();d=a.directory;raw=json.loads(gzip.decompress((d/'qualification.json.gz').read_bytes()));cases=raw['cases'];report={'seed_digests':raw['seed_digests'],'driver_ctimes':raw['driver_ctimes'],'private_proof_counts':raw['proof_counts'],'schema':{},'cases':{}};cross={k:[] for k in ('metadata','api')};threads=[]
    def changed(A,B):assert set(A)==set(B);return sorted(k for k,v in A.items() if v!=B[k])
    schemas=set();api_values=[]
    for c,arms in cases.items():
        case_report={};report['cases'][c]=case_report
        for arm,obs in arms.items():
            assert not obs['warm_roster'] and not obs['before']['roster'] and not obs['after']['roster'] and obs['before']['fresh']==obs['after']['fresh']==520
            counts=collections.Counter(ob['flags'][-1] for ob in obs['threads'].values());case_report[arm]={'actual_rustcs':len(obs['roster']),'one_thread':counts[1],'eight_threads':counts[8],'before_vs_after':{}}
            for key,ob in sorted(obs['threads'].items()):threads.append({'case':c,'arm':arm,'crate':ob['crate'],'fingerprint':key,'prior_dep_info_bytes':ob['prior_dep_info_bytes'],'rustc_thread_flags':','.join(map(str,ob['flags']))})
            for key in ['metadata','api']:
                assert len(obs['before'][key])==(442 if key=='metadata' else 435);diff=changed(obs['before'][key],obs['after'][key]);case_report[arm]['before_vs_after'][key]=diff
            for stage in ['before','after']:
                for value in obs[stage]['api'].values():
                    j=json.loads(value);schemas.add((tuple(sorted(j)),j['version'],len(j['value'])));assert all(c in '0123456789abcdef' for c in j['value']);api_values.append(value)
        crossrow={};case_report['comparisons']=crossrow
        for stage in ['before','after']:
            crossrow[stage]={}
            for key in ('metadata','api'):
                diff=changed(arms['A'][stage][key],arms['B'][stage][key]);cross[key].append(set(diff));same=changed(arms['nine'][stage][key],arms['B'][stage][key]);assert diff==raw['comparisons'][c]['control_ten_'+stage][key] and same==raw['comparisons'][c]['nine_ten_'+stage][key] and not same
                crossrow[stage][key]={'control_ten_differences':len(diff),'nine_ten_differences':len(same)}
    assert schemas=={(('value','version'),1,32)};report['schema']={'fields':['version','value'],'version':1,'value':'32 lowercase hexadecimal characters','values_checked':len(api_values)}
    report['cross_compiler_differing_sets']={}
    for k,sets in cross.items():
        assert len(sets)==4 and all(s==sets[0] for s in sets);report['cross_compiler_differing_sets'][k]={'count':len(sets[0]),'same_sets_before_and_after_both_edits':True,'files':sorted(sets[0])}
    with (d/'thread-decisions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=threads[0]);w.writeheader();w.writerows(threads)
    (d/'qualification-summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print({k:v['count'] for k,v in report['cross_compiler_differing_sets'].items()},report['schema'])
if __name__=='__main__':main()
